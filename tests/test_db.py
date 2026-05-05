from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.db import Base
from app.models import (
    EquipmentType,
    OutboxEvent,
    PortScope,
    PricingBasis,
    Quote,
    QuoteLifecycleState,
    RateTable,
    SurchargeRule,
    SurchargeType,
)
from app.seed import REFERENCE_DATA_VERSION


def test_models_create_sqlite_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {"outbox_events", "quotes", "rate_tables", "surcharge_rules"}


def test_models_persist_records() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    session.add(
        RateTable(
            origin_port="NLRTM",
            destination_port="USNYC",
            equipment_type=EquipmentType.TWENTY_FT,
            base_rate_usd=Decimal("900.00"),
            valid_from=date(2026, 4, 1),
            valid_to=date(2026, 4, 30),
        )
    )
    session.add(
        Quote(
            quote_reference="QTE-2026-00001",
            lifecycle_state=QuoteLifecycleState.ISSUED,
            schedule_id="53c362b2-1229-4ea5-a24a-9891fb1f509d",
            schedule_snapshot={
                "scheduleId": "53c362b2-1229-4ea5-a24a-9891fb1f509d",
                "originPort": "NLRTM",
                "destinationPort": "USNYC",
                "departureDate": "2026-04-15",
            },
            equipment=[{"type": EquipmentType.TWENTY_FT.value, "quantity": 2}],
            cargo_weight_kg=Decimal("18000.00"),
            pricing_basis=PricingBasis.PUBLIC_TARIFF,
            pricing_provenance={
                "pricingBasis": PricingBasis.PUBLIC_TARIFF.value,
                "referenceDataVersion": REFERENCE_DATA_VERSION,
                "baseRateRules": [
                    {
                        "rateTableId": "rate-1",
                        "equipmentType": EquipmentType.TWENTY_FT.value,
                        "quantity": 2,
                        "currency": "USD",
                        "unitAmount": 900.0,
                        "totalAmount": 1800.0,
                        "validFrom": "2026-04-01",
                        "validTo": "2026-04-30",
                    }
                ],
                "appliedSurchargeRules": [],
            },
            idempotency_key="request-123",
            line_items=[{"description": "Ocean Freight", "amount": 1800.0}],
            total_amount=Decimal("1800.00"),
        )
    )
    session.add(
        SurchargeRule(
            surcharge_type=SurchargeType.PORT_CONGESTION,
            description="Port Surcharge - Destination",
            amount_usd=Decimal("150.00"),
            port_code="USNYC",
            port_scope=PortScope.DESTINATION,
        )
    )
    session.add(
        OutboxEvent(
            aggregate_type="quote",
            aggregate_id="53c362b2-1229-4ea5-a24a-9891fb1f509d",
            event_type="quote.created",
            payload={"quoteReference": "QTE-2026-00001"},
        )
    )
    session.commit()

    assert session.query(OutboxEvent).count() == 1
    assert session.query(Quote).count() == 1
    assert session.query(RateTable).count() == 1
    assert session.query(SurchargeRule).count() == 1
    stored_quote = session.query(Quote).one()
    stored_event = session.query(OutboxEvent).one()
    assert stored_quote.lifecycle_state == QuoteLifecycleState.ISSUED
    assert stored_quote.schedule_snapshot["originPort"] == "NLRTM"
    assert stored_quote.pricing_basis == PricingBasis.PUBLIC_TARIFF
    assert stored_quote.pricing_provenance["referenceDataVersion"] == REFERENCE_DATA_VERSION
    assert stored_quote.idempotency_key == "request-123"
    assert stored_event.event_type == "quote.created"


def test_init_db_backfills_pricing_provenance_column_for_existing_sqlite_quotes_table() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE quotes ("
                "id VARCHAR(36) PRIMARY KEY, "
                "quote_reference VARCHAR(32), "
                "lifecycle_state VARCHAR(32), "
                "schedule_id VARCHAR(36), "
                "schedule_snapshot JSON, "
                "equipment JSON, "
                "cargo_weight_kg NUMERIC(10, 2), "
                "currency VARCHAR(3), "
                "pricing_basis VARCHAR(32), "
                "idempotency_key VARCHAR(128), "
                "line_items JSON, "
                "total_amount NUMERIC(10, 2), "
                "valid_until DATETIME, "
                "created_at DATETIME"
                ")"
            )
        )

    original_engine = db_module.engine
    original_session_local = db_module.SessionLocal
    try:
        db_module.engine = engine
        db_module.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db_module.init_db()
    finally:
        db_module.engine = original_engine
        db_module.SessionLocal = original_session_local

    inspector = inspect(engine)
    quote_columns = {column["name"] for column in inspector.get_columns("quotes")}
    assert "pricing_provenance" in quote_columns
