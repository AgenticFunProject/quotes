from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import EquipmentType, PricingBasis, Quote, RateTable, SurchargeRule
from app.seed import seed_reference_data
from app.schedules import Schedule, ScheduleProvider, get_schedule_provider
from app.surcharges import EquipmentSelection, calculate_surcharges, total_surcharges


_MONEY_PRECISION = Decimal("0.01")
_QUOTE_STATUS_ACTIVE = "ACTIVE"
_QUOTE_STATUS_EXPIRED = "EXPIRED"
_BOOKABILITY_REASON_OPEN = "VALIDITY_WINDOW_OPEN"
_BOOKABILITY_REASON_EXPIRED = "VALIDITY_WINDOW_EXPIRED"


class QuoteEquipmentRequest(BaseModel):
    type: EquipmentType
    quantity: int = Field(gt=0)


class CreateQuoteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schedule_id: str = Field(alias="scheduleId")
    equipment: list[QuoteEquipmentRequest] = Field(min_length=1)
    cargo_weight_kg: Decimal = Field(alias="cargoWeightKg", gt=0)


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


def _serialize_bookability(quote: Quote) -> dict[str, object]:
    expired = _quote_is_expired(quote)
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
    rate_rows = db.scalars(
        select(RateTable).where(
            RateTable.origin_port == schedule.origin_port,
            RateTable.destination_port == schedule.destination_port,
            RateTable.equipment_type.in_(equipment_types),
            RateTable.valid_from <= schedule.departure_date,
            RateTable.valid_to >= schedule.departure_date,
        )
    ).all()
    rates_by_type = {row.equipment_type: row for row in rate_rows}

    for equipment_type in equipment_types:
        if equipment_type not in rates_by_type:
            raise HTTPException(
                status_code=400,
                detail=f"No rate available for {equipment_type.value} on selected schedule",
            )

    return rates_by_type


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
    surcharge_rules = db.scalars(select(SurchargeRule)).all()

    equipment_payload = [{"type": item.type.value, "quantity": item.quantity} for item in payload.equipment]
    base_line_items: list[dict[str, object]] = []
    base_total = Decimal("0.00")
    for item in payload.equipment:
        rate = rates_by_type[item.type]
        amount = (rate.base_rate_usd * item.quantity).quantize(_MONEY_PRECISION)
        base_total += amount
        base_line_items.append(
            {
                "description": f"Ocean Freight - {item.type.value} x {item.quantity}",
                "amount": float(amount),
            }
        )

    surcharge_line_items = calculate_surcharges(
        equipment=[
            EquipmentSelection(equipment_type=item.type, quantity=item.quantity) for item in payload.equipment
        ],
        cargo_weight_kg=payload.cargo_weight_kg,
        shipment_date=schedule.departure_date,
        origin_port=schedule.origin_port,
        destination_port=schedule.destination_port,
        surcharge_rules=surcharge_rules,
    )
    line_items = base_line_items + [item.as_dict() for item in surcharge_line_items]
    total_amount = (base_total + total_surcharges(surcharge_line_items)).quantize(_MONEY_PRECISION)
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
        pricing_basis=PricingBasis.PUBLIC_TARIFF,
        line_items=line_items,
        total_amount=total_amount,
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)

    return _serialize_created_quote(quote)


@app.get("/quotes/{quote_id}")
def get_quote(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_quote(_get_quote_or_404(quote_id, db))


@app.get("/quotes/reference/{quote_reference}")
def get_quote_by_reference(quote_reference: str, db: Session = Depends(get_db)) -> dict[str, object]:
    quote = db.scalar(select(Quote).where(Quote.quote_reference == quote_reference))
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")

    return _serialize_quote(quote)


@app.get("/quotes/{quote_id}/bookability")
def get_quote_bookability(quote_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _serialize_bookability(_get_quote_or_404(quote_id, db))
