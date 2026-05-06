from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum as SqlEnum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EquipmentType(str, Enum):
    TWENTY_FT = "20FT"
    FORTY_FT = "40FT"
    FORTY_FT_HC = "40FT_HC"


class SurchargeType(str, Enum):
    BAF = "BAF"
    PORT_CONGESTION = "PORT_CONGESTION"
    HEAVY_CARGO = "HEAVY_CARGO"
    PEAK_SEASON = "PEAK_SEASON"


class PortScope(str, Enum):
    ORIGIN = "ORIGIN"
    DESTINATION = "DESTINATION"


class QuoteLifecycleState(str, Enum):
    ISSUED = "ISSUED"
    BOOKED = "BOOKED"
    EXPIRED = "EXPIRED"
    VOID = "VOID"


class PricingBasis(str, Enum):
    PUBLIC_TARIFF = "PUBLIC_TARIFF"
    CONTRACT = "CONTRACT"
    MARKET = "MARKET"
    HYBRID = "HYBRID"


class ContractMatchType(str, Enum):
    CUSTOMER = "CUSTOMER"
    ACCOUNT = "ACCOUNT"


class CommercialChangeResourceType(str, Enum):
    RATE_TABLE = "RATE_TABLE"
    SURCHARGE_RULE = "SURCHARGE_RULE"


class CommercialChangeAction(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    ACTIVATED = "ACTIVATED"


class ImpactAnalysisChangeType(str, Enum):
    SCHEDULE = "SCHEDULE"
    CONTRACT = "CONTRACT"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_valid_until() -> datetime:
    return _utc_now() + timedelta(days=7)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    lifecycle_state: Mapped[QuoteLifecycleState] = mapped_column(
        SqlEnum(
            QuoteLifecycleState,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        default=QuoteLifecycleState.ISSUED,
        index=True,
    )
    schedule_id: Mapped[str] = mapped_column(String(36), index=True)
    schedule_snapshot: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    equipment: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    cargo_weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    source_currency: Mapped[str] = mapped_column(String(3), default="USD")
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pricing_basis: Mapped[PricingBasis] = mapped_column(
        SqlEnum(
            PricingBasis,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        default=PricingBasis.PUBLIC_TARIFF,
    )
    contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    pricing_provenance: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    fx_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    rounding_policy: Mapped[str] = mapped_column(String(64), default="LINE_ITEM_HALF_UP_2DP")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    line_items: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_default_valid_until)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    aggregate_type: Mapped[str] = mapped_column(String(32), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    event_version: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)


class OutboxConsumerCheckpoint(Base):
    __tablename__ = "outbox_consumer_checkpoints"

    consumer_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    processed_events_count: Mapped[int] = mapped_column(Integer, default=0)
    last_replayed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class CommercialChangeEvent(Base):
    __tablename__ = "commercial_change_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    resource_type: Mapped[CommercialChangeResourceType] = mapped_column(
        SqlEnum(
            CommercialChangeResourceType,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        index=True,
    )
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[CommercialChangeAction] = mapped_column(
        SqlEnum(
            CommercialChangeAction,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(64), index=True)
    resource_version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, index=True)


class ImpactAnalysisRun(Base):
    __tablename__ = "impact_analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    change_type: Mapped[ImpactAnalysisChangeType] = mapped_column(
        SqlEnum(
            ImpactAnalysisChangeType,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        index=True,
    )
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, index=True)


class ManagedCommercialRecord:
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RateTable(ManagedCommercialRecord, Base):
    __tablename__ = "rate_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    origin_port: Mapped[str] = mapped_column(String(16), index=True)
    destination_port: Mapped[str] = mapped_column(String(16), index=True)
    equipment_type: Mapped[EquipmentType] = mapped_column(
        SqlEnum(
            EquipmentType,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    base_rate_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    match_type: Mapped[ContractMatchType] = mapped_column(
        SqlEnum(
            ContractMatchType,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    origin_port: Mapped[str] = mapped_column(String(16), index=True)
    destination_port: Mapped[str] = mapped_column(String(16), index=True)
    waived_surcharge_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)


class ContractRateRule(Base):
    __tablename__ = "contract_rate_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    contract_id: Mapped[str] = mapped_column(String(36), index=True)
    equipment_type: Mapped[EquipmentType] = mapped_column(
        SqlEnum(
            EquipmentType,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    base_rate_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    provider: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reference_data_version: Mapped[str] = mapped_column(String(64))


class SurchargeRule(ManagedCommercialRecord, Base):
    __tablename__ = "surcharge_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    surcharge_type: Mapped[SurchargeType] = mapped_column(
        SqlEnum(
            SurchargeType,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        index=True,
    )
    description: Mapped[str] = mapped_column(String(128))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    port_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    port_scope: Mapped[PortScope | None] = mapped_column(
        SqlEnum(
            PortScope,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=True,
    )
    weight_threshold_kg_per_teu: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
