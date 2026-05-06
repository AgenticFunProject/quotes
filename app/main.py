from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import CommercialChangeAction, CommercialChangeEvent, CommercialChangeResourceType, Contract, ContractMatchType, ContractRateRule, EquipmentType, OutboxEvent, PortScope, PricingBasis, Quote, QuoteLifecycleState, RateTable, SurchargeRule, SurchargeType
from app.seed import REFERENCE_DATA_VERSION, seed_reference_data
from app.schedules import Schedule, ScheduleProvider, get_schedule_provider
from app.surcharges import EquipmentSelection, SurchargeLineItem, calculate_surcharges, total_surcharges


_MONEY_PRECISION = Decimal("0.01")
_QUOTE_STATUS_ACTIVE = "ACTIVE"
_QUOTE_STATUS_EXPIRED = "EXPIRED"
_BOOKABILITY_REASON_OPEN = "VALIDITY_WINDOW_OPEN"
_BOOKABILITY_REASON_EXPIRED = "VALIDITY_WINDOW_EXPIRED"
_OUTBOX_AGGREGATE_QUOTE = "quote"
_QUOTE_CREATED_EVENT = "quote.created"
_QUOTE_EXPIRED_EVENT = "quote.expired"
_OUTBOX_EVENT_VERSION = 1


@dataclass(frozen=True)
class ResolvedPricing:
    pricing_basis: PricingBasis
    rates_by_type: dict[EquipmentType, object]
    surcharge_line_items: list[SurchargeLineItem]
    contract: Contract | None = None


class QuoteEquipmentRequest(BaseModel):
    type: EquipmentType
    quantity: int = Field(gt=0)


class CreateQuoteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schedule_id: str = Field(alias="scheduleId")
    equipment: list[QuoteEquipmentRequest] = Field(min_length=1)
    cargo_weight_kg: Decimal = Field(alias="cargoWeightKg", gt=0)
    customer_id: str | None = Field(default=None, alias="customerId", min_length=1)
    account_id: str | None = Field(default=None, alias="accountId", min_length=1)


class ValidateRateCoverageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    origin_port: str = Field(alias="originPort", min_length=1)
    destination_port: str = Field(alias="destinationPort", min_length=1)
    departure_date: date = Field(alias="departureDate")
    equipment: list[QuoteEquipmentRequest] = Field(min_length=1)


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


def _require_actor(actor: str | None = Header(default=None, alias="X-Actor")) -> str:
    if actor is None or not actor.strip():
        raise HTTPException(status_code=400, detail="X-Actor header is required for admin commercial data changes")

    return actor.strip()


def _serialize_quote(quote: Quote) -> dict[str, object]:
    return {
        "id": quote.id,
        "quoteReference": quote.quote_reference,
        "lifecycleState": quote.lifecycle_state.value,
        "scheduleId": quote.schedule_id,
        "scheduleSnapshot": quote.schedule_snapshot,
        "equipment": quote.equipment,
        "cargoWeightKg": _serialize_decimal(quote.cargo_weight_kg),
        "currency": quote.currency,
        "pricingBasis": quote.pricing_basis.value,
        "pricingProvenance": quote.pricing_provenance,
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
        "totalAmount": _serialize_decimal(quote.total_amount),
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def _serialize_created_quote(quote: Quote) -> dict[str, object]:
    return {
        "id": quote.id,
        "quoteReference": quote.quote_reference,
        "validUntil": quote.valid_until.isoformat(),
        "currency": quote.currency,
        "lineItems": [
            {
                "description": item["description"],
                "amount": float(item["amount"]),
            }
            for item in quote.line_items
        ],
        "totalAmount": _serialize_decimal(quote.total_amount),
    }


def _build_quote_event_payload(quote: Quote) -> dict[str, object]:
    return {
        "quoteId": quote.id,
        "quoteReference": quote.quote_reference,
        "lifecycleState": quote.lifecycle_state.value,
        "scheduleId": quote.schedule_id,
        "scheduleSnapshot": quote.schedule_snapshot,
        "equipment": quote.equipment,
        "cargoWeightKg": _serialize_decimal(quote.cargo_weight_kg),
        "currency": quote.currency,
        "customerId": quote.customer_id,
        "accountId": quote.account_id,
        "contractId": quote.contract_id,
        "pricingBasis": quote.pricing_basis.value,
        "pricingProvenance": quote.pricing_provenance,
        "lineItems": quote.line_items,
        "totalAmount": _serialize_decimal(quote.total_amount),
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def _enqueue_quote_event(
    db: Session,
    *,
    quote: Quote,
    event_type: str,
    occurred_at: datetime | None = None,
) -> None:
    db.add(
        OutboxEvent(
            aggregate_type=_OUTBOX_AGGREGATE_QUOTE,
            aggregate_id=quote.id,
            event_type=event_type,
            event_version=_OUTBOX_EVENT_VERSION,
            payload=_build_quote_event_payload(quote),
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
    if quote.lifecycle_state != QuoteLifecycleState.ISSUED:
        return quote

    if not _quote_is_expired(quote):
        return quote

    quote.lifecycle_state = QuoteLifecycleState.EXPIRED
    _enqueue_quote_event(db, quote=quote, event_type=_QUOTE_EXPIRED_EVENT)
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote


def _serialize_bookability(quote: Quote) -> dict[str, object]:
    expired = quote.lifecycle_state == QuoteLifecycleState.EXPIRED or _quote_is_expired(quote)
    return {
        "quoteId": quote.quote_reference,
        "bookable": not expired,
        "status": _QUOTE_STATUS_EXPIRED if expired else _QUOTE_STATUS_ACTIVE,
        "reason": _BOOKABILITY_REASON_EXPIRED if expired else _BOOKABILITY_REASON_OPEN,
        "expired": expired,
        "validUntil": quote.valid_until.isoformat(),
    }


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


def _resolve_pricing(
    *,
    db: Session,
    payload: CreateQuoteRequest,
    schedule: Schedule,
    public_rates_by_type: dict[EquipmentType, RateTable],
    surcharge_rules: list[SurchargeRule],
) -> ResolvedPricing:
    public_surcharge_line_items = calculate_surcharges(
        equipment=[EquipmentSelection(equipment_type=item.type, quantity=item.quantity) for item in payload.equipment],
        cargo_weight_kg=payload.cargo_weight_kg,
        shipment_date=schedule.departure_date,
        origin_port=schedule.origin_port,
        destination_port=schedule.destination_port,
        surcharge_rules=surcharge_rules,
    )

    for contract in _find_contracts(db=db, payload=payload, schedule=schedule):
        contract_rates_by_type = _load_contract_rate_rules(db, contract.id)
        if any(item.type not in contract_rates_by_type for item in payload.equipment):
            continue

        return ResolvedPricing(
            pricing_basis=PricingBasis.CONTRACT,
            rates_by_type=contract_rates_by_type,
            surcharge_line_items=_waive_surcharges(public_surcharge_line_items, contract.waived_surcharge_types),
            contract=contract,
        )

    return ResolvedPricing(
        pricing_basis=PricingBasis.PUBLIC_TARIFF,
        rates_by_type=public_rates_by_type,
        surcharge_line_items=public_surcharge_line_items,
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


def _build_pricing_provenance(
    *,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
    surcharge_line_items: list[SurchargeLineItem],
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "pricingBasis": pricing.pricing_basis.value,
        "referenceDataVersion": REFERENCE_DATA_VERSION,
        "baseRateRules": [
            {
                "rateTableId": rate.id,
                "equipmentType": item.type.value,
                "quantity": item.quantity,
                "currency": "USD",
                "unitAmount": _serialize_decimal(rate.base_rate_usd),
                "totalAmount": _serialize_decimal((rate.base_rate_usd * item.quantity).quantize(_MONEY_PRECISION)),
                "rateVersion": None if pricing.contract is not None else rate.version,
                "validFrom": None if pricing.contract is None else pricing.contract.valid_from.isoformat(),
                "validTo": None if pricing.contract is None else pricing.contract.valid_to.isoformat(),
            }
            for item in payload.equipment
            for rate in [pricing.rates_by_type[item.type]]
        ],
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
    }

    if pricing.contract is None:
        for rate_rule in provenance["baseRateRules"]:
            equipment_type = EquipmentType(rate_rule["equipmentType"])
            rate = pricing.rates_by_type[equipment_type]
            rate_rule["validFrom"] = rate.valid_from.isoformat()
            rate_rule["validTo"] = rate.valid_to.isoformat()
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


def _build_quote_line_items(
    *,
    payload: CreateQuoteRequest,
    pricing: ResolvedPricing,
) -> tuple[list[dict[str, object]], list[SurchargeLineItem], Decimal]:
    base_line_items: list[dict[str, object]] = []
    base_total = Decimal("0.00")
    for item in payload.equipment:
        rate = pricing.rates_by_type[item.type]
        amount = (rate.base_rate_usd * item.quantity).quantize(_MONEY_PRECISION)
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


@app.post("/quotes", status_code=201)
def create_quote(
    payload: CreateQuoteRequest,
    db: Session = Depends(get_db),
    schedule_provider: ScheduleProvider = Depends(get_schedule_provider),
) -> dict[str, object]:
    schedule = _get_schedule(payload.schedule_id, schedule_provider)
    rates_by_type = _load_rate_table(
        db=db,
        schedule=schedule,
        equipment_types={item.type for item in payload.equipment},
    )
    surcharge_rules = _load_active_surcharge_rules(db)
    pricing = _resolve_pricing(
        db=db,
        payload=payload,
        schedule=schedule,
        public_rates_by_type=rates_by_type,
        surcharge_rules=surcharge_rules,
    )

    equipment_payload = [{"type": item.type.value, "quantity": item.quantity} for item in payload.equipment]
    line_items, surcharge_line_items, total_amount = _build_quote_line_items(payload=payload, pricing=pricing)
    schedule_snapshot = {
        "scheduleId": schedule.schedule_id,
        "originPort": schedule.origin_port,
        "destinationPort": schedule.destination_port,
        "departureDate": schedule.departure_date.isoformat(),
    }

    quote = Quote(
        quote_reference=_generate_quote_reference(db),
        schedule_id=payload.schedule_id,
        schedule_snapshot=schedule_snapshot,
        equipment=equipment_payload,
        cargo_weight_kg=payload.cargo_weight_kg.quantize(_MONEY_PRECISION),
        currency="USD",
        customer_id=payload.customer_id,
        account_id=payload.account_id,
        pricing_basis=pricing.pricing_basis,
        contract_id=None if pricing.contract is None else pricing.contract.id,
        pricing_provenance=_build_pricing_provenance(
            payload=payload,
            pricing=pricing,
            surcharge_line_items=surcharge_line_items,
        ),
        line_items=line_items,
        total_amount=total_amount,
    )
    db.add(quote)
    db.flush()
    _enqueue_quote_event(db, quote=quote, event_type=_QUOTE_CREATED_EVENT, occurred_at=quote.created_at)
    db.commit()
    db.refresh(quote)

    return _serialize_created_quote(quote)


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
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(CommercialChangeEvent).order_by(CommercialChangeEvent.occurred_at.desc())
    if resource_type is not None:
        query = query.where(CommercialChangeEvent.resource_type == resource_type)
    if resource_id is not None:
        query = query.where(CommercialChangeEvent.resource_id == resource_id)

    events = db.scalars(query).all()
    return {"events": [_serialize_commercial_change_event(event) for event in events]}


@app.post("/admin/quote-preview")
def preview_quote(
    payload: AdminQuotePreviewRequest,
    _: str = Depends(_require_actor),
    db: Session = Depends(get_db),
    schedule_provider: ScheduleProvider = Depends(get_schedule_provider),
) -> dict[str, object]:
    schedule = _get_schedule(payload.schedule_id, schedule_provider)
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
    line_items, surcharge_line_items, total_amount = _build_quote_line_items(payload=payload, pricing=pricing)

    return {
        "currency": "USD",
        "pricingBasis": pricing.pricing_basis.value,
        "pricingProvenance": _build_pricing_provenance(
            payload=payload,
            pricing=pricing,
            surcharge_line_items=surcharge_line_items,
        ),
        "lineItems": line_items,
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


@app.get("/quotes/{quote_id}")
def get_quote(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_quote(_sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db))


@app.get("/quotes/reference/{quote_reference}")
def get_quote_by_reference(quote_reference: str, db: Session = Depends(get_db)) -> dict[str, object]:
    quote = db.scalar(select(Quote).where(Quote.quote_reference == quote_reference))
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    return _serialize_quote(_sync_quote_lifecycle(quote, db))


@app.get("/quotes/{quote_id}/bookability")
def get_quote_bookability(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_bookability(_sync_quote_lifecycle(_get_quote_or_404(quote_id, db), db))
