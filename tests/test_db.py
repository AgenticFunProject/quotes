from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    EquipmentType,
    PortScope,
    PricingBasis,
    Quote,
    QuoteLifecycleState,
    RateTable,
    SurchargeRule,
    SurchargeType,
)


def test_models_create_sqlite_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {"quotes", "rate_tables", "surcharge_rules"}


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
    session.commit()

    assert session.query(Quote).count() == 1
    assert session.query(RateTable).count() == 1
    assert session.query(SurchargeRule).count() == 1
    stored_quote = session.query(Quote).one()
    assert stored_quote.lifecycle_state == QuoteLifecycleState.ISSUED
    assert stored_quote.schedule_snapshot["originPort"] == "NLRTM"
    assert stored_quote.pricing_basis == PricingBasis.PUBLIC_TARIFF
    assert stored_quote.idempotency_key == "request-123"
