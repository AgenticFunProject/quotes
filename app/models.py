from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Enum as SqlEnum, Numeric, String
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
    pricing_basis: Mapped[PricingBasis] = mapped_column(
        SqlEnum(
            PricingBasis,
            native_enum=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        default=PricingBasis.PUBLIC_TARIFF,
    )
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


class RateTable(Base):
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


class SurchargeRule(Base):
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
