from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth import (
    SCOPE_QUOTES_ADMIN,
    SCOPE_QUOTES_APPROVE,
    AuthenticatedCaller,
    require_bearer_scope,
)
from app.db import get_db, init_db
from app.models import CommercialChangeAction, CommercialChangeEvent, CommercialChangeResourceType, Contract, ContractMatchType, ContractRateRule, EquipmentType, ExchangeRate, ImpactAnalysisChangeType, ImpactAnalysisRun, MarketRateSnapshot, OutboxConsumerCheckpoint, OutboxEvent, PortScope, PricingBasis, PricingStrategyVersion, Quote, QuoteLifecycleState, QuoteValidityPolicy, RateTable, SurchargeRule, SurchargeType
from app.seed import REFERENCE_DATA_VERSION, seed_reference_data
from app.schedules import Schedule, ScheduleProvider, get_schedule_provider
from app.service_connections import check_configured_service_health
from app.surcharges import EquipmentSelection, SurchargeLineItem, calculate_surcharges, total_surcharges


_MONEY_PRECISION = Decimal("0.01")
_QUOTE_STATUS_ACTIVE = "ACTIVE"
_QUOTE_STATUS_EXPIRED = "EXPIRED"
_QUOTE_STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
_QUOTE_STATUS_REJECTED = "REJECTED"
_QUOTE_STATUS_BOOKED = "BOOKED"
_QUOTE_STATUS_VOID = "VOID"
_BOOKABILITY_REASON_OPEN = "VALIDITY_WINDOW_OPEN"
_BOOKABILITY_REASON_EXPIRED = "VALIDITY_WINDOW_EXPIRED"
_BOOKABILITY_REASON_APPROVAL_PENDING = "APPROVAL_PENDING"
_BOOKABILITY_REASON_APPROVAL_REJECTED = "APPROVAL_REJECTED"
_BOOKABILITY_REASON_ALREADY_BOOKED = "QUOTE_ALREADY_BOOKED"
_BOOKABILITY_REASON_REVOKED = "QUOTE_REVOKED"
_OUTBOX_AGGREGATE_QUOTE = "quote"
_OUTBOX_AGGREGATE_RATE_TABLE = "rate_table"
_OUTBOX_AGGREGATE_SURCHARGE_RULE = "surcharge_rule"
_QUOTE_CREATED_EVENT = "quote.created"
_QUOTE_EXPIRED_EVENT = "quote.expired"
_QUOTE_APPROVED_EVENT = "quote.approved"
_QUOTE_REJECTED_EVENT = "quote.rejected"
_QUOTE_REVOKED_EVENT = "quote.revoked"
_RATE_UPDATED_EVENT = "rate.updated"
_SURCHARGE_UPDATED_EVENT = "surcharge.updated"
_OUTBOX_EVENT_VERSION = 1
_SOURCE_CURRENCY = "USD"
_ROUNDING_POLICY = "LINE_ITEM_HALF_UP_2DP"
_MAX_ALTERNATIVE_OPTIONS = 10
_MARKET_APPROVAL_CAPACITY_PRESSURE_THRESHOLD = 0.85
_MARKET_APPROVAL_UTILIZATION_THRESHOLD = 0.9
_MARKET_APPROVAL_SEASONALITY_THRESHOLD = 0.75
_EQUIPMENT_AVAILABILITY_STATUS_AVAILABLE = "AVAILABLE"
_EQUIPMENT_AVAILABILITY_STATUS_AVAILABLE_WITH_SUBSTITUTIONS = "AVAILABLE_WITH_SUBSTITUTIONS"
_EQUIPMENT_AVAILABILITY_STATUS_SHORTAGE = "SHORTAGE"
_EQUIPMENT_TYPE_ALIASES = {
    "40HC": EquipmentType.FORTY_FT_HC.value,
}
_ALTERNATIVE_PRICING_ORDER = {
    PricingBasis.CONTRACT: 0,
    PricingBasis.PUBLIC_TARIFF: 1,
    PricingBasis.MARKET: 2,
}


@dataclass(frozen=True)
class ResolvedPricing:
    pricing_basis: PricingBasis
    rates_by_type: dict[EquipmentType, object]
    surcharge_line_items: list[SurchargeLineItem]
    contract: Contract | None = None
    market_source: str | None = None
    market_signals: dict[str, float] = field(default_factory=dict)
    optimization_trace: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedQuoteValidity:
    valid_until: datetime
    snapshot: dict[str, object]


class PricingModeHint(str, Enum):
    AUTO = "AUTO"
    PUBLIC_TARIFF = "PUBLIC_TARIFF"
    CONTRACT = "CONTRACT"
    MARKET = "MARKET"


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ResolvedFxRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    provider: str
    observed_at: datetime
    reference_data_version: str


def _normalize_equipment_type_value(value: object) -> object:
    if isinstance(value, str):
        return _EQUIPMENT_TYPE_ALIASES.get(value.upper(), value)

    return value


class QuoteEquipmentRequest(BaseModel):
    type: EquipmentType
    quantity: int = Field(gt=0)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> object:
        return _normalize_equipment_type_value(value)


class CreateQuoteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schedule_id: str = Field(alias="scheduleId")
    equipment: list[QuoteEquipmentRequest] = Field(min_length=1)
    cargo_weight_kg: Decimal = Field(alias="cargoWeightKg", gt=0)
    customer_id: str | None = Field(default=None, alias="customerId", min_length=1)
    account_id: str | None = Field(default=None, alias="accountId", min_length=1)
    currency: str = Field(default=_SOURCE_CURRENCY, min_length=3, max_length=3)
    pricing_mode_hint: PricingModeHint | None = Field(default=None, alias="pricingModeHint")
    include_alternative_options: bool = Field(default=False, alias="includeAlternativeOptions")
    max_alternative_options: int | None = Field(
        default=None,
        alias="maxAlternativeOptions",
        ge=1,
        le=_MAX_ALTERNATIVE_OPTIONS,
    )

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class RepriceQuoteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trigger: str = Field(min_length=1, max_length=64)


class QuoteRevocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(min_length=1, max_length=240)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("reason is required")
        return reason


class ValidateRateCoverageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    origin_port: str = Field(alias="originPort", min_length=1)
    destination_port: str = Field(alias="destinationPort", min_length=1)
    departure_date: date = Field(alias="departureDate")
    equipment: list[QuoteEquipmentRequest] = Field(min_length=1)


class EquipmentAvailabilitySnapshotItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    equipment_type: EquipmentType = Field(alias="equipmentType")
    available_count: int = Field(alias="availableCount", ge=0)
    depot_code: str | None = Field(default=None, alias="depotCode", min_length=1)

    @field_validator("equipment_type", mode="before")
    @classmethod
    def normalize_equipment_type(cls, value: object) -> object:
        return _normalize_equipment_type_value(value)


class EquipmentSubstitutionPolicyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requested_type: EquipmentType = Field(alias="requestedType")
    substitute_type: EquipmentType = Field(alias="substituteType")
    priority: int = Field(ge=1)
    reason: str = Field(min_length=1)
    active: bool = Field(default=True, alias="isActive")

    @field_validator("requested_type", "substitute_type", mode="before")
    @classmethod
    def normalize_equipment_types(cls, value: object) -> object:
        return _normalize_equipment_type_value(value)


class PlanEquipmentAvailabilityRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    equipment: list[QuoteEquipmentRequest] = Field(min_length=1)
    availability: list[EquipmentAvailabilitySnapshotItem] = Field(default_factory=list)
    substitutions: list[EquipmentSubstitutionPolicyRequest] = Field(default_factory=list)
    depot_code: str | None = Field(default=None, alias="depotCode", min_length=1)


class AdminRateTableRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    origin_port: str = Field(alias="originPort", min_length=1)
    destination_port: str = Field(alias="destinationPort", min_length=1)
    equipment_type: EquipmentType = Field(alias="equipmentType")
    base_rate_usd: Decimal = Field(alias="baseRateUsd", gt=0)
    valid_from: date = Field(alias="validFrom")
    valid_to: date = Field(alias="validTo")

    @model_validator(mode="after")
    def validate_window(self) -> "AdminRateTableRequest":
        if self.valid_to < self.valid_from:
            raise ValueError("validTo must be on or after validFrom")
        return self


class AdminRateTableUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    origin_port: str | None = Field(default=None, alias="originPort", min_length=1)
    destination_port: str | None = Field(default=None, alias="destinationPort", min_length=1)
    equipment_type: EquipmentType | None = Field(default=None, alias="equipmentType")
    base_rate_usd: Decimal | None = Field(default=None, alias="baseRateUsd", gt=0)
    valid_from: date | None = Field(default=None, alias="validFrom")
    valid_to: date | None = Field(default=None, alias="validTo")


class AdminSurchargeRuleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    surcharge_type: SurchargeType = Field(alias="surchargeType")
    description: str = Field(min_length=1)
    amount_usd: Decimal = Field(alias="amountUsd", gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    port_code: str | None = Field(default=None, alias="portCode", min_length=1)
    port_scope: PortScope | None = Field(default=None, alias="portScope")
    weight_threshold_kg_per_teu: Decimal | None = Field(default=None, alias="weightThresholdKgPerTeu", gt=0)
    valid_from: date | None = Field(default=None, alias="validFrom")
    valid_to: date | None = Field(default=None, alias="validTo")

    @model_validator(mode="after")
    def validate_scope(self) -> "AdminSurchargeRuleRequest":
        if (self.port_code is None) != (self.port_scope is None):
            raise ValueError("portCode and portScope must be provided together")
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("validTo must be on or after validFrom")
        return self


class AdminSurchargeRuleUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    surcharge_type: SurchargeType | None = Field(default=None, alias="surchargeType")
    description: str | None = Field(default=None, min_length=1)
    amount_usd: Decimal | None = Field(default=None, alias="amountUsd", gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    port_code: str | None = Field(default=None, alias="portCode", min_length=1)
    port_scope: PortScope | None = Field(default=None, alias="portScope")
    weight_threshold_kg_per_teu: Decimal | None = Field(default=None, alias="weightThresholdKgPerTeu", gt=0)
    valid_from: date | None = Field(default=None, alias="validFrom")
    valid_to: date | None = Field(default=None, alias="validTo")


class AdminQuotePreviewRequest(CreateQuoteRequest):
    rate_table_ids: list[str] = Field(default_factory=list, alias="rateTableIds")
    surcharge_rule_ids: list[str] = Field(default_factory=list, alias="surchargeRuleIds")


class ReplayOutboxRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    batch_size: int = Field(default=100, alias="batchSize", ge=1, le=500)
    from_start: bool = Field(default=False, alias="fromStart")
    event_types: list[str] = Field(default_factory=list, alias="eventTypes")
    aggregate_types: list[str] = Field(default_factory=list, alias="aggregateTypes")


class ImpactAnalysisRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    change_type: ImpactAnalysisChangeType = Field(alias="changeType")
    schedule_id: str | None = Field(default=None, alias="scheduleId", min_length=1)
    contract_id: str | None = Field(default=None, alias="contractId", min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "ImpactAnalysisRequest":
        if self.change_type == ImpactAnalysisChangeType.SCHEDULE:
            if self.schedule_id is None:
                raise ValueError("scheduleId is required for SCHEDULE impact analysis")
            if self.contract_id is not None:
                raise ValueError("contractId is not allowed for SCHEDULE impact analysis")
        if self.change_type == ImpactAnalysisChangeType.CONTRACT:
            if self.contract_id is None:
                raise ValueError("contractId is required for CONTRACT impact analysis")
            if self.schedule_id is not None:
                raise ValueError("scheduleId is not allowed for CONTRACT impact analysis")
        return self


class QuoteApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    decision: ApprovalDecision
    note: str | None = Field(default=None, min_length=1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_reference_data()
    yield


app = FastAPI(title="Quotes Service", lifespan=lifespan)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def _serialize_decimal(value: Decimal) -> float:
    return float(value)


def _serialize_optional_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None

    return float(value)


def _serialize_optional_date(value: date | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _actor_from_auth(caller: AuthenticatedCaller, actor: str | None) -> str:
    if actor is not None and actor.strip():
        return actor.strip()
    return caller.subject


def _require_actor(
    authorization: str | None = Header(default=None, alias="Authorization"),
    actor: str | None = Header(default=None, alias="X-Actor"),
) -> str:
    caller = require_bearer_scope(authorization, SCOPE_QUOTES_ADMIN)
    return _actor_from_auth(caller, actor)


def _require_quote_approval_actor(
    authorization: str | None = Header(default=None, alias="Authorization"),
    actor: str | None = Header(default=None, alias="X-Actor"),
) -> str:
    caller = require_bearer_scope(authorization, SCOPE_QUOTES_APPROVE)
    return _actor_from_auth(caller, actor)


@app.get("/admin/service-connections/equipments")
def check_equipments_service_connection(_: str = Depends(_require_actor)) -> dict[str, object]:
    return check_configured_service_health(
        service="equipments",
        base_url_env="EQUIPMENTS_SERVICE_URL",
        health_path_env="EQUIPMENTS_HEALTH_PATH",
        timeout_env="EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS",
    )


def _quote_approval_decision(quote: Quote) -> dict[str, object] | None:
    if not quote.approval_decision:
        return None

    return quote.approval_decision


def _serialize_quote(quote: Quote) -> dict[str, object]:
    source_total_amount = _quote_source_total_amount(quote)
    payload = {
        "id": quote.id,
        "quoteReference": quote.quote_reference,
        "lifecycleState": quote.lifecycle_state.value,
        "scheduleId": quote.schedule_id,
        "scheduleSnapshot": quote.schedule_snapshot,
        "equipment": quote.equipment,
        "cargoWeightKg": _serialize_decimal(quote.cargo_weight_kg),
        "currency": quote.currency,
        "sourceCurrency": quote.source_currency,
        "responseCurrency": quote.currency,
        "fx": _quote_fx_snapshot(quote),
        "roundingPolicy": _quote_rounding_policy(quote),
        "pricingBasis": quote.pricing_basis.value,
        "pricingProvenance": quote.pricing_provenance,
        "approvalReasons": quote.approval_reasons,
        "approvalDecision": _quote_approval_decision(quote),
        "customerId": quote.customer_id,
        "accountId": quote.account_id,
        "contractId": quote.contract_id,
        "idempotencyKey": quote.idempotency_key,
        "lineItems": [
            {
                "description": item["description"],
                "amount": float(item["amount"]),
            }
            for item in quote.line_items
        ],
        "sourceTotalAmount": source_total_amount,
        "totalAmount": _serialize_decimal(quote.total_amount),
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }

    if quote.repriced_from_quote_id is not None:
        payload["repricedFromQuoteId"] = quote.repriced_from_quote_id
        payload["repricingTrigger"] = quote.repricing_trigger
        payload["varianceSummary"] = quote.variance_summary

    return payload


def _serialize_created_quote(quote: Quote) -> dict[str, object]:
    source_total_amount = _quote_source_total_amount(quote)
    return {
        "id": quote.id,
        "quoteReference": quote.quote_reference,
        "validUntil": quote.valid_until.isoformat(),
        "currency": quote.currency,
        "sourceCurrency": quote.source_currency,
        "responseCurrency": quote.currency,
        "lifecycleState": quote.lifecycle_state.value,
        "approvalReasons": quote.approval_reasons,
        "approvalDecision": _quote_approval_decision(quote),
        "fx": _quote_fx_snapshot(quote),
        "roundingPolicy": _quote_rounding_policy(quote),
        "lineItems": [
            {
                "description": item["description"],
                "amount": float(item["amount"]),
            }
            for item in quote.line_items
        ],
        "sourceTotalAmount": source_total_amount,
        "totalAmount": _serialize_decimal(quote.total_amount),
    }


def _build_quote_event_payload(quote: Quote) -> dict[str, object]:
    source_total_amount = _quote_source_total_amount(quote)
    payload = {
        "quoteId": quote.id,
        "quoteReference": quote.quote_reference,
        "lifecycleState": quote.lifecycle_state.value,
        "scheduleId": quote.schedule_id,
        "scheduleSnapshot": quote.schedule_snapshot,
        "equipment": quote.equipment,
        "cargoWeightKg": _serialize_decimal(quote.cargo_weight_kg),
        "currency": quote.currency,
        "sourceCurrency": quote.source_currency,
        "responseCurrency": quote.currency,
        "fx": _quote_fx_snapshot(quote),
        "roundingPolicy": _quote_rounding_policy(quote),
        "customerId": quote.customer_id,
        "accountId": quote.account_id,
        "contractId": quote.contract_id,
        "pricingBasis": quote.pricing_basis.value,
        "pricingProvenance": quote.pricing_provenance,
        "approvalReasons": quote.approval_reasons,
        "approvalDecision": _quote_approval_decision(quote),
        "lineItems": quote.line_items,
        "sourceTotalAmount": source_total_amount,
        "totalAmount": _serialize_decimal(quote.total_amount),
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }

    if quote.repriced_from_quote_id is not None:
        payload["repricedFromQuoteId"] = quote.repriced_from_quote_id
        payload["repricingTrigger"] = quote.repricing_trigger
        payload["varianceSummary"] = quote.variance_summary

    return payload


def _serialize_outbox_event(event: OutboxEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "aggregateType": event.aggregate_type,
        "aggregateId": event.aggregate_id,
        "eventType": event.event_type,
        "eventVersion": event.event_version,
        "payload": event.payload,
        "occurredAt": event.occurred_at.isoformat(),
        "publishedAt": _serialize_optional_datetime(event.published_at),
        "publishAttempts": event.publish_attempts,
        "lastError": event.last_error,
    }


def _serialize_checkpoint(checkpoint: OutboxConsumerCheckpoint) -> dict[str, object]:
    return {
        "consumerName": checkpoint.consumer_name,
        "lastEventId": checkpoint.last_event_id,
        "lastOccurredAt": _serialize_optional_datetime(checkpoint.last_occurred_at),
        "processedEventsCount": checkpoint.processed_events_count,
        "lastReplayedBy": checkpoint.last_replayed_by,
        "updatedAt": checkpoint.updated_at.isoformat(),
    }


def _serialize_impact_analysis(run: ImpactAnalysisRun) -> dict[str, object]:
    return {
        "id": run.id,
        "changeType": run.change_type.value,
        "targetId": run.target_id,
        "actor": run.actor,
        "summary": run.summary,
        "createdAt": run.created_at.isoformat(),
    }


def _build_commercial_change_event_payload(
    *,
    resource_type: CommercialChangeResourceType,
    resource_id: str,
    action: CommercialChangeAction,
    actor: str,
    resource_version: int,
    snapshot: dict[str, object],
    occurred_at: datetime,
) -> dict[str, object]:
    return {
        "resourceType": resource_type.value,
        "resourceId": resource_id,
        "action": action.value,
        "actor": actor,
        "resourceVersion": resource_version,
        "snapshot": snapshot,
        "occurredAt": _normalize_utc(occurred_at).isoformat(),
    }


def _commercial_change_event_contract(resource_type: CommercialChangeResourceType) -> tuple[str, str]:
    if resource_type == CommercialChangeResourceType.RATE_TABLE:
        return _OUTBOX_AGGREGATE_RATE_TABLE, _RATE_UPDATED_EVENT

    return _OUTBOX_AGGREGATE_SURCHARGE_RULE, _SURCHARGE_UPDATED_EVENT


def _enqueue_quote_event(
    db: Session,
    *,
    quote: Quote,
    event_type: str,
    occurred_at: datetime | None = None,
    payload_extra: dict[str, object] | None = None,
) -> None:
    payload = _build_quote_event_payload(quote)
    if payload_extra is not None:
        payload.update(payload_extra)

    db.add(
        OutboxEvent(
            aggregate_type=_OUTBOX_AGGREGATE_QUOTE,
            aggregate_id=quote.id,
            event_type=event_type,
            event_version=_OUTBOX_EVENT_VERSION,
            payload=payload,
            occurred_at=_normalize_utc(occurred_at or datetime.now(timezone.utc)),
        )
    )


def _get_schedule(schedule_id: str, schedule_provider: ScheduleProvider) -> Schedule:
    schedule = schedule_provider.get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return schedule


def _get_quote_or_404(quote_id: str, db: Session) -> Quote:
    quote = db.scalar(select(Quote).where(or_(Quote.id == quote_id, Quote.quote_reference == quote_id)))
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    return quote


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _quote_is_expired(quote: Quote, *, now: datetime | None = None) -> bool:
    effective_now = _normalize_utc(now or datetime.now(timezone.utc))
    return _normalize_utc(quote.valid_until) <= effective_now


def _sync_quote_lifecycle(quote: Quote, db: Session) -> Quote:
    if quote.lifecycle_state in {
        QuoteLifecycleState.BOOKED,
        QuoteLifecycleState.EXPIRED,
        QuoteLifecycleState.REJECTED,
        QuoteLifecycleState.VOID,
    }:
        return quote

    if not _quote_is_expired(quote):
        return quote

    quote.lifecycle_state = QuoteLifecycleState.EXPIRED
    _enqueue_quote_event(db, quote=quote, event_type=_QUOTE_EXPIRED_EVENT)
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


def _quote_revocation_conflict_detail(quote: Quote) -> str:
    if quote.lifecycle_state == QuoteLifecycleState.PENDING_APPROVAL:
        return "Pending approval quotes cannot be revoked"
    if quote.lifecycle_state == QuoteLifecycleState.EXPIRED:
        return "Expired quotes cannot be revoked"
    if quote.lifecycle_state == QuoteLifecycleState.REJECTED:
        return "Rejected quotes cannot be revoked"
    if quote.lifecycle_state == QuoteLifecycleState.BOOKED:
        return "Booked quotes cannot be revoked"
    if quote.lifecycle_state == QuoteLifecycleState.VOID:
        return "Revoked quotes cannot be revoked again"

    return "Only active or approved quotes can be revoked"


def _serialize_bookability(quote: Quote) -> dict[str, object]:
    if quote.lifecycle_state == QuoteLifecycleState.PENDING_APPROVAL:
        return {
            "quoteId": quote.quote_reference,
            "bookable": False,
            "status": _QUOTE_STATUS_PENDING_APPROVAL,
            "reason": _BOOKABILITY_REASON_APPROVAL_PENDING,
            "expired": False,
            "validUntil": quote.valid_until.isoformat(),
        }

    if quote.lifecycle_state == QuoteLifecycleState.REJECTED:
        return {
            "quoteId": quote.quote_reference,
            "bookable": False,
            "status": _QUOTE_STATUS_REJECTED,
            "reason": _BOOKABILITY_REASON_APPROVAL_REJECTED,
            "expired": False,
            "validUntil": quote.valid_until.isoformat(),
        }

    if quote.lifecycle_state == QuoteLifecycleState.BOOKED:
        return {
            "quoteId": quote.quote_reference,
            "bookable": False,
            "status": _QUOTE_STATUS_BOOKED,
            "reason": _BOOKABILITY_REASON_ALREADY_BOOKED,
            "expired": False,
            "validUntil": quote.valid_until.isoformat(),
        }

    if quote.lifecycle_state == QuoteLifecycleState.VOID:
        return {
            "quoteId": quote.quote_reference,
            "bookable": False,
            "status": _QUOTE_STATUS_VOID,
            "reason": _BOOKABILITY_REASON_REVOKED,
            "expired": False,
            "validUntil": quote.valid_until.isoformat(),
        }

    expired = quote.lifecycle_state == QuoteLifecycleState.EXPIRED or _quote_is_expired(quote)
    return {
        "quoteId": quote.quote_reference,
        "bookable": not expired,
        "status": _QUOTE_STATUS_EXPIRED if expired else _QUOTE_STATUS_ACTIVE,
        "reason": _BOOKABILITY_REASON_EXPIRED if expired else _BOOKABILITY_REASON_OPEN,
        "expired": expired,
        "validUntil": quote.valid_until.isoformat(),
    }


def _serialize_quote_explainability(quote: Quote) -> dict[str, object]:
    payload = {
        "quoteId": quote.id,
        "quoteReference": quote.quote_reference,
        "pricingBasis": quote.pricing_basis.value,
        "marketSource": quote.market_source,
        "customerId": quote.customer_id,
        "accountId": quote.account_id,
        "contractId": quote.contract_id,
        "optimizationTrace": quote.optimization_trace,
        "pricingProvenance": quote.pricing_provenance,
    }

    if quote.repriced_from_quote_id is not None:
        payload["repricedFromQuoteId"] = quote.repriced_from_quote_id
        payload["repricingTrigger"] = quote.repricing_trigger
        payload["varianceSummary"] = quote.variance_summary

    return payload


def _build_bookability_snapshot(valid_until: datetime) -> dict[str, object]:
    return {
        "bookable": True,
        "status": _QUOTE_STATUS_ACTIVE,
        "reason": _BOOKABILITY_REASON_OPEN,
        "expired": False,
        "validUntil": valid_until.isoformat(),
    }


def _build_bookability_snapshot(valid_until: datetime) -> dict[str, object]:
    return {
        "bookable": True,
        "status": _QUOTE_STATUS_ACTIVE,
        "reason": _BOOKABILITY_REASON_OPEN,
        "expired": False,
        "validUntil": valid_until.isoformat(),
    }


def _quote_fx_snapshot(quote: Quote) -> dict[str, object]:
    if quote.fx_snapshot:
        return quote.fx_snapshot

    return {
        "provider": "legacy-identity-fx",
        "baseCurrency": quote.source_currency,
        "quoteCurrency": quote.currency,
        "rate": 1.0,
        "observedAt": quote.created_at.isoformat(),
        "referenceDataVersion": "legacy",
    }


def _quote_rounding_policy(quote: Quote) -> str:
    return quote.rounding_policy or _ROUNDING_POLICY


def _quote_source_total_amount(quote: Quote) -> float:
    source_total_amount = quote.pricing_provenance.get("sourceTotalAmount")
    if source_total_amount is not None:
        return float(source_total_amount)

    return _serialize_decimal(quote.total_amount)


def _sum_pricing_rule_amounts(rules: list[dict[str, object]]) -> Decimal:
    total = Decimal("0.00")
    for rule in rules:
        total += Decimal(str(rule.get("totalAmount", 0)))
    return total.quantize(_MONEY_PRECISION)


def _serialize_variance_amount(*, original: Decimal, repriced: Decimal) -> dict[str, object]:
    delta = (repriced - original).quantize(_MONEY_PRECISION)
    return {
        "original": _serialize_decimal(original),
        "repriced": _serialize_decimal(repriced),
        "delta": _serialize_decimal(delta),
        "changed": delta != Decimal("0.00"),
    }


def _extract_market_inputs(quote: Quote) -> dict[str, object]:
    base_rate_rules = quote.pricing_provenance.get("baseRateRules") or []
    market_rules = [rule for rule in base_rate_rules if isinstance(rule, dict) and rule.get("marketRateSnapshotId") is not None]

    def average(metric: str) -> float | None:
        values = [Decimal(str(rule[metric])) for rule in market_rules if rule.get(metric) is not None]
        if not values:
            return None
        return _serialize_decimal((sum(values, Decimal("0.00")) / Decimal(len(values))).quantize(_MONEY_PRECISION))

    return {
        "pricingBasis": quote.pricing_basis.value,
        "marketSource": quote.market_source or quote.pricing_provenance.get("marketSource"),
        "marketRateSnapshotIds": [rule["marketRateSnapshotId"] for rule in market_rules],
        "capacityPressureIndex": average("capacityPressureIndex"),
        "utilizationIndex": average("utilizationIndex"),
        "seasonalityIndex": average("seasonalityIndex"),
    }


def _extract_optimization_inputs(quote: Quote) -> dict[str, object]:
    trace = quote.optimization_trace or {}
    strategy = trace.get("strategy") if isinstance(trace.get("strategy"), dict) else None
    return {
        "pricingModeHint": quote.pricing_mode_hint or trace.get("pricingModeHint") or PricingModeHint.AUTO.value,
        "decision": trace.get("decision"),
        "selectedPricingBasis": trace.get("selectedPricingBasis"),
        "fallbackPricingBasis": trace.get("fallbackPricingBasis"),
        "strategyId": None if strategy is None else strategy.get("strategyId"),
        "strategyName": None if strategy is None else strategy.get("strategyName"),
        "strategyVersion": None if strategy is None else strategy.get("version"),
    }


def _build_quote_variance_summary(*, original_quote: Quote, repriced_quote: Quote) -> dict[str, object]:
    original_source_total = Decimal(str(_quote_source_total_amount(original_quote)))
    repriced_source_total = Decimal(str(_quote_source_total_amount(repriced_quote)))
    original_base_total = _sum_pricing_rule_amounts(original_quote.pricing_provenance.get("baseRateRules") or [])
    repriced_base_total = _sum_pricing_rule_amounts(repriced_quote.pricing_provenance.get("baseRateRules") or [])
    original_surcharge_total = _sum_pricing_rule_amounts(original_quote.pricing_provenance.get("appliedSurchargeRules") or [])
    repriced_surcharge_total = _sum_pricing_rule_amounts(repriced_quote.pricing_provenance.get("appliedSurchargeRules") or [])
    original_market_inputs = _extract_market_inputs(original_quote)
    repriced_market_inputs = _extract_market_inputs(repriced_quote)
    original_optimization_inputs = _extract_optimization_inputs(original_quote)
    repriced_optimization_inputs = _extract_optimization_inputs(repriced_quote)

    total_delta = (repriced_quote.total_amount - original_quote.total_amount).quantize(_MONEY_PRECISION)
    if total_delta > Decimal("0.00"):
        direction = "HIGHER"
    elif total_delta < Decimal("0.00"):
        direction = "LOWER"
    else:
        direction = "UNCHANGED"

    original_fx = _quote_fx_snapshot(original_quote)
    repriced_fx = _quote_fx_snapshot(repriced_quote)

    return {
        "direction": direction,
        "totalAmount": _serialize_variance_amount(original=original_quote.total_amount, repriced=repriced_quote.total_amount),
        "sourceTotalAmount": _serialize_variance_amount(original=original_source_total, repriced=repriced_source_total),
        "baseRate": _serialize_variance_amount(original=original_base_total, repriced=repriced_base_total),
        "surcharges": _serialize_variance_amount(original=original_surcharge_total, repriced=repriced_surcharge_total),
        "fx": {
            "changed": original_fx != repriced_fx,
            "original": original_fx,
            "repriced": repriced_fx,
        },
        "marketInputs": {
            "changed": original_market_inputs != repriced_market_inputs,
            "original": original_market_inputs,
            "repriced": repriced_market_inputs,
        },
        "optimizationInputs": {
            "changed": original_optimization_inputs != repriced_optimization_inputs,
            "original": original_optimization_inputs,
            "repriced": repriced_optimization_inputs,
        },
    }


def _resolve_fx_rate(*, db: Session, currency: str) -> ResolvedFxRate:
    fx_rate = db.scalar(
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == _SOURCE_CURRENCY,
            ExchangeRate.quote_currency == currency,
        )
        .order_by(ExchangeRate.observed_at.desc())
    )
    if fx_rate is None:
        raise HTTPException(status_code=400, detail=f"Unsupported currency: {currency}")

    return ResolvedFxRate(
        base_currency=fx_rate.base_currency,
        quote_currency=fx_rate.quote_currency,
        rate=fx_rate.rate,
        provider=fx_rate.provider,
        observed_at=_normalize_utc(fx_rate.observed_at),
        reference_data_version=fx_rate.reference_data_version,
    )


def _serialize_fx_snapshot(fx_rate: ResolvedFxRate) -> dict[str, object]:
    return {
        "provider": fx_rate.provider,
        "baseCurrency": fx_rate.base_currency,
        "quoteCurrency": fx_rate.quote_currency,
        "rate": _serialize_decimal(fx_rate.rate),
        "observedAt": fx_rate.observed_at.isoformat(),
        "referenceDataVersion": fx_rate.reference_data_version,
    }


def _convert_money(amount: Decimal, *, fx_rate: ResolvedFxRate) -> Decimal:
    return (amount * fx_rate.rate).quantize(_MONEY_PRECISION, rounding=ROUND_HALF_UP)


def _generate_quote_reference(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    issued_count = db.scalar(
        select(func.count()).select_from(Quote).where(Quote.quote_reference.like(f"QTE-{year}-%"))
    )
    return f"QTE-{year}-{int(issued_count or 0) + 1:05d}"


def _load_rate_table(
    *,
    db: Session,
    schedule: Schedule,
    equipment_types: set[EquipmentType],
) -> dict[EquipmentType, RateTable]:
    rates_by_type = _find_rate_coverage(
        db=db,
        origin_port=schedule.origin_port,
        destination_port=schedule.destination_port,
        departure_date=schedule.departure_date,
        equipment_types=equipment_types,
    )

    for equipment_type in equipment_types:
        if equipment_type not in rates_by_type:
            raise HTTPException(
                status_code=400,
                detail=f"No rate available for {equipment_type.value} on selected schedule",
            )

    return rates_by_type


def _find_rate_coverage(
    *,
    db: Session,
    origin_port: str,
    destination_port: str,
    departure_date: date,
    equipment_types: set[EquipmentType],
) -> dict[EquipmentType, RateTable]:
    rate_rows = db.scalars(
        select(RateTable).where(
            RateTable.origin_port == origin_port,
            RateTable.destination_port == destination_port,
            RateTable.equipment_type.in_(equipment_types),
            RateTable.is_active.is_(True),
            RateTable.valid_from <= departure_date,
            RateTable.valid_to >= departure_date,
        )
    ).all()
    rates_by_type: dict[EquipmentType, RateTable] = {}
    for row in rate_rows:
        current = rates_by_type.get(row.equipment_type)
        if current is None or row.version > current.version:
            rates_by_type[row.equipment_type] = row
    return rates_by_type


def _find_contracts(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    schedule: Schedule,
) -> list[Contract]:
    if payload.customer_id is None and payload.account_id is None:
        return []

    contracts = db.scalars(
        select(Contract).where(
            Contract.origin_port == schedule.origin_port,
            Contract.destination_port == schedule.destination_port,
            Contract.valid_from <= schedule.departure_date,
            Contract.valid_to >= schedule.departure_date,
        )
    ).all()

    matches: list[Contract] = []
    for contract in contracts:
        if contract.match_type == ContractMatchType.ACCOUNT:
            if payload.account_id is None or contract.account_id != payload.account_id:
                continue
            if payload.customer_id is not None and contract.customer_id is not None and contract.customer_id != payload.customer_id:
                continue
            matches.append(contract)
            continue

        if payload.customer_id is not None and contract.customer_id == payload.customer_id:
            matches.append(contract)

    return sorted(matches, key=lambda contract: 0 if contract.match_type == ContractMatchType.ACCOUNT else 1)


def _load_contract_rate_rules(db: Session, contract_id: str) -> dict[EquipmentType, ContractRateRule]:
    rate_rules = db.scalars(select(ContractRateRule).where(ContractRateRule.contract_id == contract_id)).all()
    return {row.equipment_type: row for row in rate_rules}


def _load_active_surcharge_rules(db: Session) -> list[SurchargeRule]:
    return db.scalars(select(SurchargeRule).where(SurchargeRule.is_active.is_(True))).all()


def _get_rate_table_or_404(rate_table_id: str, db: Session) -> RateTable:
    rate_table = db.scalar(select(RateTable).where(RateTable.id == rate_table_id))
    if rate_table is None:
        raise HTTPException(status_code=404, detail="Rate table not found")

    return rate_table


def _get_surcharge_rule_or_404(surcharge_rule_id: str, db: Session) -> SurchargeRule:
    surcharge_rule = db.scalar(select(SurchargeRule).where(SurchargeRule.id == surcharge_rule_id))
    if surcharge_rule is None:
        raise HTTPException(status_code=404, detail="Surcharge rule not found")

    return surcharge_rule


def _load_rate_tables_by_id(rate_table_ids: list[str], db: Session) -> list[RateTable]:
    if not rate_table_ids:
        return []

    rows = db.scalars(select(RateTable).where(RateTable.id.in_(rate_table_ids))).all()
    rows_by_id = {row.id: row for row in rows}
    missing_ids = [rate_table_id for rate_table_id in rate_table_ids if rate_table_id not in rows_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Rate table not found: {missing_ids[0]}")

    return [rows_by_id[rate_table_id] for rate_table_id in rate_table_ids]


def _load_surcharge_rules_by_id(surcharge_rule_ids: list[str], db: Session) -> list[SurchargeRule]:
    if not surcharge_rule_ids:
        return []

    rows = db.scalars(select(SurchargeRule).where(SurchargeRule.id.in_(surcharge_rule_ids))).all()
    rows_by_id = {row.id: row for row in rows}
    missing_ids = [surcharge_rule_id for surcharge_rule_id in surcharge_rule_ids if surcharge_rule_id not in rows_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Surcharge rule not found: {missing_ids[0]}")

    return [rows_by_id[surcharge_rule_id] for surcharge_rule_id in surcharge_rule_ids]


def _date_windows_overlap(
    start_a: date | None,
    end_a: date | None,
    start_b: date | None,
    end_b: date | None,
) -> bool:
    effective_start_a = date.min if start_a is None else start_a
    effective_end_a = date.max if end_a is None else end_a
    effective_start_b = date.min if start_b is None else start_b
    effective_end_b = date.max if end_b is None else end_b
    return effective_start_a <= effective_end_b and effective_start_b <= effective_end_a


def _next_rate_table_version(payload: AdminRateTableRequest, db: Session) -> int:
    latest_version = db.scalar(
        select(func.max(RateTable.version)).where(
            RateTable.origin_port == payload.origin_port,
            RateTable.destination_port == payload.destination_port,
            RateTable.equipment_type == payload.equipment_type,
        )
    )
    return int(latest_version or 0) + 1


def _next_surcharge_rule_version(payload: AdminSurchargeRuleRequest, db: Session) -> int:
    latest_version = db.scalar(
        select(func.max(SurchargeRule.version)).where(
            SurchargeRule.surcharge_type == payload.surcharge_type,
            SurchargeRule.port_code == payload.port_code,
            SurchargeRule.port_scope == payload.port_scope,
            SurchargeRule.weight_threshold_kg_per_teu == payload.weight_threshold_kg_per_teu,
        )
    )
    return int(latest_version or 0) + 1


def _ensure_rate_table_is_editable(rate_table: RateTable) -> None:
    if rate_table.is_active:
        raise HTTPException(status_code=409, detail="Active rate tables cannot be edited; create a new draft version")


def _ensure_surcharge_rule_is_editable(surcharge_rule: SurchargeRule) -> None:
    if surcharge_rule.is_active:
        raise HTTPException(status_code=409, detail="Active surcharge rules cannot be edited; create a new draft version")


def _serialize_rate_table(rate_table: RateTable) -> dict[str, object]:
    return {
        "id": rate_table.id,
        "originPort": rate_table.origin_port,
        "destinationPort": rate_table.destination_port,
        "equipmentType": rate_table.equipment_type.value,
        "baseRateUsd": _serialize_decimal(rate_table.base_rate_usd),
        "validFrom": rate_table.valid_from.isoformat(),
        "validTo": rate_table.valid_to.isoformat(),
        "version": rate_table.version,
        "isActive": rate_table.is_active,
        "createdBy": rate_table.created_by,
        "updatedBy": rate_table.updated_by,
        "activatedBy": rate_table.activated_by,
        "createdAt": rate_table.created_at.isoformat(),
        "updatedAt": rate_table.updated_at.isoformat(),
        "activatedAt": _serialize_optional_datetime(rate_table.activated_at),
    }


def _serialize_surcharge_rule(surcharge_rule: SurchargeRule) -> dict[str, object]:
    return {
        "id": surcharge_rule.id,
        "surchargeType": surcharge_rule.surcharge_type.value,
        "description": surcharge_rule.description,
        "amountUsd": _serialize_decimal(surcharge_rule.amount_usd),
        "currency": surcharge_rule.currency,
        "portCode": surcharge_rule.port_code,
        "portScope": None if surcharge_rule.port_scope is None else surcharge_rule.port_scope.value,
        "weightThresholdKgPerTeu": _serialize_optional_decimal(surcharge_rule.weight_threshold_kg_per_teu),
        "validFrom": _serialize_optional_date(surcharge_rule.valid_from),
        "validTo": _serialize_optional_date(surcharge_rule.valid_to),
        "version": surcharge_rule.version,
        "isActive": surcharge_rule.is_active,
        "createdBy": surcharge_rule.created_by,
        "updatedBy": surcharge_rule.updated_by,
        "activatedBy": surcharge_rule.activated_by,
        "createdAt": surcharge_rule.created_at.isoformat(),
        "updatedAt": surcharge_rule.updated_at.isoformat(),
        "activatedAt": _serialize_optional_datetime(surcharge_rule.activated_at),
    }


def _serialize_commercial_change_event(event: CommercialChangeEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "resourceType": event.resource_type.value,
        "resourceId": event.resource_id,
        "action": event.action.value,
        "actor": event.actor,
        "resourceVersion": event.resource_version,
        "snapshot": event.snapshot,
        "occurredAt": event.occurred_at.isoformat(),
    }


def _record_commercial_change(
    db: Session,
    *,
    resource_type: CommercialChangeResourceType,
    resource_id: str,
    action: CommercialChangeAction,
    actor: str,
    resource_version: int,
    snapshot: dict[str, object],
    occurred_at: datetime,
) -> None:
    db.add(
        CommercialChangeEvent(
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            actor=actor,
            resource_version=resource_version,
            snapshot=snapshot,
            occurred_at=occurred_at,
        )
    )
    aggregate_type, event_type = _commercial_change_event_contract(resource_type)
    db.add(
        OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=resource_id,
            event_type=event_type,
            event_version=_OUTBOX_EVENT_VERSION,
            payload=_build_commercial_change_event_payload(
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                actor=actor,
                resource_version=resource_version,
                snapshot=snapshot,
                occurred_at=occurred_at,
            ),
            occurred_at=occurred_at,
        )
    )


def _quote_lifecycle_state_for_reporting(quote: Quote) -> QuoteLifecycleState:
    if quote.lifecycle_state in {
        QuoteLifecycleState.ISSUED,
        QuoteLifecycleState.PENDING_APPROVAL,
        QuoteLifecycleState.APPROVED,
    } and _quote_is_expired(quote):
        return QuoteLifecycleState.EXPIRED

    return quote.lifecycle_state


def _serialize_impacted_quote(quote: Quote) -> dict[str, object]:
    lifecycle_state = _quote_lifecycle_state_for_reporting(quote)
    bookable = lifecycle_state in {QuoteLifecycleState.ISSUED, QuoteLifecycleState.APPROVED} and not _quote_is_expired(quote)
    return {
        "quoteId": quote.id,
        "quoteReference": quote.quote_reference,
        "lifecycleState": lifecycle_state.value,
        "bookable": bookable,
        "scheduleId": quote.schedule_id,
        "contractId": quote.contract_id,
        "pricingBasis": quote.pricing_basis.value,
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def _build_impact_summary(payload: ImpactAnalysisRequest, quotes: list[Quote]) -> dict[str, object]:
    target_id = payload.schedule_id if payload.change_type == ImpactAnalysisChangeType.SCHEDULE else payload.contract_id
    affected_quotes = [_serialize_impacted_quote(quote) for quote in quotes]
    return {
        "changeType": payload.change_type.value,
        "targetId": target_id,
        "affectedCount": len(affected_quotes),
        "affectedQuotes": affected_quotes,
    }


def _build_market_approval_reasons(pricing: ResolvedPricing) -> list[dict[str, object]]:
    if pricing.pricing_basis != PricingBasis.MARKET:
        return []

    reasons: list[dict[str, object]] = []
    for equipment_type, snapshot in pricing.rates_by_type.items():
        metrics = [
            (
                "MARKET_CAPACITY_PRESSURE_THRESHOLD_EXCEEDED",
                float(snapshot.capacity_pressure_index),
                _MARKET_APPROVAL_CAPACITY_PRESSURE_THRESHOLD,
                "capacityPressureIndex",
            ),
            (
                "MARKET_UTILIZATION_THRESHOLD_EXCEEDED",
                float(snapshot.utilization_index),
                _MARKET_APPROVAL_UTILIZATION_THRESHOLD,
                "utilizationIndex",
            ),
            (
                "MARKET_SEASONALITY_THRESHOLD_EXCEEDED",
                float(snapshot.seasonality_index),
                _MARKET_APPROVAL_SEASONALITY_THRESHOLD,
                "seasonalityIndex",
            ),
        ]
        for code, observed_value, threshold, metric in metrics:
            if observed_value < threshold:
                continue
            reasons.append(
                {
                    "code": code,
                    "message": f"{metric} exceeded the approval threshold for {equipment_type.value}",
                    "equipmentType": equipment_type.value,
                    "marketRateSnapshotId": snapshot.id,
                    "metric": metric,
                    "observedValue": observed_value,
                    "threshold": threshold,
                }
            )

    return reasons


def _deactivate_superseded_rate_tables(rate_table: RateTable, *, actor: str, changed_at: datetime, db: Session) -> None:
    active_candidates = db.scalars(
        select(RateTable).where(
            RateTable.id != rate_table.id,
            RateTable.is_active.is_(True),
            RateTable.origin_port == rate_table.origin_port,
            RateTable.destination_port == rate_table.destination_port,
            RateTable.equipment_type == rate_table.equipment_type,
        )
    ).all()
    for candidate in active_candidates:
        if not _date_windows_overlap(rate_table.valid_from, rate_table.valid_to, candidate.valid_from, candidate.valid_to):
            continue
        candidate.is_active = False
        candidate.updated_by = actor
        candidate.updated_at = changed_at


def _deactivate_superseded_surcharge_rules(
    surcharge_rule: SurchargeRule,
    *,
    actor: str,
    changed_at: datetime,
    db: Session,
) -> None:
    active_candidates = db.scalars(
        select(SurchargeRule).where(
            SurchargeRule.id != surcharge_rule.id,
            SurchargeRule.is_active.is_(True),
            SurchargeRule.surcharge_type == surcharge_rule.surcharge_type,
            SurchargeRule.port_code == surcharge_rule.port_code,
            SurchargeRule.port_scope == surcharge_rule.port_scope,
            SurchargeRule.weight_threshold_kg_per_teu == surcharge_rule.weight_threshold_kg_per_teu,
        )
    ).all()
    for candidate in active_candidates:
        if not _date_windows_overlap(surcharge_rule.valid_from, surcharge_rule.valid_to, candidate.valid_from, candidate.valid_to):
            continue
        candidate.is_active = False
        candidate.updated_by = actor
        candidate.updated_at = changed_at


def _apply_preview_rate_tables(
    *,
    rates_by_type: dict[EquipmentType, RateTable],
    schedule: Schedule,
    preview_rate_tables: list[RateTable],
) -> dict[EquipmentType, RateTable]:
    preview_rates = dict(rates_by_type)
    for rate_table in preview_rate_tables:
        if rate_table.origin_port != schedule.origin_port or rate_table.destination_port != schedule.destination_port:
            raise HTTPException(status_code=400, detail=f"Preview rate table {rate_table.id} does not match the selected schedule route")
        if rate_table.valid_from > schedule.departure_date or rate_table.valid_to < schedule.departure_date:
            raise HTTPException(status_code=400, detail=f"Preview rate table {rate_table.id} is not effective for the selected departure date")
        preview_rates[rate_table.equipment_type] = rate_table

    return preview_rates


def _apply_preview_surcharge_rules(
    *,
    active_surcharge_rules: list[SurchargeRule],
    preview_surcharge_rules: list[SurchargeRule],
) -> list[SurchargeRule]:
    if not preview_surcharge_rules:
        return active_surcharge_rules

    preview_rule_ids = {rule.id for rule in preview_surcharge_rules}
    return [rule for rule in active_surcharge_rules if rule.id not in preview_rule_ids] + preview_surcharge_rules


def _waive_surcharges(
    surcharge_line_items: list[SurchargeLineItem],
    waived_surcharge_types: list[str],
) -> list[SurchargeLineItem]:
    waived_types = {SurchargeType(value) for value in waived_surcharge_types}
    return [item for item in surcharge_line_items if item.rule.surcharge_type not in waived_types]


def _resolve_contract_pricing(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    schedule: Schedule,
    public_surcharge_line_items: list[SurchargeLineItem],
) -> ResolvedPricing | None:
    for contract in _find_contracts(db=db, payload=payload, schedule=schedule):
        contract_rates_by_type = _load_contract_rate_rules(db, contract.id)
        if any(item.type not in contract_rates_by_type for item in payload.equipment):
            continue

        return ResolvedPricing(
            pricing_basis=PricingBasis.CONTRACT,
            rates_by_type=contract_rates_by_type,
            surcharge_line_items=_waive_surcharges(public_surcharge_line_items, contract.waived_surcharge_types),
            contract=contract,
            market_signals={},
        )

    return None


def _build_pricing_candidates(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    schedule: Schedule,
    public_rates_by_type: dict[EquipmentType, RateTable],
    surcharge_rules: list[SurchargeRule],
) -> dict[PricingBasis, ResolvedPricing]:
    public_surcharge_line_items = calculate_surcharges(
        equipment=[EquipmentSelection(equipment_type=item.type, quantity=item.quantity) for item in payload.equipment],
        cargo_weight_kg=payload.cargo_weight_kg,
        shipment_date=schedule.departure_date,
        origin_port=schedule.origin_port,
        destination_port=schedule.destination_port,
        surcharge_rules=surcharge_rules,
    )

    pricing_candidates: dict[PricingBasis, ResolvedPricing] = {
        PricingBasis.PUBLIC_TARIFF: ResolvedPricing(
            pricing_basis=PricingBasis.PUBLIC_TARIFF,
            rates_by_type=public_rates_by_type,
            surcharge_line_items=public_surcharge_line_items,
        )
    }

    contract_pricing = _resolve_contract_pricing(
        db=db,
        payload=payload,
        schedule=schedule,
        public_surcharge_line_items=public_surcharge_line_items,
    )
    if contract_pricing is not None:
        pricing_candidates[PricingBasis.CONTRACT] = contract_pricing

    market_rates_by_type = _load_market_rate_snapshots(
        db=db,
        schedule=schedule,
        equipment_types={item.type for item in payload.equipment},
    )
    if all(item.type in market_rates_by_type for item in payload.equipment):
        pricing_candidates[PricingBasis.MARKET] = ResolvedPricing(
            pricing_basis=PricingBasis.MARKET,
            rates_by_type=market_rates_by_type,
            surcharge_line_items=public_surcharge_line_items,
            market_source=next(iter(market_rates_by_type.values())).source_name,
            market_signals=_market_signal_metrics(market_rates_by_type),
        )

    return pricing_candidates


def _select_pricing(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    pricing_candidates: dict[PricingBasis, ResolvedPricing],
) -> ResolvedPricing:
    public_pricing = pricing_candidates[PricingBasis.PUBLIC_TARIFF]
    contract_pricing = pricing_candidates.get(PricingBasis.CONTRACT)
    market_pricing = pricing_candidates.get(PricingBasis.MARKET)
    default_fallback = contract_pricing or public_pricing
    hint = payload.pricing_mode_hint or PricingModeHint.AUTO
    has_full_market_coverage = market_pricing is not None
    strategy = _load_active_pricing_strategy(db)
    metrics = _market_signal_metrics({} if market_pricing is None else market_pricing.rates_by_type)
    rule_decisions, strategy_selected_market = _strategy_rule_decisions(strategy, metrics)

    trace = {
        "pricingModeHint": hint.value,
        "fallbackPricingBasis": default_fallback.pricing_basis.value,
        "marketAvailable": has_full_market_coverage,
        "marketSignals": metrics,
        "strategy": None
        if strategy is None
        else {
            "strategyId": strategy.id,
            "strategyName": strategy.strategy_name,
            "version": strategy.version,
            "selectionMode": strategy.rules.get("selectionMode", "ANY_SIGNAL"),
            "rules": rule_decisions,
        },
    }

    def with_trace(pricing: ResolvedPricing, *, decision: str, include_trace: bool) -> ResolvedPricing:
        return ResolvedPricing(
            pricing_basis=pricing.pricing_basis,
            rates_by_type=pricing.rates_by_type,
            surcharge_line_items=pricing.surcharge_line_items,
            contract=pricing.contract,
            market_source=pricing.market_source,
            market_signals=pricing.market_signals,
            optimization_trace={}
            if not include_trace
            else {**trace, "decision": decision, "selectedPricingBasis": pricing.pricing_basis.value},
        )

    if hint == PricingModeHint.PUBLIC_TARIFF:
        return with_trace(public_pricing, decision="CLIENT_HINT_PUBLIC_TARIFF", include_trace=True)

    if hint == PricingModeHint.CONTRACT:
        if contract_pricing is not None:
            return with_trace(contract_pricing, decision="CLIENT_HINT_CONTRACT", include_trace=True)
        return with_trace(public_pricing, decision="CLIENT_HINT_CONTRACT_FALLBACK_PUBLIC_TARIFF", include_trace=True)

    if not has_full_market_coverage:
        return with_trace(default_fallback, decision="MARKET_UNAVAILABLE_FALLBACK", include_trace=hint == PricingModeHint.MARKET)

    assert market_pricing is not None
    if hint == PricingModeHint.MARKET:
        return with_trace(market_pricing, decision="CLIENT_HINT_MARKET", include_trace=True)

    if strategy_selected_market:
        return with_trace(market_pricing, decision="STRATEGY_SELECTED_MARKET", include_trace=True)

    return with_trace(default_fallback, decision="STRATEGY_FALLBACK", include_trace=False)


def _load_market_rate_snapshots(
    *,
    db: Session,
    schedule: Schedule,
    equipment_types: set[EquipmentType],
) -> dict[EquipmentType, MarketRateSnapshot]:
    rows = db.scalars(
        select(MarketRateSnapshot).where(
            MarketRateSnapshot.origin_port == schedule.origin_port,
            MarketRateSnapshot.destination_port == schedule.destination_port,
            MarketRateSnapshot.equipment_type.in_(equipment_types),
            MarketRateSnapshot.valid_from <= schedule.departure_date,
            MarketRateSnapshot.valid_to >= schedule.departure_date,
        )
    ).all()
    return {row.equipment_type: row for row in rows}


def _load_active_pricing_strategy(db: Session) -> PricingStrategyVersion | None:
    return db.scalar(
        select(PricingStrategyVersion)
        .where(PricingStrategyVersion.is_active.is_(True))
        .order_by(PricingStrategyVersion.version.desc(), PricingStrategyVersion.activated_at.desc())
    )


def _market_signal_metrics(market_rates_by_type: dict[EquipmentType, MarketRateSnapshot]) -> dict[str, float]:
    snapshots = list(market_rates_by_type.values())
    if not snapshots:
        return {
            "capacityPressureIndex": 0.0,
            "utilizationIndex": 0.0,
            "seasonalityIndex": 0.0,
        }

    divisor = float(len(snapshots))
    return {
        "capacityPressureIndex": sum(float(snapshot.capacity_pressure_index) for snapshot in snapshots) / divisor,
        "utilizationIndex": sum(float(snapshot.utilization_index) for snapshot in snapshots) / divisor,
        "seasonalityIndex": sum(float(snapshot.seasonality_index) for snapshot in snapshots) / divisor,
    }


def _strategy_rule_decisions(
    strategy: PricingStrategyVersion | None,
    metrics: dict[str, float],
) -> tuple[list[dict[str, object]], bool]:
    if strategy is None:
        return [], False

    rules = strategy.rules or {}
    decisions = [
        {
            "rule": "capacity-pressure",
            "metric": metrics["capacityPressureIndex"],
            "threshold": float(rules.get("capacityPressureThreshold", 1.0)),
            "matched": metrics["capacityPressureIndex"] >= float(rules.get("capacityPressureThreshold", 1.0)),
        },
        {
            "rule": "utilization",
            "metric": metrics["utilizationIndex"],
            "threshold": float(rules.get("utilizationThreshold", 1.0)),
            "matched": metrics["utilizationIndex"] >= float(rules.get("utilizationThreshold", 1.0)),
        },
        {
            "rule": "seasonality",
            "metric": metrics["seasonalityIndex"],
            "threshold": float(rules.get("seasonalityThreshold", 1.0)),
            "matched": metrics["seasonalityIndex"] >= float(rules.get("seasonalityThreshold", 1.0)),
        },
    ]
    return decisions, any(decision["matched"] for decision in decisions)


def _resolve_pricing(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    schedule: Schedule,
    public_rates_by_type: dict[EquipmentType, RateTable],
    surcharge_rules: list[SurchargeRule],
) -> ResolvedPricing:
    pricing_candidates = _build_pricing_candidates(
        db=db,
        payload=payload,
        schedule=schedule,
        public_rates_by_type=public_rates_by_type,
        surcharge_rules=surcharge_rules,
    )
    return _select_pricing(db=db, payload=payload, pricing_candidates=pricing_candidates)


def _validity_policy_market_specificity(policy: QuoteValidityPolicy) -> int:
    return sum(
        threshold is not None
        for threshold in (
            policy.min_capacity_pressure_index,
            policy.min_utilization_index,
            policy.min_seasonality_index,
        )
    )


def _validity_policy_sort_key(policy: QuoteValidityPolicy) -> tuple[int, int, int, int, int, int, str]:
    return (
        1 if policy.contract_id is not None else 0,
        1 if policy.account_id is not None else 0,
        1 if policy.customer_id is not None else 0,
        1 if policy.pricing_basis is not None else 0,
        _validity_policy_market_specificity(policy),
        policy.priority,
        policy.id,
    )


def _validity_policy_matches(
    policy: QuoteValidityPolicy,
    *,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
) -> bool:
    if policy.customer_id is not None and policy.customer_id != payload.customer_id:
        return False
    if policy.account_id is not None and policy.account_id != payload.account_id:
        return False
    if policy.contract_id is not None and policy.contract_id != (None if pricing.contract is None else pricing.contract.id):
        return False
    if policy.pricing_basis is not None and policy.pricing_basis != pricing.pricing_basis:
        return False

    capacity_pressure_index = pricing.market_signals.get("capacityPressureIndex", 0.0)
    utilization_index = pricing.market_signals.get("utilizationIndex", 0.0)
    seasonality_index = pricing.market_signals.get("seasonalityIndex", 0.0)

    if policy.min_capacity_pressure_index is not None and capacity_pressure_index < float(policy.min_capacity_pressure_index):
        return False
    if policy.min_utilization_index is not None and utilization_index < float(policy.min_utilization_index):
        return False
    if policy.min_seasonality_index is not None and seasonality_index < float(policy.min_seasonality_index):
        return False

    return True


def _resolve_quote_validity(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
    created_at: datetime,
) -> ResolvedQuoteValidity:
    policies = db.scalars(
        select(QuoteValidityPolicy)
        .where(QuoteValidityPolicy.is_active.is_(True))
        .order_by(QuoteValidityPolicy.priority.desc(), QuoteValidityPolicy.id.asc())
    ).all()
    matched_policies = [policy for policy in policies if _validity_policy_matches(policy, payload=payload, pricing=pricing)]
    if not matched_policies:
        raise HTTPException(status_code=500, detail="No quote validity policy available")
    selected_policy = max(matched_policies, key=_validity_policy_sort_key)

    return ResolvedQuoteValidity(
        valid_until=created_at + timedelta(hours=selected_policy.validity_hours),
        snapshot={
            "policyId": selected_policy.id,
            "policyName": selected_policy.policy_name,
            "validityHours": selected_policy.validity_hours,
            "matchedOn": {
                "customerId": payload.customer_id if selected_policy.customer_id is not None else None,
                "accountId": payload.account_id if selected_policy.account_id is not None else None,
                "contractId": None if selected_policy.contract_id is None or pricing.contract is None else pricing.contract.id,
                "pricingBasis": pricing.pricing_basis.value if selected_policy.pricing_basis is not None else None,
                "marketSignals": None
                if _validity_policy_market_specificity(selected_policy) == 0
                else pricing.market_signals,
            },
            "selectionContext": {
                "customerId": payload.customer_id,
                "accountId": payload.account_id,
                "contractId": None if pricing.contract is None else pricing.contract.id,
                "pricingBasis": pricing.pricing_basis.value,
                "marketSignals": pricing.market_signals,
            },
        },
    )


def _serialize_rate_coverage(
    payload: ValidateRateCoverageRequest,
    rates_by_type: dict[EquipmentType, RateTable],
) -> dict[str, object]:
    coverage = []
    uncovered_equipment = []
    for item in payload.equipment:
        rate = rates_by_type.get(item.type)
        covered = rate is not None
        if not covered and item.type.value not in uncovered_equipment:
            uncovered_equipment.append(item.type.value)

        coverage.append(
            {
                "equipmentType": item.type.value,
                "quantity": item.quantity,
                "covered": covered,
                "rateTableId": None if rate is None else rate.id,
                "validFrom": None if rate is None else rate.valid_from.isoformat(),
                "validTo": None if rate is None else rate.valid_to.isoformat(),
            }
        )

    covered = not uncovered_equipment
    return {
        "covered": covered,
        "reason": "RATE_AVAILABLE" if covered else "RATE_MISSING",
        "pricingBasis": PricingBasis.PUBLIC_TARIFF.value,
        "referenceDataVersion": REFERENCE_DATA_VERSION,
        "route": {
            "originPort": payload.origin_port,
            "destinationPort": payload.destination_port,
            "departureDate": payload.departure_date.isoformat(),
        },
        "coverage": coverage,
        "uncoveredEquipment": uncovered_equipment,
    }


def _availability_by_type(payload: PlanEquipmentAvailabilityRequest) -> dict[EquipmentType, int]:
    availability: dict[EquipmentType, int] = {}
    for item in payload.availability:
        if payload.depot_code is not None and item.depot_code != payload.depot_code:
            continue
        availability[item.equipment_type] = availability.get(item.equipment_type, 0) + item.available_count

    return availability


def _plan_equipment_availability(payload: PlanEquipmentAvailabilityRequest) -> dict[str, object]:
    availability = _availability_by_type(payload)
    remaining_availability = dict(availability)
    equipment_rows: list[dict[str, object]] = []
    shortages: list[dict[str, object]] = []

    for item in payload.equipment:
        available_count = remaining_availability.get(item.type, 0)
        direct_covered_quantity = min(item.quantity, available_count)
        shortage_quantity = item.quantity - direct_covered_quantity
        remaining_availability[item.type] = available_count - direct_covered_quantity

        if shortage_quantity > 0:
            shortages.append({"type": item.type, "quantity": shortage_quantity})

        equipment_rows.append(
            {
                "type": item.type.value,
                "requestedQuantity": item.quantity,
                "availableCount": available_count,
                "directCoveredQuantity": direct_covered_quantity,
                "shortageQuantity": shortage_quantity,
                "status": _EQUIPMENT_AVAILABILITY_STATUS_SHORTAGE
                if shortage_quantity > 0
                else _EQUIPMENT_AVAILABILITY_STATUS_AVAILABLE,
            }
        )

    substitutions: list[dict[str, object]] = []
    uncovered_equipment: list[dict[str, object]] = []
    for shortage in shortages:
        requested_type = shortage["type"]
        remaining_shortage = int(shortage["quantity"])
        policies = sorted(
            (
                policy
                for policy in payload.substitutions
                if policy.active and policy.requested_type == requested_type
            ),
            key=lambda policy: (policy.priority, policy.substitute_type.value),
        )

        for policy in policies:
            if remaining_shortage <= 0:
                break

            available_count = remaining_availability.get(policy.substitute_type, 0)
            if available_count <= 0:
                continue

            quantity_covered = min(remaining_shortage, available_count)
            remaining_availability[policy.substitute_type] = available_count - quantity_covered
            remaining_shortage -= quantity_covered
            substitutions.append(
                {
                    "requestedType": requested_type.value,
                    "substituteType": policy.substitute_type.value,
                    "priority": policy.priority,
                    "reason": policy.reason,
                    "availableCount": available_count,
                    "quantityCovered": quantity_covered,
                }
            )

        if remaining_shortage > 0:
            uncovered_equipment.append(
                {
                    "type": requested_type.value,
                    "shortageQuantity": remaining_shortage,
                }
            )

    has_direct_shortage = any(row["shortageQuantity"] > 0 for row in equipment_rows)
    if uncovered_equipment:
        status = _EQUIPMENT_AVAILABILITY_STATUS_SHORTAGE
    elif has_direct_shortage:
        status = _EQUIPMENT_AVAILABILITY_STATUS_AVAILABLE_WITH_SUBSTITUTIONS
    else:
        status = _EQUIPMENT_AVAILABILITY_STATUS_AVAILABLE

    return {
        "status": status,
        "available": status != _EQUIPMENT_AVAILABILITY_STATUS_SHORTAGE,
        "depotCode": payload.depot_code,
        "equipment": equipment_rows,
        "substitutions": substitutions,
        "uncoveredEquipment": uncovered_equipment,
    }


def _build_pricing_provenance(
    *,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
    surcharge_line_items: list[SurchargeLineItem],
    source_total_amount: Decimal,
    fx_rate: ResolvedFxRate,
    quote_validity: ResolvedQuoteValidity,
) -> dict[str, object]:
    base_rate_rules: list[dict[str, object]] = []
    for item in payload.equipment:
        rate = pricing.rates_by_type[item.type]
        rate_rule = {
            "equipmentType": item.type.value,
            "quantity": item.quantity,
            "currency": "USD",
            "unitAmount": _serialize_decimal(rate.base_rate_usd if hasattr(rate, "base_rate_usd") else rate.rate_usd),
            "totalAmount": _serialize_decimal(
                ((rate.base_rate_usd if hasattr(rate, "base_rate_usd") else rate.rate_usd) * item.quantity).quantize(_MONEY_PRECISION)
            ),
        }
        if pricing.pricing_basis == PricingBasis.MARKET:
            rate_rule.update(
                {
                    "marketRateSnapshotId": rate.id,
                    "marketSource": rate.source_name,
                    "sourceReference": rate.source_reference,
                    "capturedAt": _normalize_utc(rate.captured_at).isoformat(),
                    "approvedAt": _normalize_utc(rate.approved_at).isoformat(),
                    "capacityPressureIndex": _serialize_decimal(rate.capacity_pressure_index),
                    "utilizationIndex": _serialize_decimal(rate.utilization_index),
                    "seasonalityIndex": _serialize_decimal(rate.seasonality_index),
                    "validFrom": rate.valid_from.isoformat(),
                    "validTo": rate.valid_to.isoformat(),
                }
            )
        else:
            rate_rule.update(
                {
                    "rateTableId": rate.id,
                    "rateVersion": None if pricing.contract is not None else rate.version,
                    "validFrom": None if pricing.contract is None else pricing.contract.valid_from.isoformat(),
                    "validTo": None if pricing.contract is None else pricing.contract.valid_to.isoformat(),
                }
            )
        base_rate_rules.append(rate_rule)

    provenance: dict[str, object] = {
        "pricingBasis": pricing.pricing_basis.value,
        "referenceDataVersion": REFERENCE_DATA_VERSION,
        "sourceCurrency": _SOURCE_CURRENCY,
        "responseCurrency": payload.currency,
        "sourceTotalAmount": _serialize_decimal(source_total_amount),
        "currencyConversion": {
            **_serialize_fx_snapshot(fx_rate),
            "roundingPolicy": _ROUNDING_POLICY,
            "conversionLevel": "LINE_ITEM",
        },
        "baseRateRules": base_rate_rules,
        "appliedSurchargeRules": [
            {
                "surchargeRuleId": item.rule.id,
                "surchargeType": item.rule.surcharge_type.value,
                "description": item.rule.description,
                "currency": item.rule.currency,
                "unitAmount": _serialize_decimal(item.rule.amount_usd),
                "totalAmount": _serialize_decimal(item.amount),
                "surchargeRuleVersion": item.rule.version,
                "portCode": item.rule.port_code,
                "portScope": item.rule.port_scope.value if item.rule.port_scope is not None else None,
                "weightThresholdKgPerTeu": _serialize_optional_decimal(item.rule.weight_threshold_kg_per_teu),
                "validFrom": _serialize_optional_date(item.rule.valid_from),
                "validTo": _serialize_optional_date(item.rule.valid_to),
            }
            for item in surcharge_line_items
        ],
        "validityPolicy": quote_validity.snapshot,
    }

    if pricing.optimization_trace:
        provenance["optimizationTrace"] = pricing.optimization_trace

    if pricing.market_source is not None:
        provenance["marketSource"] = pricing.market_source

    if pricing.contract is None and pricing.pricing_basis != PricingBasis.MARKET:
        for rate_rule in provenance["baseRateRules"]:
            equipment_type = EquipmentType(rate_rule["equipmentType"])
            rate = pricing.rates_by_type[equipment_type]
            rate_rule["validFrom"] = rate.valid_from.isoformat()
            rate_rule["validTo"] = rate.valid_to.isoformat()
        return provenance

    if pricing.pricing_basis == PricingBasis.MARKET:
        return provenance

    provenance["customerContext"] = {
        "customerId": payload.customer_id,
        "accountId": payload.account_id,
    }
    provenance["contract"] = {
        "contractId": pricing.contract.id,
        "matchType": pricing.contract.match_type.value,
        "waivedSurchargeTypes": pricing.contract.waived_surcharge_types,
    }
    return provenance


def _build_source_quote_line_items(
    *,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
) -> tuple[list[dict[str, object]], list[SurchargeLineItem], Decimal]:
    base_line_items: list[dict[str, object]] = []
    base_total = Decimal("0.00")
    for item in payload.equipment:
        rate = pricing.rates_by_type[item.type]
        unit_rate = rate.base_rate_usd if hasattr(rate, "base_rate_usd") else rate.rate_usd
        amount = (unit_rate * item.quantity).quantize(_MONEY_PRECISION)
        base_total += amount
        base_line_items.append(
            {
                "description": f"Ocean Freight - {item.type.value} x {item.quantity}",
                "amount": float(amount),
            }
        )

    surcharge_line_items = pricing.surcharge_line_items
    line_items = base_line_items + [item.as_dict() for item in surcharge_line_items]
    total_amount = (base_total + total_surcharges(surcharge_line_items)).quantize(_MONEY_PRECISION)
    return line_items, surcharge_line_items, total_amount


def _convert_quote_line_items(
    source_line_items: list[dict[str, object]],
    *,
    fx_rate: ResolvedFxRate,
) -> tuple[list[dict[str, object]], Decimal]:
    converted_line_items: list[dict[str, object]] = []
    converted_total = Decimal("0.00")
    for item in source_line_items:
        converted_amount = _convert_money(Decimal(str(item["amount"])), fx_rate=fx_rate)
        converted_total += converted_amount
        converted_line_items.append(
            {
                "description": item["description"],
                "amount": float(converted_amount),
            }
        )

    return converted_line_items, converted_total.quantize(_MONEY_PRECISION)


def _build_quote_payload_from_stored_quote(quote: Quote) -> CreateQuoteRequest:
    return CreateQuoteRequest.model_validate(
        {
            "scheduleId": quote.schedule_id,
            "equipment": quote.equipment,
            "cargoWeightKg": quote.cargo_weight_kg,
            "customerId": quote.customer_id,
            "accountId": quote.account_id,
            "currency": quote.currency,
            "pricingModeHint": quote.pricing_mode_hint,
        }
    )


def _serialize_quote_option(
    *,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
    fx_rate: ResolvedFxRate,
    quote_validity: ResolvedQuoteValidity,
) -> tuple[dict[str, object], Decimal]:
    source_line_items, surcharge_line_items, source_total_amount = _build_source_quote_line_items(
        payload=payload,
        pricing=pricing,
    )
    line_items, total_amount = _convert_quote_line_items(source_line_items, fx_rate=fx_rate)
    option = {
        "pricingBasis": pricing.pricing_basis.value,
        "currency": payload.currency,
        "sourceCurrency": _SOURCE_CURRENCY,
        "responseCurrency": payload.currency,
        "fx": _serialize_fx_snapshot(fx_rate),
        "roundingPolicy": _ROUNDING_POLICY,
        "pricingProvenance": _build_pricing_provenance(
            payload=payload,
            pricing=pricing,
            surcharge_line_items=surcharge_line_items,
            source_total_amount=source_total_amount,
            fx_rate=fx_rate,
            quote_validity=quote_validity,
        ),
        "lineItems": line_items,
        "sourceTotalAmount": _serialize_decimal(source_total_amount),
        "totalAmount": _serialize_decimal(total_amount),
        "bookability": _build_bookability_snapshot(quote_validity.valid_until),
    }
    if pricing.contract is not None:
        option["contractId"] = pricing.contract.id
    if pricing.market_source is not None:
        option["marketSource"] = pricing.market_source
    return option, source_total_amount


def _serialize_quote_options(
    *,
    payload: CreateQuoteRequest,
    pricing_candidates: dict[PricingBasis, ResolvedPricing],
    primary_pricing: ResolvedPricing,
    fx_rate: ResolvedFxRate,
    quote_validities: dict[PricingBasis, ResolvedQuoteValidity],
    max_alternative_options: int | None,
) -> dict[str, object]:
    primary_option, _ = _serialize_quote_option(
        payload=payload,
        pricing=primary_pricing,
        fx_rate=fx_rate,
        quote_validity=quote_validities[primary_pricing.pricing_basis],
    )
    alternatives: list[tuple[dict[str, object], Decimal]] = []
    for pricing_basis, pricing in pricing_candidates.items():
        if pricing_basis == primary_pricing.pricing_basis:
            continue

        alternatives.append(
            _serialize_quote_option(
                payload=payload,
                pricing=pricing,
                fx_rate=fx_rate,
                quote_validity=quote_validities[pricing_basis],
            )
        )

    ordered_alternatives = [
        option
        for option, _ in sorted(
            alternatives,
            key=lambda item: (
                item[1],
                _ALTERNATIVE_PRICING_ORDER[PricingBasis(item[0]["pricingBasis"])],
            ),
        )
    ]
    if max_alternative_options is not None:
        ordered_alternatives = ordered_alternatives[:max_alternative_options]

    return {
        "primary": primary_option,
        "alternatives": ordered_alternatives,
    }


def _create_quote_record(
    *,
    payload: CreateQuoteRequest,
    db: Session,
    schedule_provider: ScheduleProvider,
    repriced_from_quote: Quote | None = None,
    repricing_trigger: str | None = None,
) -> Quote:
    schedule = _get_schedule(payload.schedule_id, schedule_provider)
    fx_rate = _resolve_fx_rate(db=db, currency=payload.currency)
    rates_by_type = _load_rate_table(
        db=db,
        schedule=schedule,
        equipment_types={item.type for item in payload.equipment},
    )
    surcharge_rules = _load_active_surcharge_rules(db)
    pricing_candidates = _build_pricing_candidates(
        db=db,
        payload=payload,
        schedule=schedule,
        public_rates_by_type=rates_by_type,
        surcharge_rules=surcharge_rules,
    )
    pricing = _select_pricing(db=db, payload=payload, pricing_candidates=pricing_candidates)
    created_at = _normalize_utc(datetime.now(timezone.utc))
    quote_validity = _resolve_quote_validity(
        db=db,
        payload=payload,
        pricing=pricing,
        created_at=created_at,
    )
    approval_reasons = _build_market_approval_reasons(pricing)

    equipment_payload = [{"type": item.type.value, "quantity": item.quantity} for item in payload.equipment]
    source_line_items, surcharge_line_items, source_total_amount = _build_source_quote_line_items(
        payload=payload,
        pricing=pricing,
    )
    line_items, total_amount = _convert_quote_line_items(source_line_items, fx_rate=fx_rate)
    schedule_snapshot = {
        "scheduleId": schedule.schedule_id,
        "originPort": schedule.origin_port,
        "destinationPort": schedule.destination_port,
        "departureDate": schedule.departure_date.isoformat(),
    }

    quote = Quote(
        quote_reference=_generate_quote_reference(db),
        lifecycle_state=QuoteLifecycleState.PENDING_APPROVAL if approval_reasons else QuoteLifecycleState.ISSUED,
        schedule_id=payload.schedule_id,
        schedule_snapshot=schedule_snapshot,
        equipment=equipment_payload,
        cargo_weight_kg=payload.cargo_weight_kg.quantize(_MONEY_PRECISION),
        currency=payload.currency,
        source_currency=_SOURCE_CURRENCY,
        customer_id=payload.customer_id,
        account_id=payload.account_id,
        pricing_mode_hint=None if payload.pricing_mode_hint is None else payload.pricing_mode_hint.value,
        pricing_basis=pricing.pricing_basis,
        contract_id=None if pricing.contract is None else pricing.contract.id,
        market_source=pricing.market_source,
        pricing_provenance=_build_pricing_provenance(
            payload=payload,
            pricing=pricing,
            surcharge_line_items=surcharge_line_items,
            source_total_amount=source_total_amount,
            fx_rate=fx_rate,
            quote_validity=quote_validity,
        ),
        optimization_trace=pricing.optimization_trace,
        approval_reasons=approval_reasons,
        fx_snapshot=_serialize_fx_snapshot(fx_rate),
        rounding_policy=_ROUNDING_POLICY,
        repriced_from_quote_id=None if repriced_from_quote is None else repriced_from_quote.id,
        repricing_trigger=repricing_trigger,
        line_items=line_items,
        total_amount=total_amount,
        valid_until=quote_validity.valid_until,
        created_at=created_at,
    )
    if repriced_from_quote is not None:
        quote.variance_summary = _build_quote_variance_summary(original_quote=repriced_from_quote, repriced_quote=quote)

    db.add(quote)
    db.flush()
    _enqueue_quote_event(db, quote=quote, event_type=_QUOTE_CREATED_EVENT, occurred_at=quote.created_at)
    db.commit()
    db.refresh(quote)
    return quote


@app.post("/quotes", status_code=201)
def create_quote(
    payload: CreateQuoteRequest,
    db: Session = Depends(get_db),
    schedule_provider: ScheduleProvider = Depends(get_schedule_provider),
) -> dict[str, object]:
    quote = _create_quote_record(payload=payload, db=db, schedule_provider=schedule_provider)
    response = _serialize_created_quote(quote)
    if payload.include_alternative_options:
        schedule = _get_schedule(payload.schedule_id, schedule_provider)
        rates_by_type = _load_rate_table(
            db=db,
            schedule=schedule,
            equipment_types={item.type for item in payload.equipment},
        )
        surcharge_rules = _load_active_surcharge_rules(db)
        pricing_candidates = _build_pricing_candidates(
            db=db,
            payload=payload,
            schedule=schedule,
            public_rates_by_type=rates_by_type,
            surcharge_rules=surcharge_rules,
        )
        primary_pricing = pricing_candidates[quote.pricing_basis]
        quote_validities = {
            pricing_basis: _resolve_quote_validity(
                db=db,
                payload=payload,
                pricing=pricing,
                created_at=quote.created_at,
            )
            for pricing_basis, pricing in pricing_candidates.items()
        }
        quote_validities[quote.pricing_basis] = ResolvedQuoteValidity(
            valid_until=quote.valid_until,
            snapshot=quote.pricing_provenance["validityPolicy"],
        )
        response["options"] = _serialize_quote_options(
            payload=payload,
            pricing_candidates=pricing_candidates,
            primary_pricing=primary_pricing,
            fx_rate=_resolve_fx_rate(db=db, currency=payload.currency),
            quote_validities=quote_validities,
            max_alternative_options=payload.max_alternative_options,
        )

    return response


@app.post("/quotes/{quote_id}/approval-decisions")
def create_quote_approval_decision(
    quote_id: str,
    payload: QuoteApprovalDecisionRequest,
    actor: str = Depends(_require_quote_approval_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    quote = _sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db)
    if quote.lifecycle_state != QuoteLifecycleState.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="Only pending approval quotes can be decided")

    decided_at = _normalize_utc(datetime.now(timezone.utc))
    quote.lifecycle_state = (
        QuoteLifecycleState.APPROVED if payload.decision == ApprovalDecision.APPROVE else QuoteLifecycleState.REJECTED
    )
    quote.approval_decision = {
        "decision": payload.decision.value,
        "actor": actor,
        "decidedAt": decided_at.isoformat(),
        "note": payload.note,
    }
    db.add(quote)
    _enqueue_quote_event(
        db,
        quote=quote,
        event_type=_QUOTE_APPROVED_EVENT if payload.decision == ApprovalDecision.APPROVE else _QUOTE_REJECTED_EVENT,
        occurred_at=decided_at,
    )
    db.commit()
    db.refresh(quote)
    return _serialize_quote(quote)


@app.post("/quotes/{quote_id}/revocations")
def revoke_quote(
    quote_id: str,
    payload: QuoteRevocationRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    quote = _sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db)
    if quote.lifecycle_state not in {QuoteLifecycleState.ISSUED, QuoteLifecycleState.APPROVED}:
        raise HTTPException(status_code=409, detail=_quote_revocation_conflict_detail(quote))

    revoked_at = _normalize_utc(datetime.now(timezone.utc))
    quote.lifecycle_state = QuoteLifecycleState.VOID
    db.add(quote)
    _enqueue_quote_event(
        db,
        quote=quote,
        event_type=_QUOTE_REVOKED_EVENT,
        occurred_at=revoked_at,
        payload_extra={
            "revocation": {
                "actor": actor,
                "reason": payload.reason,
                "revokedAt": revoked_at.isoformat(),
            }
        },
    )
    db.commit()
    db.refresh(quote)
    return _serialize_quote(quote)


@app.post("/quotes/{quote_id}/reprice", status_code=201)
def reprice_quote(
    quote_id: str,
    payload: RepriceQuoteRequest,
    _: str = Depends(_require_actor),
    db: Session = Depends(get_db),
    schedule_provider: ScheduleProvider = Depends(get_schedule_provider),
) -> dict[str, object]:
    original_quote = _sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db)
    repriced_quote = _create_quote_record(
        payload=_build_quote_payload_from_stored_quote(original_quote),
        db=db,
        schedule_provider=schedule_provider,
        repriced_from_quote=original_quote,
        repricing_trigger=payload.trigger,
    )
    response = _serialize_quote(repriced_quote)
    response["repricedFromQuoteReference"] = original_quote.quote_reference
    return response


@app.post("/admin/rate-tables", status_code=201)
def create_rate_table(
    payload: AdminRateTableRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    now = _normalize_utc(datetime.now(timezone.utc))
    rate_table = RateTable(
        origin_port=payload.origin_port,
        destination_port=payload.destination_port,
        equipment_type=payload.equipment_type,
        base_rate_usd=payload.base_rate_usd.quantize(_MONEY_PRECISION),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        version=_next_rate_table_version(payload, db),
        is_active=False,
        created_by=actor,
        updated_by=actor,
        activated_by=None,
        created_at=now,
        updated_at=now,
        activated_at=None,
    )
    db.add(rate_table)
    db.flush()
    _record_commercial_change(
        db,
        resource_type=CommercialChangeResourceType.RATE_TABLE,
        resource_id=rate_table.id,
        action=CommercialChangeAction.CREATED,
        actor=actor,
        resource_version=rate_table.version,
        snapshot=_serialize_rate_table(rate_table),
        occurred_at=now,
    )
    db.commit()
    db.refresh(rate_table)
    return _serialize_rate_table(rate_table)


@app.patch("/admin/rate-tables/{rate_table_id}")
def update_rate_table(
    rate_table_id: str,
    payload: AdminRateTableUpdateRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rate_table = _get_rate_table_or_404(rate_table_id, db)
    _ensure_rate_table_is_editable(rate_table)

    if payload.origin_port is not None:
        rate_table.origin_port = payload.origin_port
    if payload.destination_port is not None:
        rate_table.destination_port = payload.destination_port
    if payload.equipment_type is not None:
        rate_table.equipment_type = payload.equipment_type
    if payload.base_rate_usd is not None:
        rate_table.base_rate_usd = payload.base_rate_usd.quantize(_MONEY_PRECISION)
    if payload.valid_from is not None:
        rate_table.valid_from = payload.valid_from
    if payload.valid_to is not None:
        rate_table.valid_to = payload.valid_to
    if rate_table.valid_to < rate_table.valid_from:
        raise HTTPException(status_code=422, detail="validTo must be on or after validFrom")

    rate_table.updated_by = actor
    rate_table.updated_at = _normalize_utc(datetime.now(timezone.utc))
    db.add(rate_table)
    _record_commercial_change(
        db,
        resource_type=CommercialChangeResourceType.RATE_TABLE,
        resource_id=rate_table.id,
        action=CommercialChangeAction.UPDATED,
        actor=actor,
        resource_version=rate_table.version,
        snapshot=_serialize_rate_table(rate_table),
        occurred_at=rate_table.updated_at,
    )
    db.commit()
    db.refresh(rate_table)
    return _serialize_rate_table(rate_table)


@app.post("/admin/rate-tables/{rate_table_id}/activate")
def activate_rate_table(
    rate_table_id: str,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rate_table = _get_rate_table_or_404(rate_table_id, db)
    changed_at = _normalize_utc(datetime.now(timezone.utc))
    _deactivate_superseded_rate_tables(rate_table, actor=actor, changed_at=changed_at, db=db)
    rate_table.is_active = True
    rate_table.updated_by = actor
    rate_table.updated_at = changed_at
    rate_table.activated_by = actor
    rate_table.activated_at = changed_at
    db.add(rate_table)
    _record_commercial_change(
        db,
        resource_type=CommercialChangeResourceType.RATE_TABLE,
        resource_id=rate_table.id,
        action=CommercialChangeAction.ACTIVATED,
        actor=actor,
        resource_version=rate_table.version,
        snapshot=_serialize_rate_table(rate_table),
        occurred_at=changed_at,
    )
    db.commit()
    db.refresh(rate_table)
    return _serialize_rate_table(rate_table)


@app.post("/admin/surcharge-rules", status_code=201)
def create_surcharge_rule(
    payload: AdminSurchargeRuleRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    now = _normalize_utc(datetime.now(timezone.utc))
    surcharge_rule = SurchargeRule(
        surcharge_type=payload.surcharge_type,
        description=payload.description,
        amount_usd=payload.amount_usd.quantize(_MONEY_PRECISION),
        currency=payload.currency,
        port_code=payload.port_code,
        port_scope=payload.port_scope,
        weight_threshold_kg_per_teu=None
        if payload.weight_threshold_kg_per_teu is None
        else payload.weight_threshold_kg_per_teu.quantize(_MONEY_PRECISION),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        version=_next_surcharge_rule_version(payload, db),
        is_active=False,
        created_by=actor,
        updated_by=actor,
        activated_by=None,
        created_at=now,
        updated_at=now,
        activated_at=None,
    )
    db.add(surcharge_rule)
    db.flush()
    _record_commercial_change(
        db,
        resource_type=CommercialChangeResourceType.SURCHARGE_RULE,
        resource_id=surcharge_rule.id,
        action=CommercialChangeAction.CREATED,
        actor=actor,
        resource_version=surcharge_rule.version,
        snapshot=_serialize_surcharge_rule(surcharge_rule),
        occurred_at=now,
    )
    db.commit()
    db.refresh(surcharge_rule)
    return _serialize_surcharge_rule(surcharge_rule)


@app.patch("/admin/surcharge-rules/{surcharge_rule_id}")
def update_surcharge_rule(
    surcharge_rule_id: str,
    payload: AdminSurchargeRuleUpdateRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    surcharge_rule = _get_surcharge_rule_or_404(surcharge_rule_id, db)
    _ensure_surcharge_rule_is_editable(surcharge_rule)

    if payload.surcharge_type is not None:
        surcharge_rule.surcharge_type = payload.surcharge_type
    if payload.description is not None:
        surcharge_rule.description = payload.description
    if payload.amount_usd is not None:
        surcharge_rule.amount_usd = payload.amount_usd.quantize(_MONEY_PRECISION)
    if payload.currency is not None:
        surcharge_rule.currency = payload.currency
    if payload.port_code is not None:
        surcharge_rule.port_code = payload.port_code
    if payload.port_scope is not None:
        surcharge_rule.port_scope = payload.port_scope
    if payload.weight_threshold_kg_per_teu is not None:
        surcharge_rule.weight_threshold_kg_per_teu = payload.weight_threshold_kg_per_teu.quantize(_MONEY_PRECISION)
    if payload.valid_from is not None:
        surcharge_rule.valid_from = payload.valid_from
    if payload.valid_to is not None:
        surcharge_rule.valid_to = payload.valid_to
    if (surcharge_rule.port_code is None) != (surcharge_rule.port_scope is None):
        raise HTTPException(status_code=422, detail="portCode and portScope must be provided together")
    if surcharge_rule.valid_from is not None and surcharge_rule.valid_to is not None and surcharge_rule.valid_to < surcharge_rule.valid_from:
        raise HTTPException(status_code=422, detail="validTo must be on or after validFrom")

    surcharge_rule.updated_by = actor
    surcharge_rule.updated_at = _normalize_utc(datetime.now(timezone.utc))
    db.add(surcharge_rule)
    _record_commercial_change(
        db,
        resource_type=CommercialChangeResourceType.SURCHARGE_RULE,
        resource_id=surcharge_rule.id,
        action=CommercialChangeAction.UPDATED,
        actor=actor,
        resource_version=surcharge_rule.version,
        snapshot=_serialize_surcharge_rule(surcharge_rule),
        occurred_at=surcharge_rule.updated_at,
    )
    db.commit()
    db.refresh(surcharge_rule)
    return _serialize_surcharge_rule(surcharge_rule)


@app.post("/admin/surcharge-rules/{surcharge_rule_id}/activate")
def activate_surcharge_rule(
    surcharge_rule_id: str,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    surcharge_rule = _get_surcharge_rule_or_404(surcharge_rule_id, db)
    changed_at = _normalize_utc(datetime.now(timezone.utc))
    _deactivate_superseded_surcharge_rules(surcharge_rule, actor=actor, changed_at=changed_at, db=db)
    surcharge_rule.is_active = True
    surcharge_rule.updated_by = actor
    surcharge_rule.updated_at = changed_at
    surcharge_rule.activated_by = actor
    surcharge_rule.activated_at = changed_at
    db.add(surcharge_rule)
    _record_commercial_change(
        db,
        resource_type=CommercialChangeResourceType.SURCHARGE_RULE,
        resource_id=surcharge_rule.id,
        action=CommercialChangeAction.ACTIVATED,
        actor=actor,
        resource_version=surcharge_rule.version,
        snapshot=_serialize_surcharge_rule(surcharge_rule),
        occurred_at=changed_at,
    )
    db.commit()
    db.refresh(surcharge_rule)
    return _serialize_surcharge_rule(surcharge_rule)


@app.get("/admin/commercial-change-events")
def list_commercial_change_events(
    resource_type: CommercialChangeResourceType | None = Query(default=None, alias="resourceType"),
    resource_id: str | None = Query(default=None, alias="resourceId"),
    _: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(CommercialChangeEvent).order_by(CommercialChangeEvent.occurred_at.desc())
    if resource_type is not None:
        query = query.where(CommercialChangeEvent.resource_type == resource_type)
    if resource_id is not None:
        query = query.where(CommercialChangeEvent.resource_id == resource_id)

    events = db.scalars(query).all()
    return {"events": [_serialize_commercial_change_event(event) for event in events]}


@app.get("/admin/outbox-events")
def list_outbox_events(
    aggregate_type: str | None = Query(default=None, alias="aggregateType"),
    event_type: str | None = Query(default=None, alias="eventType"),
    published: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(OutboxEvent).order_by(OutboxEvent.occurred_at, OutboxEvent.id)
    if aggregate_type is not None:
        query = query.where(OutboxEvent.aggregate_type == aggregate_type)
    if event_type is not None:
        query = query.where(OutboxEvent.event_type == event_type)
    if published is True:
        query = query.where(OutboxEvent.published_at.is_not(None))
    if published is False:
        query = query.where(OutboxEvent.published_at.is_(None))

    events = db.scalars(query.limit(limit)).all()
    return {"events": [_serialize_outbox_event(event) for event in events]}


@app.post("/admin/outbox-consumers/{consumer_name}/replay")
def replay_outbox_events(
    consumer_name: str,
    payload: ReplayOutboxRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    checkpoint = db.get(OutboxConsumerCheckpoint, consumer_name)
    if checkpoint is None:
        checkpoint = OutboxConsumerCheckpoint(consumer_name=consumer_name)
        db.add(checkpoint)
        db.flush()

    query = select(OutboxEvent)
    if payload.aggregate_types:
        query = query.where(OutboxEvent.aggregate_type.in_(payload.aggregate_types))
    if payload.event_types:
        query = query.where(OutboxEvent.event_type.in_(payload.event_types))
    if not payload.from_start and checkpoint.last_occurred_at is not None:
        if checkpoint.last_event_id is None:
            query = query.where(OutboxEvent.occurred_at > checkpoint.last_occurred_at)
        else:
            query = query.where(
                or_(
                    OutboxEvent.occurred_at > checkpoint.last_occurred_at,
                    and_(
                        OutboxEvent.occurred_at == checkpoint.last_occurred_at,
                        OutboxEvent.id > checkpoint.last_event_id,
                    ),
                )
            )

    events = db.scalars(query.order_by(OutboxEvent.occurred_at, OutboxEvent.id).limit(payload.batch_size)).all()
    if events:
        checkpoint.last_event_id = events[-1].id
        checkpoint.last_occurred_at = events[-1].occurred_at
        checkpoint.processed_events_count += len(events)
    checkpoint.last_replayed_by = actor
    checkpoint.updated_at = _normalize_utc(datetime.now(timezone.utc))
    db.add(checkpoint)
    db.commit()
    db.refresh(checkpoint)

    return {
        "consumerName": consumer_name,
        "replayedCount": len(events),
        "events": [_serialize_outbox_event(event) for event in events],
        "checkpoint": _serialize_checkpoint(checkpoint),
    }


@app.post("/admin/impact-analyses", status_code=201)
def create_impact_analysis(
    payload: ImpactAnalysisRequest,
    actor: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if payload.change_type == ImpactAnalysisChangeType.SCHEDULE:
        quotes = db.scalars(select(Quote).where(Quote.schedule_id == payload.schedule_id).order_by(Quote.created_at.desc())).all()
        target_id = payload.schedule_id
    else:
        quotes = db.scalars(select(Quote).where(Quote.contract_id == payload.contract_id).order_by(Quote.created_at.desc())).all()
        target_id = payload.contract_id

    summary = _build_impact_summary(payload, quotes)
    run = ImpactAnalysisRun(
        change_type=payload.change_type,
        target_id=target_id or "",
        actor=actor,
        summary=summary,
        created_at=_normalize_utc(datetime.now(timezone.utc)),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _serialize_impact_analysis(run)


@app.get("/admin/impact-analyses/{run_id}")
def get_impact_analysis(
    run_id: str,
    _: str = Depends(_require_actor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = db.get(ImpactAnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Impact analysis not found")

    return _serialize_impact_analysis(run)


@app.post("/admin/quote-preview")
def preview_quote(
    payload: AdminQuotePreviewRequest,
    _: str = Depends(_require_actor),
    db: Session = Depends(get_db),
    schedule_provider: ScheduleProvider = Depends(get_schedule_provider),
) -> dict[str, object]:
    schedule = _get_schedule(payload.schedule_id, schedule_provider)
    fx_rate = _resolve_fx_rate(db=db, currency=payload.currency)
    equipment_types = {item.type for item in payload.equipment}
    public_rates_by_type = _find_rate_coverage(
        db=db,
        origin_port=schedule.origin_port,
        destination_port=schedule.destination_port,
        departure_date=schedule.departure_date,
        equipment_types=equipment_types,
    )
    preview_rates_by_type = _apply_preview_rate_tables(
        rates_by_type=public_rates_by_type,
        schedule=schedule,
        preview_rate_tables=_load_rate_tables_by_id(payload.rate_table_ids, db),
    )
    for equipment_type in equipment_types:
        if equipment_type not in preview_rates_by_type:
            raise HTTPException(status_code=400, detail=f"No rate available for {equipment_type.value} on selected schedule")

    surcharge_rules = _apply_preview_surcharge_rules(
        active_surcharge_rules=_load_active_surcharge_rules(db),
        preview_surcharge_rules=_load_surcharge_rules_by_id(payload.surcharge_rule_ids, db),
    )
    pricing = _resolve_pricing(
        db=db,
        payload=payload,
        schedule=schedule,
        public_rates_by_type=preview_rates_by_type,
        surcharge_rules=surcharge_rules,
    )
    quote_validity = _resolve_quote_validity(
        db=db,
        payload=payload,
        pricing=pricing,
        created_at=_normalize_utc(datetime.now(timezone.utc)),
    )
    source_line_items, surcharge_line_items, source_total_amount = _build_source_quote_line_items(
        payload=payload,
        pricing=pricing,
    )
    line_items, total_amount = _convert_quote_line_items(source_line_items, fx_rate=fx_rate)

    return {
        "currency": payload.currency,
        "sourceCurrency": _SOURCE_CURRENCY,
        "responseCurrency": payload.currency,
        "fx": _serialize_fx_snapshot(fx_rate),
        "roundingPolicy": _ROUNDING_POLICY,
        "pricingBasis": pricing.pricing_basis.value,
        "pricingProvenance": _build_pricing_provenance(
            payload=payload,
            pricing=pricing,
            surcharge_line_items=surcharge_line_items,
            source_total_amount=source_total_amount,
            fx_rate=fx_rate,
            quote_validity=quote_validity,
        ),
        "lineItems": line_items,
        "sourceTotalAmount": _serialize_decimal(source_total_amount),
        "totalAmount": _serialize_decimal(total_amount),
    }


@app.post("/quotes/coverage/validate")
def validate_quote_rate_coverage(
    payload: ValidateRateCoverageRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return _serialize_rate_coverage(
        payload,
        _find_rate_coverage(
            db=db,
            origin_port=payload.origin_port,
            destination_port=payload.destination_port,
            departure_date=payload.departure_date,
            equipment_types={item.type for item in payload.equipment},
        ),
    )


@app.post("/quotes/equipment-availability/plan")
def plan_quote_equipment_availability(payload: PlanEquipmentAvailabilityRequest) -> dict[str, object]:
    return _plan_equipment_availability(payload)


@app.get("/quotes/{quote_id}")
def get_quote(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_quote(_sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db))


@app.get("/quotes/{quote_id}/explain")
def get_quote_explainability(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_quote_explainability(_sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db))


@app.get("/quotes/reference/{quote_reference}")
def get_quote_by_reference(quote_reference: str, db: Session = Depends(get_db)) -> dict[str, object]:
    quote = db.scalar(select(Quote).where(Quote.quote_reference == quote_reference))
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    return _serialize_quote(_sync_quote_lifecycle(quote, db))


@app.get("/quotes/{quote_id}/bookability")
def get_quote_bookability(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_bookability(_sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db))
