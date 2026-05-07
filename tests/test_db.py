from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.db import Base
from app.models import (
    CommercialChangeAction,
    CommercialChangeEvent,
    CommercialChangeResourceType,
    Contract,
    ContractMatchType,
    ContractRateRule,
    EquipmentType,
    ImpactAnalysisChangeType,
    ImpactAnalysisRun,
    MarketRateSnapshot,
    OutboxEvent,
    OutboxConsumerCheckpoint,
    PortScope,
    PricingBasis,
    PricingStrategyVersion,
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
    assert set(inspector.get_table_names()) == {
        "commercial_change_events",
        "contract_rate_rules",
        "contracts",
        "exchange_rates",
        "impact_analysis_runs",
        "market_rate_snapshots",
        "outbox_events",
        "outbox_consumer_checkpoints",
        "pricing_strategy_versions",
        "quotes",
        "rate_tables",
        "surcharge_rules",
    }


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
        Contract(
            id="contract-1",
            customer_id="cust-acme",
            account_id=None,
            match_type=ContractMatchType.CUSTOMER,
            origin_port="NLRTM",
            destination_port="USNYC",
            waived_surcharge_types=[SurchargeType.PEAK_SEASON.value],
            valid_from=date(2026, 4, 1),
            valid_to=date(2026, 12, 31),
        )
    )
    session.add(
        ContractRateRule(
            contract_id="contract-1",
            equipment_type=EquipmentType.TWENTY_FT,
            base_rate_usd=Decimal("700.00"),
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
            customer_id="cust-acme",
            account_id=None,
            pricing_basis=PricingBasis.PUBLIC_TARIFF,
            contract_id=None,
            market_source=None,
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
            optimization_trace={"decision": "STRATEGY_FALLBACK"},
            idempotency_key="request-123",
            line_items=[{"description": "Ocean Freight", "amount": 1800.0}],
            total_amount=Decimal("1800.00"),
        )
    )
    session.add(
        MarketRateSnapshot(
            id="market-1",
            source_name="approved-spot-market-feed",
            source_reference="spot-quote-1",
            origin_port="NLRTM",
            destination_port="USNYC",
            equipment_type=EquipmentType.TWENTY_FT,
            rate_usd=Decimal("1010.00"),
            valid_from=date(2026, 4, 1),
            valid_to=date(2026, 4, 30),
            capacity_pressure_index=Decimal("0.70"),
            utilization_index=Decimal("0.82"),
            seasonality_index=Decimal("0.60"),
            captured_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            approved_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            approved_by="pricing.manager@quotes",
        )
    )
    session.add(
        PricingStrategyVersion(
            id="strategy-1",
            strategy_name="market-optimization",
            rules={"capacityPressureThreshold": 0.75},
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
        CommercialChangeEvent(
            resource_type=CommercialChangeResourceType.RATE_TABLE,
            resource_id="rate-1",
            action=CommercialChangeAction.CREATED,
            actor="pricing.ops@quotes",
            resource_version=1,
            snapshot={"id": "rate-1"},
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
    session.add(
        OutboxConsumerCheckpoint(
            consumer_name="booking-cache",
            last_event_id="outbox-1",
            processed_events_count=2,
        )
    )
    session.add(
        ImpactAnalysisRun(
            change_type=ImpactAnalysisChangeType.SCHEDULE,
            target_id="53c362b2-1229-4ea5-a24a-9891fb1f509d",
            actor="ops@quotes",
            summary={"affectedCount": 1},
        )
    )
    session.commit()

    assert session.query(CommercialChangeEvent).count() == 1
    assert session.query(ImpactAnalysisRun).count() == 1
    assert session.query(OutboxEvent).count() == 1
    assert session.query(OutboxConsumerCheckpoint).count() == 1
    assert session.query(Contract).count() == 1
    assert session.query(ContractRateRule).count() == 1
    assert session.query(MarketRateSnapshot).count() == 1
    assert session.query(PricingStrategyVersion).count() == 1
    assert session.query(Quote).count() == 1
    assert session.query(RateTable).count() == 1
    assert session.query(SurchargeRule).count() == 1
    stored_quote = session.query(Quote).one()
    stored_event = session.query(OutboxEvent).one()
    assert stored_quote.lifecycle_state == QuoteLifecycleState.ISSUED
    assert stored_quote.schedule_snapshot["originPort"] == "NLRTM"
    assert stored_quote.pricing_basis == PricingBasis.PUBLIC_TARIFF
    assert stored_quote.customer_id == "cust-acme"
    assert stored_quote.pricing_provenance["referenceDataVersion"] == REFERENCE_DATA_VERSION
    assert stored_quote.optimization_trace["decision"] == "STRATEGY_FALLBACK"
    assert stored_quote.idempotency_key == "request-123"
    assert session.query(CommercialChangeEvent).one().action == CommercialChangeAction.CREATED
    assert stored_event.event_type == "quote.created"
    assert session.query(OutboxConsumerCheckpoint).one().consumer_name == "booking-cache"
    assert session.query(ImpactAnalysisRun).one().change_type == ImpactAnalysisChangeType.SCHEDULE
    assert session.query(RateTable).one().version == 1
    assert session.query(RateTable).one().is_active is True
    assert session.query(SurchargeRule).one().version == 1
    assert session.query(SurchargeRule).one().is_active is True


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
                "customer_id VARCHAR(64), "
                "account_id VARCHAR(64), "
                "pricing_basis VARCHAR(32), "
                "contract_id VARCHAR(36), "
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
    assert "customer_id" in quote_columns
    assert "account_id" in quote_columns
    assert "contract_id" in quote_columns
    assert "market_source" in quote_columns
    assert "pricing_provenance" in quote_columns
    assert "optimization_trace" in quote_columns
    assert "source_currency" in quote_columns
    assert "fx_snapshot" in quote_columns
    assert "rounding_policy" in quote_columns


def test_init_db_backfills_managed_commercial_columns_for_existing_sqlite_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE rate_tables ("
                "id VARCHAR(36) PRIMARY KEY, "
                "origin_port VARCHAR(16), "
                "destination_port VARCHAR(16), "
                "equipment_type VARCHAR(16), "
                "base_rate_usd NUMERIC(10, 2), "
                "valid_from DATE, "
                "valid_to DATE"
                ")"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE surcharge_rules ("
                "id VARCHAR(36) PRIMARY KEY, "
                "surcharge_type VARCHAR(32), "
                "description VARCHAR(128), "
                "amount_usd NUMERIC(10, 2), "
                "currency VARCHAR(3), "
                "port_code VARCHAR(16), "
                "port_scope VARCHAR(16), "
                "weight_threshold_kg_per_teu NUMERIC(10, 2), "
                "valid_from DATE, "
                "valid_to DATE"
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
    rate_columns = {column["name"] for column in inspector.get_columns("rate_tables")}
    surcharge_columns = {column["name"] for column in inspector.get_columns("surcharge_rules")}
    for expected_column in {
        "version",
        "is_active",
        "created_by",
        "updated_by",
        "activated_by",
        "created_at",
        "updated_at",
        "activated_at",
    }:
        assert expected_column in rate_columns
        assert expected_column in surcharge_columns
