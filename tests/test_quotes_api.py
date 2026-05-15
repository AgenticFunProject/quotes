from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db
from app.db import Base, get_db
from app.main import app
from app.models import CommercialChangeAction, CommercialChangeEvent, CommercialChangeResourceType, EquipmentType, ExchangeRate, ImpactAnalysisRun, MarketRateSnapshot, OutboxConsumerCheckpoint, OutboxEvent, PricingBasis, PricingStrategyVersion, Quote, QuoteLifecycleState, RateTable, SurchargeRule
from app.seed import FX_PROVIDER, FX_REFERENCE_DATA_VERSION, REFERENCE_DATA_VERSION, seed_reference_data
from app.schedules import Schedule, get_schedule_provider


@pytest.fixture()
def client(monkeypatch) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr("app.seed.SessionLocal", session_factory)

    Base.metadata.create_all(bind=engine)
    seed_reference_data()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, session_factory

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _public_tariff_pricing_provenance() -> dict[str, object]:
    return {
        "pricingBasis": PricingBasis.PUBLIC_TARIFF.value,
        "referenceDataVersion": REFERENCE_DATA_VERSION,
        "sourceCurrency": "USD",
        "responseCurrency": "USD",
        "sourceTotalAmount": 1960.0,
        "currencyConversion": {
            "provider": FX_PROVIDER,
            "baseCurrency": "USD",
            "quoteCurrency": "USD",
            "rate": 1.0,
            "observedAt": "2026-05-06T00:00:00+00:00",
            "referenceDataVersion": FX_REFERENCE_DATA_VERSION,
            "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
            "conversionLevel": "LINE_ITEM",
        },
        "baseRateRules": [
            {
                "rateTableId": "rate-20ft-nlrtm-usnyc",
                "equipmentType": "20FT",
                "quantity": 2,
                "currency": "USD",
                "unitAmount": 900.0,
                "totalAmount": 1800.0,
                "rateVersion": 1,
                "validFrom": "2026-04-01",
                "validTo": "2026-04-30",
            }
        ],
        "appliedSurchargeRules": [
            {
                "surchargeRuleId": "rule-baf",
                "surchargeType": "BAF",
                "description": "Bunker Adjustment Factor (BAF)",
                "currency": "USD",
                "unitAmount": 80.0,
                "totalAmount": 160.0,
                "surchargeRuleVersion": 1,
                "portCode": None,
                "portScope": None,
                "weightThresholdKgPerTeu": None,
                "validFrom": None,
                "validTo": None,
            }
        ],
        "validityPolicy": {
            "policyId": "validity-default-7d",
            "policyName": "Default seven-day validity",
            "validityHours": 168,
            "matchedOn": {
                "customerId": None,
                "accountId": None,
                "contractId": None,
                "pricingBasis": None,
                "marketSignals": None,
            },
            "selectionContext": {
                "customerId": None,
                "accountId": None,
                "contractId": None,
                "pricingBasis": PricingBasis.PUBLIC_TARIFF.value,
                "marketSignals": {},
            },
        },
    }


def _fx_snapshot(*, currency: str = "USD", rate: float = 1.0) -> dict[str, object]:
    return {
        "provider": FX_PROVIDER,
        "baseCurrency": "USD",
        "quoteCurrency": currency,
        "rate": rate,
        "observedAt": "2026-05-06T00:00:00+00:00",
        "referenceDataVersion": FX_REFERENCE_DATA_VERSION,
    }


def _validity_policy_snapshot(
    *,
    policy_id: str,
    policy_name: str,
    validity_hours: int,
    customer_id: str | None,
    account_id: str | None,
    contract_id: str | None,
    pricing_basis: PricingBasis,
    market_signals: dict[str, float],
    matched_pricing_basis: str | None = None,
    matched_market_signals: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "policyId": policy_id,
        "policyName": policy_name,
        "validityHours": validity_hours,
        "matchedOn": {
            "customerId": customer_id if customer_id is not None and policy_id != "validity-default-7d" else None,
            "accountId": account_id if account_id is not None and policy_id == "validity-account-acme-premium-14d" else None,
            "contractId": contract_id if contract_id is not None and policy_id.startswith("validity-contract-") else None,
            "pricingBasis": matched_pricing_basis,
            "marketSignals": matched_market_signals,
        },
        "selectionContext": {
            "customerId": customer_id,
            "accountId": account_id,
            "contractId": contract_id,
            "pricingBasis": pricing_basis.value,
            "marketSignals": market_signals,
        },
    }


def test_create_quote_returns_itemized_quote_and_persists_it(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [
                {"type": "20FT", "quantity": 2},
                {"type": "40FT", "quantity": 1},
            ],
            "cargoWeightKg": 70000,
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "quoteReference": response.json()["quoteReference"],
        "validUntil": response.json()["validUntil"],
        "currency": "USD",
        "sourceCurrency": "USD",
        "responseCurrency": "USD",
        "lifecycleState": "ISSUED",
        "approvalReasons": [],
        "approvalDecision": None,
        "fx": _fx_snapshot(),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1900.0},
            {"description": "Ocean Freight - 40FT x 1", "amount": 1400.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 240.0},
            {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 450.0},
            {"description": "Peak Season Surcharge", "amount": 360.0},
        ],
        "sourceTotalAmount": 4350.0,
        "totalAmount": 4350.0,
    }
    assert response.json()["id"]
    assert response.json()["quoteReference"].endswith("-00001")
    assert response.json()["quoteReference"].startswith("QTE-")

    valid_until = datetime.fromisoformat(response.json()["validUntil"])

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    created_at = stored_quote.created_at
    assert valid_until > created_at
    assert timedelta(days=6, hours=23) <= valid_until - created_at <= timedelta(days=7, minutes=1)
    assert stored_quote.id == response.json()["id"]
    assert stored_quote.quote_reference == response.json()["quoteReference"]
    assert float(stored_quote.total_amount) == response.json()["totalAmount"]
    assert stored_quote.source_currency == "USD"
    assert stored_quote.fx_snapshot == _fx_snapshot()
    assert stored_quote.rounding_policy == "LINE_ITEM_HALF_UP_2DP"
    assert stored_quote.lifecycle_state == QuoteLifecycleState.ISSUED
    assert stored_quote.pricing_basis == PricingBasis.PUBLIC_TARIFF
    assert stored_quote.pricing_provenance["pricingBasis"] == PricingBasis.PUBLIC_TARIFF.value
    assert stored_quote.pricing_provenance["referenceDataVersion"] == REFERENCE_DATA_VERSION
    assert stored_quote.pricing_provenance["currencyConversion"] == {
        **_fx_snapshot(),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "conversionLevel": "LINE_ITEM",
    }
    assert stored_quote.pricing_provenance["validityPolicy"] == _public_tariff_pricing_provenance()["validityPolicy"]
    assert stored_quote.pricing_provenance["baseRateRules"] == [
        {
            "rateTableId": stored_quote.pricing_provenance["baseRateRules"][0]["rateTableId"],
            "equipmentType": "20FT",
            "quantity": 2,
            "currency": "USD",
            "unitAmount": 950.0,
            "totalAmount": 1900.0,
            "rateVersion": 1,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
        {
            "rateTableId": stored_quote.pricing_provenance["baseRateRules"][1]["rateTableId"],
            "equipmentType": "40FT",
            "quantity": 1,
            "currency": "USD",
            "unitAmount": 1400.0,
            "totalAmount": 1400.0,
            "rateVersion": 1,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    ]
    assert stored_quote.pricing_provenance["appliedSurchargeRules"] == [
        {
            "surchargeRuleId": stored_quote.pricing_provenance["appliedSurchargeRules"][0]["surchargeRuleId"],
            "surchargeType": "BAF",
            "description": "Bunker Adjustment Factor (BAF)",
            "currency": "USD",
            "unitAmount": 80.0,
            "totalAmount": 240.0,
            "surchargeRuleVersion": 1,
            "portCode": None,
            "portScope": None,
            "weightThresholdKgPerTeu": None,
            "validFrom": None,
            "validTo": None,
        },
        {
            "surchargeRuleId": stored_quote.pricing_provenance["appliedSurchargeRules"][1]["surchargeRuleId"],
            "surchargeType": "PORT_CONGESTION",
            "description": "Port Congestion Surcharge - Destination USNYC",
            "currency": "USD",
            "unitAmount": 150.0,
            "totalAmount": 450.0,
            "surchargeRuleVersion": 1,
            "portCode": "USNYC",
            "portScope": "DESTINATION",
            "weightThresholdKgPerTeu": None,
            "validFrom": None,
            "validTo": None,
        },
        {
            "surchargeRuleId": stored_quote.pricing_provenance["appliedSurchargeRules"][2]["surchargeRuleId"],
            "surchargeType": "PEAK_SEASON",
            "description": "Peak Season Surcharge",
            "currency": "USD",
            "unitAmount": 120.0,
            "totalAmount": 360.0,
            "surchargeRuleVersion": 1,
            "portCode": None,
            "portScope": None,
            "weightThresholdKgPerTeu": None,
            "validFrom": "2026-08-01",
            "validTo": "2026-09-30",
        },
    ]
    assert stored_quote.idempotency_key is None
    assert stored_quote.schedule_snapshot == {
        "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        "originPort": "NLRTM",
        "destinationPort": "USNYC",
        "departureDate": "2026-08-18",
    }

    with session_factory() as session:
        stored_event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == response.json()["id"],
                OutboxEvent.event_type == "quote.created",
            )
        )

    assert stored_event is not None
    assert stored_event.aggregate_type == "quote"
    assert stored_event.event_version == 1
    assert stored_event.payload["quoteId"] == response.json()["id"]
    assert stored_event.payload["quoteReference"] == response.json()["quoteReference"]
    assert stored_event.payload["lifecycleState"] == "ISSUED"
    assert stored_event.payload["pricingProvenance"] == stored_quote.pricing_provenance


def test_create_quote_can_return_a_requested_currency_with_fx_provenance(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "currency": "EUR",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "quoteReference": response.json()["quoteReference"],
        "validUntil": response.json()["validUntil"],
        "currency": "EUR",
        "sourceCurrency": "USD",
        "responseCurrency": "EUR",
        "lifecycleState": "ISSUED",
        "approvalReasons": [],
        "approvalDecision": None,
        "fx": _fx_snapshot(currency="EUR", rate=0.92),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 1", "amount": 874.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 73.6},
            {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 138.0},
            {"description": "Peak Season Surcharge", "amount": 110.4},
        ],
        "sourceTotalAmount": 1300.0,
        "totalAmount": 1196.0,
    }

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.currency == "EUR"
    assert stored_quote.source_currency == "USD"
    assert stored_quote.fx_snapshot == _fx_snapshot(currency="EUR", rate=0.92)
    assert stored_quote.pricing_provenance["responseCurrency"] == "EUR"
    assert stored_quote.pricing_provenance["sourceTotalAmount"] == 1300.0


def test_create_quote_increments_quote_reference_sequence(client) -> None:
    test_client, _ = client

    first_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    second_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "7a59721c-cd5d-4d9f-86a0-9aa9f7f6c47b",
            "equipment": [{"type": "40FT_HC", "quantity": 1}],
            "cargoWeightKg": 15000,
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["quoteReference"].endswith("-00001")
    assert second_response.json()["quoteReference"].endswith("-00002")


def test_create_quote_returns_404_for_unknown_schedule(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "missing-schedule",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 10000,
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Schedule not found"}


def test_create_quote_rejects_unsupported_requested_currency(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 10000,
            "currency": "JPY",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported currency: JPY"}


def test_create_quote_uses_schedule_provider_dependency(client) -> None:
    test_client, _ = client

    class StubScheduleProvider:
        def get_schedule(self, schedule_id: str) -> Schedule | None:
            if schedule_id != "provider-schedule":
                return None

            return Schedule(
                schedule_id=schedule_id,
                origin_port="NLRTM",
                destination_port="USNYC",
                departure_date=datetime(2026, 8, 18).date(),
            )

    app.dependency_overrides[get_schedule_provider] = lambda: StubScheduleProvider()

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "provider-schedule",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 950.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
        {"description": "Peak Season Surcharge", "amount": 120.0},
    ]


def test_create_quote_returns_400_when_rate_table_is_missing_for_schedule(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "1ce1ab21-9d58-4a6d-b867-afc93098352f",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 10000,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "No rate available for 20FT on selected schedule"}


def test_create_quote_applies_baf_heavy_cargo_and_peak_season_surcharges(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 25000,
        },
    )

    assert response.status_code == 201
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 950.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
        {"description": "Heavy Cargo Surcharge", "amount": 200.0},
        {"description": "Peak Season Surcharge", "amount": 120.0},
    ]
    assert response.json()["totalAmount"] == 1500.0


def test_create_quote_uses_customer_contract_pricing_and_waives_contract_surcharges(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 700.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
    ]
    assert response.json()["totalAmount"] == 930.0

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.customer_id == "cust-acme"
    assert stored_quote.account_id is None
    assert stored_quote.contract_id == "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001"
    assert stored_quote.pricing_basis == PricingBasis.CONTRACT
    assert stored_quote.pricing_provenance["contract"] == {
        "contractId": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001",
        "matchType": "CUSTOMER",
        "waivedSurchargeTypes": ["PEAK_SEASON"],
    }


def test_create_quote_prefers_account_contract_over_customer_contract(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "accountId": "acct-acme-premium",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 650.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
    ]
    assert response.json()["totalAmount"] == 800.0

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.contract_id == "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002"
    assert stored_quote.pricing_basis == PricingBasis.CONTRACT
    assert stored_quote.pricing_provenance["contract"] == {
        "contractId": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002",
        "matchType": "ACCOUNT",
        "waivedSurchargeTypes": ["BAF", "PEAK_SEASON"],
    }


def test_create_quote_matches_account_contract_when_only_account_context_is_provided(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "accountId": "acct-acme-premium",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["totalAmount"] == 800.0

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.contract_id == "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002"


def test_create_quote_returns_different_customer_prices_for_same_shipment(client) -> None:
    test_client, _ = client

    acme_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    globex_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-globex",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert acme_response.status_code == 201
    assert globex_response.status_code == 201
    assert acme_response.json()["totalAmount"] == 930.0
    assert globex_response.json()["totalAmount"] == 1020.0


def test_create_quote_market_hint_uses_approved_market_rate_and_persists_trace(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "pricingModeHint": "MARKET",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 1085.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
        {"description": "Peak Season Surcharge", "amount": 120.0},
    ]
    assert response.json()["totalAmount"] == 1435.0

    quote_id = response.json()["id"]
    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote_id))

    assert stored_quote is not None
    assert stored_quote.pricing_basis == PricingBasis.MARKET
    assert stored_quote.market_source == "approved-spot-market-feed"
    assert stored_quote.optimization_trace["decision"] == "CLIENT_HINT_MARKET"
    assert stored_quote.optimization_trace["selectedPricingBasis"] == PricingBasis.MARKET.value
    assert stored_quote.pricing_provenance["marketSource"] == "approved-spot-market-feed"
    assert stored_quote.pricing_provenance["baseRateRules"][0] == {
        "marketRateSnapshotId": "market-nlrtm-usnyc-20ft",
        "equipmentType": "20FT",
        "quantity": 1,
        "currency": "USD",
        "unitAmount": 1085.0,
        "totalAmount": 1085.0,
        "marketSource": "approved-spot-market-feed",
        "sourceReference": "spot-quote-2026-05-05-nlrtm-usnyc-20ft",
        "capturedAt": "2026-05-05T12:00:00+00:00",
        "approvedAt": "2026-05-06T09:30:00+00:00",
        "capacityPressureIndex": 0.62,
        "utilizationIndex": 0.81,
        "seasonalityIndex": 0.58,
        "validFrom": "2026-08-01",
        "validTo": "2026-08-31",
    }

    explain_response = test_client.get(f"/quotes/{quote_id}/explain")

    assert explain_response.status_code == 200
    assert explain_response.json()["pricingBasis"] == PricingBasis.MARKET.value
    assert explain_response.json()["marketSource"] == "approved-spot-market-feed"
    assert explain_response.json()["optimizationTrace"]["decision"] == "CLIENT_HINT_MARKET"


def test_create_quote_market_hint_falls_back_to_contract_when_market_is_unavailable(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        snapshots = session.scalars(select(MarketRateSnapshot)).all()
        for snapshot in snapshots:
            snapshot.valid_to = datetime(2026, 7, 31, tzinfo=timezone.utc).date()
        session.commit()

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "pricingModeHint": "MARKET",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["totalAmount"] == 930.0

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.pricing_basis == PricingBasis.CONTRACT
    assert stored_quote.optimization_trace["decision"] == "MARKET_UNAVAILABLE_FALLBACK"
    assert stored_quote.optimization_trace["fallbackPricingBasis"] == PricingBasis.CONTRACT.value


def test_create_quote_can_return_ordered_alternative_pricing_options(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "includeAlternativeOptions": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    primary = payload["options"]["primary"]
    alternatives = payload["options"]["alternatives"]

    assert payload["totalAmount"] == 930.0
    assert primary["pricingBasis"] == PricingBasis.CONTRACT.value
    assert primary["totalAmount"] == 930.0
    assert primary["sourceTotalAmount"] == 930.0
    assert primary["pricingProvenance"]["pricingBasis"] == PricingBasis.CONTRACT.value
    assert primary["pricingProvenance"]["baseRateRules"][0]["equipmentType"] == "20FT"
    assert primary["bookability"] == {
        "bookable": True,
        "status": "ACTIVE",
        "reason": "VALIDITY_WINDOW_OPEN",
        "expired": False,
        "validUntil": primary["bookability"]["validUntil"],
    }
    assert primary["contractId"] == "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001"

    assert [option["pricingBasis"] for option in alternatives] == [
        PricingBasis.PUBLIC_TARIFF.value,
        PricingBasis.MARKET.value,
    ]
    assert [option["totalAmount"] for option in alternatives] == [1300.0, 1435.0]

    public_option = alternatives[0]
    assert public_option["pricingProvenance"]["pricingBasis"] == PricingBasis.PUBLIC_TARIFF.value
    assert public_option["bookability"]["bookable"] is True

    market_option = alternatives[1]
    assert market_option["marketSource"] == "approved-spot-market-feed"
    assert market_option["pricingProvenance"]["marketSource"] == "approved-spot-market-feed"
    assert market_option["pricingProvenance"]["baseRateRules"][0]["marketRateSnapshotId"] == "market-nlrtm-usnyc-20ft"
    assert market_option["bookability"]["bookable"] is True


def test_create_quote_can_limit_ordered_alternative_pricing_options(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "includeAlternativeOptions": True,
            "maxAlternativeOptions": 1,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["options"]["primary"]["pricingBasis"] == PricingBasis.CONTRACT.value
    assert [option["pricingBasis"] for option in payload["options"]["alternatives"]] == [
        PricingBasis.PUBLIC_TARIFF.value
    ]
    assert [option["totalAmount"] for option in payload["options"]["alternatives"]] == [1300.0]


def test_create_quote_max_alternative_options_does_not_enable_options(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "maxAlternativeOptions": 1,
        },
    )

    assert response.status_code == 201
    assert "options" not in response.json()


@pytest.mark.parametrize("max_alternative_options", [0, 11])
def test_create_quote_rejects_invalid_max_alternative_options(client, max_alternative_options: int) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "includeAlternativeOptions": True,
            "maxAlternativeOptions": max_alternative_options,
        },
    )

    assert response.status_code == 422
    assert any(error["loc"] == ["body", "maxAlternativeOptions"] for error in response.json()["detail"])


def test_create_quote_holds_market_quote_for_approval_when_market_risk_guardrails_are_exceeded(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        snapshot = session.scalar(select(MarketRateSnapshot).where(MarketRateSnapshot.id == "market-nlrtm-usnyc-20ft"))
        assert snapshot is not None
        snapshot.utilization_index = Decimal("0.94")
        snapshot.capacity_pressure_index = Decimal("0.88")
        session.commit()

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "pricingModeHint": "MARKET",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert response.json()["lifecycleState"] == "PENDING_APPROVAL"
    assert [reason["code"] for reason in response.json()["approvalReasons"]] == [
        "MARKET_CAPACITY_PRESSURE_THRESHOLD_EXCEEDED",
        "MARKET_UTILIZATION_THRESHOLD_EXCEEDED",
    ]
    assert response.json()["approvalDecision"] is None

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))
        created_event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == response.json()["id"],
                OutboxEvent.event_type == "quote.created",
            )
        )

    assert stored_quote is not None
    assert stored_quote.lifecycle_state == QuoteLifecycleState.PENDING_APPROVAL
    assert [reason["code"] for reason in stored_quote.approval_reasons] == [
        "MARKET_CAPACITY_PRESSURE_THRESHOLD_EXCEEDED",
        "MARKET_UTILIZATION_THRESHOLD_EXCEEDED",
    ]
    assert created_event is not None
    assert created_event.payload["lifecycleState"] == "PENDING_APPROVAL"
    assert created_event.payload["approvalDecision"] is None


def test_quote_approval_decision_approves_pending_quote_without_repricing(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        snapshot = session.scalar(select(MarketRateSnapshot).where(MarketRateSnapshot.id == "market-nlrtm-usnyc-20ft"))
        assert snapshot is not None
        snapshot.utilization_index = Decimal("0.94")
        session.commit()

    create_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "pricingModeHint": "MARKET",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    quote_id = create_response.json()["id"]

    approval_response = test_client.post(
        f"/quotes/{quote_id}/approval-decisions",
        headers={"X-Actor": "pricing.manager@quotes"},
        json={"decision": "APPROVE", "note": "Market conditions reviewed and accepted."},
    )

    assert approval_response.status_code == 200
    assert approval_response.json()["lifecycleState"] == "APPROVED"
    assert approval_response.json()["approvalDecision"]["decision"] == "APPROVE"
    assert approval_response.json()["approvalDecision"]["actor"] == "pricing.manager@quotes"
    assert approval_response.json()["approvalDecision"]["note"] == "Market conditions reviewed and accepted."

    bookability_response = test_client.get(f"/quotes/{quote_id}/bookability")

    assert bookability_response.status_code == 200
    assert bookability_response.json()["bookable"] is True
    assert bookability_response.json()["status"] == "ACTIVE"

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote_id))
        approved_event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == quote_id,
                OutboxEvent.event_type == "quote.approved",
            )
        )

    assert stored_quote is not None
    assert stored_quote.lifecycle_state == QuoteLifecycleState.APPROVED
    assert stored_quote.pricing_provenance["baseRateRules"][0]["marketRateSnapshotId"] == "market-nlrtm-usnyc-20ft"
    assert approved_event is not None
    assert approved_event.payload["lifecycleState"] == "APPROVED"
    assert approved_event.payload["approvalDecision"]["decision"] == "APPROVE"


def test_quote_approval_decision_can_reject_pending_quote(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        snapshot = session.scalar(select(MarketRateSnapshot).where(MarketRateSnapshot.id == "market-nlrtm-usnyc-20ft"))
        assert snapshot is not None
        snapshot.utilization_index = Decimal("0.94")
        session.commit()

    create_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "pricingModeHint": "MARKET",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    quote_id = create_response.json()["id"]

    rejection_response = test_client.post(
        f"/quotes/{quote_id}/approval-decisions",
        headers={"X-Actor": "pricing.manager@quotes"},
        json={"decision": "REJECT", "note": "Margin does not support this offer."},
    )

    assert rejection_response.status_code == 200
    assert rejection_response.json()["lifecycleState"] == "REJECTED"
    assert rejection_response.json()["approvalDecision"]["decision"] == "REJECT"

    bookability_response = test_client.get(f"/quotes/{quote_id}/bookability")

    assert bookability_response.status_code == 200
    assert bookability_response.json() == {
        "quoteId": create_response.json()["quoteReference"],
        "bookable": False,
        "status": "REJECTED",
        "reason": "APPROVAL_REJECTED",
        "expired": False,
        "validUntil": create_response.json()["validUntil"],
    }


def test_quote_approval_decision_requires_actor_header(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        quote = Quote(
            quote_reference="QTE-2026-00990",
            lifecycle_state=QuoteLifecycleState.PENDING_APPROVAL,
            schedule_id="df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            schedule_snapshot={"scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274"},
            equipment=[{"type": "20FT", "quantity": 1}],
            cargo_weight_kg=Decimal("18000.00"),
            currency="USD",
            source_currency="USD",
            pricing_basis=PricingBasis.MARKET,
            pricing_provenance={"pricingBasis": PricingBasis.MARKET.value, "sourceTotalAmount": 1085.0},
            approval_reasons=[{"code": "MARKET_UTILIZATION_THRESHOLD_EXCEEDED"}],
            fx_snapshot=_fx_snapshot(),
            rounding_policy="LINE_ITEM_HALF_UP_2DP",
            line_items=[{"description": "Ocean Freight - 20FT x 1", "amount": 1085.0}],
            total_amount=Decimal("1085.00"),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

    response = test_client.post(f"/quotes/{quote.id}/approval-decisions", json={"decision": "APPROVE"})

    assert response.status_code == 400
    assert response.json() == {"detail": "X-Actor header is required for quote approval decisions"}


def test_quote_approval_decision_rejects_non_pending_quotes(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    response = test_client.post(
        f"/quotes/{quote.id}/approval-decisions",
        headers={"X-Actor": "pricing.manager@quotes"},
        json={"decision": "APPROVE"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only pending approval quotes can be decided"}


def test_create_quote_auto_strategy_can_select_market(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        strategy = session.scalar(select(PricingStrategyVersion).where(PricingStrategyVersion.id == "strategy-market-optimization-v1"))
        assert strategy is not None
        strategy.rules = {
            "capacityPressureThreshold": 0.6,
            "utilizationThreshold": 0.8,
            "seasonalityThreshold": 0.5,
            "selectionMode": "ANY_SIGNAL",
        }
        session.commit()

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.pricing_basis == PricingBasis.MARKET
    assert stored_quote.optimization_trace["decision"] == "STRATEGY_SELECTED_MARKET"
    assert stored_quote.optimization_trace["strategy"]["rules"][0]["matched"] is True


def test_reprice_existing_quote_preserves_original_and_reports_structured_variance(client) -> None:
    test_client, session_factory = client

    original_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "currency": "EUR",
        },
    )
    assert original_response.status_code == 201

    rate_response = test_client.post(
        "/admin/rate-tables",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "equipmentType": "20FT",
            "baseRateUsd": 1110,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    )
    assert rate_response.status_code == 201
    activate_rate_response = test_client.post(
        f"/admin/rate-tables/{rate_response.json()['id']}/activate",
        headers={"X-Actor": "pricing.manager@quotes"},
    )
    assert activate_rate_response.status_code == 200

    surcharge_response = test_client.post(
        "/admin/surcharge-rules",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "surchargeType": "PORT_CONGESTION",
            "description": "Port Congestion Surcharge - Destination USNYC",
            "amountUsd": 210,
            "currency": "USD",
            "portCode": "USNYC",
            "portScope": "DESTINATION",
        },
    )
    assert surcharge_response.status_code == 201
    activate_surcharge_response = test_client.post(
        f"/admin/surcharge-rules/{surcharge_response.json()['id']}/activate",
        headers={"X-Actor": "pricing.manager@quotes"},
    )
    assert activate_surcharge_response.status_code == 200

    with session_factory() as session:
        eur_rate = session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency == "USD",
                ExchangeRate.quote_currency == "EUR",
            )
        )
        assert eur_rate is not None
        eur_rate.rate = Decimal("0.95")
        eur_rate.observed_at = datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc)
        eur_rate.reference_data_version = "seed-fx-2026-05-07"
        session.commit()

    reprice_response = test_client.post(
        f"/quotes/{original_response.json()['id']}/reprice",
        json={"trigger": "COMMERCIAL_REFRESH"},
    )

    assert reprice_response.status_code == 201
    assert reprice_response.json()["id"] != original_response.json()["id"]
    assert reprice_response.json()["quoteReference"] != original_response.json()["quoteReference"]
    assert reprice_response.json()["repricedFromQuoteId"] == original_response.json()["id"]
    assert reprice_response.json()["repricedFromQuoteReference"] == original_response.json()["quoteReference"]
    assert reprice_response.json()["repricingTrigger"] == "COMMERCIAL_REFRESH"
    assert reprice_response.json()["totalAmount"] == 1444.0
    assert reprice_response.json()["varianceSummary"] == {
        "direction": "HIGHER",
        "totalAmount": {
            "original": 1196.0,
            "repriced": 1444.0,
            "delta": 248.0,
            "changed": True,
        },
        "sourceTotalAmount": {
            "original": 1300.0,
            "repriced": 1520.0,
            "delta": 220.0,
            "changed": True,
        },
        "baseRate": {
            "original": 950.0,
            "repriced": 1110.0,
            "delta": 160.0,
            "changed": True,
        },
        "surcharges": {
            "original": 350.0,
            "repriced": 410.0,
            "delta": 60.0,
            "changed": True,
        },
        "fx": {
            "changed": True,
            "original": _fx_snapshot(currency="EUR", rate=0.92),
            "repriced": {
                **_fx_snapshot(currency="EUR", rate=0.95),
                "observedAt": "2026-05-07T10:00:00+00:00",
                "referenceDataVersion": "seed-fx-2026-05-07",
            },
        },
        "marketInputs": {
            "changed": False,
            "original": {
                "pricingBasis": "PUBLIC_TARIFF",
                "marketSource": None,
                "marketRateSnapshotIds": [],
                "capacityPressureIndex": None,
                "utilizationIndex": None,
                "seasonalityIndex": None,
            },
            "repriced": {
                "pricingBasis": "PUBLIC_TARIFF",
                "marketSource": None,
                "marketRateSnapshotIds": [],
                "capacityPressureIndex": None,
                "utilizationIndex": None,
                "seasonalityIndex": None,
            },
        },
        "optimizationInputs": {
            "changed": False,
            "original": {
                "pricingModeHint": "AUTO",
                "decision": None,
                "selectedPricingBasis": None,
                "fallbackPricingBasis": None,
                "strategyId": None,
                "strategyName": None,
                "strategyVersion": None,
            },
            "repriced": {
                "pricingModeHint": "AUTO",
                "decision": None,
                "selectedPricingBasis": None,
                "fallbackPricingBasis": None,
                "strategyId": None,
                "strategyName": None,
                "strategyVersion": None,
            },
        },
    }

    original_quote_response = test_client.get(f"/quotes/{original_response.json()['id']}")
    assert original_quote_response.status_code == 200
    assert original_quote_response.json()["totalAmount"] == 1196.0
    assert "varianceSummary" not in original_quote_response.json()

    explain_response = test_client.get(f"/quotes/{reprice_response.json()['id']}/explain")
    assert explain_response.status_code == 200
    assert explain_response.json()["repricedFromQuoteId"] == original_response.json()["id"]
    assert explain_response.json()["varianceSummary"]["baseRate"]["delta"] == 160.0

    with session_factory() as session:
        original_quote = session.scalar(select(Quote).where(Quote.id == original_response.json()["id"]))
        repriced_quote = session.scalar(select(Quote).where(Quote.id == reprice_response.json()["id"]))

    assert original_quote is not None
    assert repriced_quote is not None
    assert float(original_quote.total_amount) == 1196.0
    assert repriced_quote.repriced_from_quote_id == original_quote.id
    assert repriced_quote.repricing_trigger == "COMMERCIAL_REFRESH"
    assert repriced_quote.variance_summary["direction"] == "HIGHER"


def test_admin_rate_table_draft_can_be_updated_and_activated(client) -> None:
    test_client, session_factory = client

    create_response = test_client.post(
        "/admin/rate-tables",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "equipmentType": "20FT",
            "baseRateUsd": 990,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["version"] == 2
    assert create_response.json()["isActive"] is False
    assert create_response.json()["createdBy"] == "pricing.ops@quotes"
    assert create_response.json()["activatedAt"] is None

    update_response = test_client.patch(
        f"/admin/rate-tables/{create_response.json()['id']}",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={"baseRateUsd": 1000},
    )

    assert update_response.status_code == 200
    assert update_response.json()["baseRateUsd"] == 1000.0

    activate_response = test_client.post(
        f"/admin/rate-tables/{create_response.json()['id']}/activate",
        headers={"X-Actor": "pricing.manager@quotes"},
    )

    assert activate_response.status_code == 200
    assert activate_response.json()["isActive"] is True
    assert activate_response.json()["activatedBy"] == "pricing.manager@quotes"

    quote_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert quote_response.status_code == 201
    assert quote_response.json()["lineItems"][0] == {"description": "Ocean Freight - 20FT x 1", "amount": 1000.0}
    assert quote_response.json()["totalAmount"] == 1350.0

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote_response.json()["id"]))
        superseded_rate = session.scalar(
            select(RateTable).where(
                RateTable.origin_port == "NLRTM",
                RateTable.destination_port == "USNYC",
                RateTable.equipment_type == EquipmentType.TWENTY_FT,
                RateTable.version == 1,
            )
        )

    assert stored_quote is not None
    assert stored_quote.pricing_provenance["baseRateRules"][0]["rateVersion"] == 2
    assert superseded_rate is not None
    assert superseded_rate.is_active is False


def test_admin_rate_table_changes_are_recorded_in_audit_trail(client) -> None:
    test_client, session_factory = client

    create_response = test_client.post(
        "/admin/rate-tables",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "equipmentType": "40FT_HC",
            "baseRateUsd": 1600,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    )
    rate_table_id = create_response.json()["id"]

    update_response = test_client.patch(
        f"/admin/rate-tables/{rate_table_id}",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={"baseRateUsd": 1615},
    )
    activate_response = test_client.post(
        f"/admin/rate-tables/{rate_table_id}/activate",
        headers={"X-Actor": "pricing.manager@quotes"},
    )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert activate_response.status_code == 200

    audit_response = test_client.get(
        "/admin/commercial-change-events",
        params={"resourceType": "RATE_TABLE", "resourceId": rate_table_id},
    )

    assert audit_response.status_code == 200
    assert [event["action"] for event in audit_response.json()["events"]] == ["ACTIVATED", "UPDATED", "CREATED"]
    assert audit_response.json()["events"][0]["actor"] == "pricing.manager@quotes"
    assert audit_response.json()["events"][0]["snapshot"]["isActive"] is True

    with session_factory() as session:
        stored_events = session.scalars(
            select(CommercialChangeEvent)
            .where(CommercialChangeEvent.resource_id == rate_table_id)
            .order_by(CommercialChangeEvent.occurred_at)
        ).all()

    assert [event.action for event in stored_events] == [
        CommercialChangeAction.CREATED,
        CommercialChangeAction.UPDATED,
        CommercialChangeAction.ACTIVATED,
    ]
    assert all(event.resource_type == CommercialChangeResourceType.RATE_TABLE for event in stored_events)


def test_admin_rate_table_changes_are_published_to_outbox(client) -> None:
    test_client, session_factory = client

    create_response = test_client.post(
        "/admin/rate-tables",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "equipmentType": "40FT",
            "baseRateUsd": 1505,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    )
    rate_table_id = create_response.json()["id"]

    update_response = test_client.patch(
        f"/admin/rate-tables/{rate_table_id}",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={"baseRateUsd": 1510},
    )
    activate_response = test_client.post(
        f"/admin/rate-tables/{rate_table_id}/activate",
        headers={"X-Actor": "pricing.manager@quotes"},
    )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert activate_response.status_code == 200

    outbox_response = test_client.get(
        "/admin/outbox-events",
        params={"aggregateType": "rate_table", "eventType": "rate.updated"},
    )

    assert outbox_response.status_code == 200
    matching_events = [event for event in outbox_response.json()["events"] if event["aggregateId"] == rate_table_id]
    assert [event["payload"]["action"] for event in matching_events] == ["CREATED", "UPDATED", "ACTIVATED"]
    assert matching_events[-1]["payload"]["actor"] == "pricing.manager@quotes"
    assert matching_events[-1]["payload"]["resourceVersion"] == 2

    with session_factory() as session:
        stored_events = session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_id == rate_table_id, OutboxEvent.event_type == "rate.updated")
            .order_by(OutboxEvent.occurred_at)
        ).all()

    assert len(stored_events) == 3
    assert stored_events[0].aggregate_type == "rate_table"
    assert stored_events[0].payload["snapshot"]["baseRateUsd"] == 1505.0
    assert stored_events[1].payload["snapshot"]["baseRateUsd"] == 1510.0


def test_admin_cannot_patch_an_active_rate_table(client) -> None:
    test_client, session_factory = client

    with session_factory() as session:
        active_rate = session.scalar(select(RateTable).where(RateTable.is_active.is_(True)).limit(1))

    assert active_rate is not None
    response = test_client.patch(
        f"/admin/rate-tables/{active_rate.id}",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={"baseRateUsd": 1001},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Active rate tables cannot be edited; create a new draft version"}


def test_admin_surcharge_rule_draft_can_be_updated_and_activated(client) -> None:
    test_client, session_factory = client

    create_response = test_client.post(
        "/admin/surcharge-rules",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "surchargeType": "PORT_CONGESTION",
            "description": "Port Congestion Surcharge - Destination USNYC",
            "amountUsd": 165,
            "currency": "USD",
            "portCode": "USNYC",
            "portScope": "DESTINATION",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["version"] == 2
    assert create_response.json()["isActive"] is False

    update_response = test_client.patch(
        f"/admin/surcharge-rules/{create_response.json()['id']}",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={"amountUsd": 175},
    )

    assert update_response.status_code == 200
    assert update_response.json()["amountUsd"] == 175.0

    activate_response = test_client.post(
        f"/admin/surcharge-rules/{create_response.json()['id']}/activate",
        headers={"X-Actor": "pricing.manager@quotes"},
    )

    assert activate_response.status_code == 200
    assert activate_response.json()["isActive"] is True

    quote_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert quote_response.status_code == 201
    assert quote_response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 950.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 175.0},
        {"description": "Peak Season Surcharge", "amount": 120.0},
    ]
    assert quote_response.json()["totalAmount"] == 1325.0

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote_response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.pricing_provenance["appliedSurchargeRules"][1]["surchargeRuleVersion"] == 2


def test_admin_quote_preview_can_use_draft_rate_and_surcharge_versions(client) -> None:
    test_client, session_factory = client

    rate_response = test_client.post(
        "/admin/rate-tables",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "equipmentType": "20FT",
            "baseRateUsd": 1110,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    )
    surcharge_response = test_client.post(
        "/admin/surcharge-rules",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "surchargeType": "PORT_CONGESTION",
            "description": "Port Congestion Surcharge - Destination USNYC",
            "amountUsd": 210,
            "currency": "USD",
            "portCode": "USNYC",
            "portScope": "DESTINATION",
        },
    )

    preview_response = test_client.post(
        "/admin/quote-preview",
        headers={"X-Actor": "pricing.ops@quotes"},
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "currency": "EUR",
            "rateTableIds": [rate_response.json()["id"]],
            "surchargeRuleIds": [surcharge_response.json()["id"]],
        },
    )

    assert rate_response.status_code == 201
    assert surcharge_response.status_code == 201
    assert preview_response.status_code == 200
    assert preview_response.json() == {
        "currency": "EUR",
        "sourceCurrency": "USD",
        "responseCurrency": "EUR",
        "fx": _fx_snapshot(currency="EUR", rate=0.92),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "pricingBasis": "PUBLIC_TARIFF",
        "pricingProvenance": {
            "pricingBasis": "PUBLIC_TARIFF",
            "referenceDataVersion": REFERENCE_DATA_VERSION,
            "sourceCurrency": "USD",
            "responseCurrency": "EUR",
            "sourceTotalAmount": 1520.0,
            "currencyConversion": {
                **_fx_snapshot(currency="EUR", rate=0.92),
                "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
                "conversionLevel": "LINE_ITEM",
            },
            "baseRateRules": [
                {
                    "rateTableId": rate_response.json()["id"],
                    "equipmentType": "20FT",
                    "quantity": 1,
                    "currency": "USD",
                    "unitAmount": 1110.0,
                    "totalAmount": 1110.0,
                    "rateVersion": 2,
                    "validFrom": "2026-04-01",
                    "validTo": "2026-12-31",
                }
            ],
            "appliedSurchargeRules": [
                {
                    "surchargeRuleId": preview_response.json()["pricingProvenance"]["appliedSurchargeRules"][0]["surchargeRuleId"],
                    "surchargeType": "BAF",
                    "description": "Bunker Adjustment Factor (BAF)",
                    "currency": "USD",
                    "unitAmount": 80.0,
                    "totalAmount": 80.0,
                    "surchargeRuleVersion": 1,
                    "portCode": None,
                    "portScope": None,
                    "weightThresholdKgPerTeu": None,
                    "validFrom": None,
                    "validTo": None,
                },
                {
                    "surchargeRuleId": surcharge_response.json()["id"],
                    "surchargeType": "PORT_CONGESTION",
                    "description": "Port Congestion Surcharge - Destination USNYC",
                    "currency": "USD",
                    "unitAmount": 210.0,
                    "totalAmount": 210.0,
                    "surchargeRuleVersion": 2,
                    "portCode": "USNYC",
                    "portScope": "DESTINATION",
                    "weightThresholdKgPerTeu": None,
                    "validFrom": None,
                    "validTo": None,
                },
                {
                    "surchargeRuleId": preview_response.json()["pricingProvenance"]["appliedSurchargeRules"][2]["surchargeRuleId"],
                    "surchargeType": "PEAK_SEASON",
                    "description": "Peak Season Surcharge",
                    "currency": "USD",
                    "unitAmount": 120.0,
                    "totalAmount": 120.0,
                    "surchargeRuleVersion": 1,
                    "portCode": None,
                    "portScope": None,
                    "weightThresholdKgPerTeu": None,
                    "validFrom": "2026-08-01",
                    "validTo": "2026-09-30",
                },
            ],
            "validityPolicy": _public_tariff_pricing_provenance()["validityPolicy"],
        },
        "sourceTotalAmount": 1520.0,
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 1", "amount": 1021.2},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 73.6},
            {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 193.2},
            {"description": "Peak Season Surcharge", "amount": 110.4},
        ],
        "totalAmount": 1398.4,
    }

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Quote)) == 0
        assert session.scalar(select(func.count()).select_from(SurchargeRule).where(SurchargeRule.id == surcharge_response.json()["id"])) == 1


def test_admin_outbox_replay_advances_named_consumer_checkpoint(client) -> None:
    test_client, session_factory = client

    quote_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    assert quote_response.status_code == 201

    first_replay = test_client.post(
        "/admin/outbox-consumers/booking-cache/replay",
        headers={"X-Actor": "booking.sync@quotes"},
        json={"fromStart": True, "batchSize": 1, "eventTypes": ["quote.created"]},
    )
    second_replay = test_client.post(
        "/admin/outbox-consumers/booking-cache/replay",
        headers={"X-Actor": "booking.sync@quotes"},
        json={"batchSize": 1, "eventTypes": ["quote.created"]},
    )

    assert first_replay.status_code == 200
    assert first_replay.json()["replayedCount"] == 1
    assert first_replay.json()["events"][0]["eventType"] == "quote.created"
    assert second_replay.status_code == 200
    assert second_replay.json()["replayedCount"] == 0

    with session_factory() as session:
        checkpoint = session.get(OutboxConsumerCheckpoint, "booking-cache")

    assert checkpoint is not None
    assert checkpoint.processed_events_count == 1
    assert checkpoint.last_replayed_by == "booking.sync@quotes"


def test_admin_impact_analysis_persists_schedule_and_contract_results(client) -> None:
    test_client, session_factory = client

    public_quote_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    contract_quote_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert public_quote_response.status_code == 201
    assert contract_quote_response.status_code == 201

    schedule_response = test_client.post(
        "/admin/impact-analyses",
        headers={"X-Actor": "ops@quotes"},
        json={
            "changeType": "SCHEDULE",
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        },
    )
    contract_response = test_client.post(
        "/admin/impact-analyses",
        headers={"X-Actor": "ops@quotes"},
        json={
            "changeType": "CONTRACT",
            "contractId": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001",
        },
    )

    assert schedule_response.status_code == 201
    assert schedule_response.json()["changeType"] == "SCHEDULE"
    assert schedule_response.json()["summary"]["affectedCount"] == 2
    assert {quote["quoteId"] for quote in schedule_response.json()["summary"]["affectedQuotes"]} == {
        public_quote_response.json()["id"],
        contract_quote_response.json()["id"],
    }

    assert contract_response.status_code == 201
    assert contract_response.json()["changeType"] == "CONTRACT"
    assert contract_response.json()["summary"]["affectedCount"] == 1
    assert contract_response.json()["summary"]["affectedQuotes"][0]["quoteId"] == contract_quote_response.json()["id"]
    assert contract_response.json()["summary"]["affectedQuotes"][0]["contractId"] == "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001"

    get_response = test_client.get(f"/admin/impact-analyses/{contract_response.json()['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["summary"]["affectedCount"] == 1

    with session_factory() as session:
        stored_runs = session.scalars(select(ImpactAnalysisRun).order_by(ImpactAnalysisRun.created_at)).all()

    assert len(stored_runs) == 2
    assert stored_runs[0].summary["affectedCount"] == 2
    assert stored_runs[1].summary["affectedCount"] == 1


def test_admin_requires_actor_header_for_managed_commercial_changes(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/admin/rate-tables",
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "equipmentType": "20FT",
            "baseRateUsd": 990,
            "validFrom": "2026-04-01",
            "validTo": "2026-12-31",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "X-Actor header is required for admin commercial data changes"}

    preview_response = test_client.post(
        "/admin/quote-preview",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert preview_response.status_code == 400
    assert preview_response.json() == {"detail": "X-Actor header is required for admin commercial data changes"}


@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        pytest.param(
            {
                "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
                "equipment": [],
                "cargoWeightKg": 10000,
            },
            "equipment",
            id="empty-equipment",
        ),
        pytest.param(
            {
                "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
                "equipment": [{"type": "20FT", "quantity": 0}],
                "cargoWeightKg": 10000,
            },
            "quantity",
            id="zero-quantity",
        ),
        pytest.param(
            {
                "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
                "equipment": [{"type": "INVALID", "quantity": 1}],
                "cargoWeightKg": 10000,
            },
            "type",
            id="invalid-equipment-type",
        ),
        pytest.param(
            {
                "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
                "equipment": [{"type": "20FT", "quantity": 1}],
                "cargoWeightKg": 0,
            },
            "cargoWeightKg",
            id="non-positive-cargo-weight",
        ),
    ],
)
def test_create_quote_rejects_invalid_payloads(client, payload: dict[str, object], error_field: str) -> None:
    test_client, _ = client

    response = test_client.post("/quotes", json=payload)

    assert response.status_code == 422
    assert any(error_field in ".".join(str(part) for part in error["loc"]) for error in response.json()["detail"])


def _seed_quote(session_factory: sessionmaker[Session]) -> Quote:
    with session_factory() as session:
        quote = Quote(
            id="53c362b2-1229-4ea5-a24a-9891fb1f509d",
            quote_reference="QTE-2026-00108",
            lifecycle_state=QuoteLifecycleState.ISSUED,
            schedule_id="df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            schedule_snapshot={
                "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
                "originPort": "NLRTM",
                "destinationPort": "USNYC",
                "departureDate": "2026-08-18",
            },
            equipment=[{"type": "20FT", "quantity": 2}],
            cargo_weight_kg=Decimal("18000.00"),
            currency="USD",
            source_currency="USD",
            pricing_basis=PricingBasis.PUBLIC_TARIFF,
            pricing_provenance=_public_tariff_pricing_provenance(),
            approval_reasons=[],
            approval_decision={},
            fx_snapshot=_fx_snapshot(),
            rounding_policy="LINE_ITEM_HALF_UP_2DP",
            idempotency_key="booking-request-42",
            line_items=[
                {"description": "Ocean Freight - 20FT x 2", "amount": 1800.0},
                {"description": "Bunker Adjustment Factor (BAF)", "amount": 160.0},
            ],
            total_amount=Decimal("1960.00"),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        return quote


def _seed_expired_quote(session_factory: sessionmaker[Session]) -> Quote:
    with session_factory() as session:
        quote = Quote(
            id="4f438b27-7bfc-4fa9-8fd1-fc589fb8d9df",
            quote_reference="QTE-2026-00109",
            lifecycle_state=QuoteLifecycleState.EXPIRED,
            schedule_id="df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            schedule_snapshot={
                "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
                "originPort": "NLRTM",
                "destinationPort": "USNYC",
                "departureDate": "2026-08-18",
            },
            equipment=[{"type": "40FT", "quantity": 1}],
            cargo_weight_kg=Decimal("12000.00"),
            currency="USD",
            source_currency="USD",
            pricing_basis=PricingBasis.PUBLIC_TARIFF,
            pricing_provenance={
                "pricingBasis": PricingBasis.PUBLIC_TARIFF.value,
                "referenceDataVersion": REFERENCE_DATA_VERSION,
                "sourceCurrency": "USD",
                "responseCurrency": "USD",
                "sourceTotalAmount": 1400.0,
                "currencyConversion": {
                    **_fx_snapshot(),
                    "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
                    "conversionLevel": "LINE_ITEM",
                },
                "baseRateRules": [
                    {
                        "rateTableId": "rate-40ft-nlrtm-usnyc",
                        "equipmentType": "40FT",
                        "quantity": 1,
                        "currency": "USD",
                        "unitAmount": 1400.0,
                        "totalAmount": 1400.0,
                        "rateVersion": 1,
                        "validFrom": "2026-04-01",
                        "validTo": "2026-12-31",
                    }
                ],
                "appliedSurchargeRules": [],
                "validityPolicy": _public_tariff_pricing_provenance()["validityPolicy"],
            },
            approval_reasons=[],
            approval_decision={},
            fx_snapshot=_fx_snapshot(),
            rounding_policy="LINE_ITEM_HALF_UP_2DP",
            line_items=[{"description": "Ocean Freight - 40FT x 1", "amount": 1400.0}],
            total_amount=Decimal("1400.00"),
            valid_until=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        return quote


def test_get_quote_by_uuid_returns_full_quote(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    response = test_client.get(f"/quotes/{quote.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": quote.id,
        "quoteReference": "QTE-2026-00108",
        "lifecycleState": "ISSUED",
        "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        "scheduleSnapshot": {
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "departureDate": "2026-08-18",
        },
        "equipment": [{"type": "20FT", "quantity": 2}],
        "cargoWeightKg": 18000.0,
        "currency": "USD",
        "sourceCurrency": "USD",
        "responseCurrency": "USD",
        "fx": _fx_snapshot(),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "pricingBasis": "PUBLIC_TARIFF",
        "pricingProvenance": _public_tariff_pricing_provenance(),
        "approvalReasons": [],
        "approvalDecision": None,
        "customerId": None,
        "accountId": None,
        "contractId": None,
        "idempotencyKey": "booking-request-42",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1800.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 160.0},
        ],
        "sourceTotalAmount": 1960.0,
        "totalAmount": 1960.0,
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def test_get_quote_by_reference_returns_full_quote(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    response = test_client.get("/quotes/QTE-2026-00108")

    assert response.status_code == 200
    assert response.json() == {
        "id": quote.id,
        "quoteReference": "QTE-2026-00108",
        "lifecycleState": "ISSUED",
        "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        "scheduleSnapshot": {
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "departureDate": "2026-08-18",
        },
        "equipment": [{"type": "20FT", "quantity": 2}],
        "cargoWeightKg": 18000.0,
        "currency": "USD",
        "sourceCurrency": "USD",
        "responseCurrency": "USD",
        "fx": _fx_snapshot(),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "pricingBasis": "PUBLIC_TARIFF",
        "pricingProvenance": _public_tariff_pricing_provenance(),
        "approvalReasons": [],
        "approvalDecision": None,
        "customerId": None,
        "accountId": None,
        "contractId": None,
        "idempotencyKey": "booking-request-42",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1800.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 160.0},
        ],
        "sourceTotalAmount": 1960.0,
        "totalAmount": 1960.0,
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def test_get_quote_by_quote_reference_returns_full_quote(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    response = test_client.get(f"/quotes/reference/{quote.quote_reference}")

    assert response.status_code == 200
    assert response.json() == {
        "id": quote.id,
        "quoteReference": quote.quote_reference,
        "lifecycleState": "ISSUED",
        "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        "scheduleSnapshot": {
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "departureDate": "2026-08-18",
        },
        "equipment": [{"type": "20FT", "quantity": 2}],
        "cargoWeightKg": 18000.0,
        "currency": "USD",
        "sourceCurrency": "USD",
        "responseCurrency": "USD",
        "fx": _fx_snapshot(),
        "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
        "pricingBasis": "PUBLIC_TARIFF",
        "pricingProvenance": _public_tariff_pricing_provenance(),
        "approvalReasons": [],
        "approvalDecision": None,
        "customerId": None,
        "accountId": None,
        "contractId": None,
        "idempotencyKey": "booking-request-42",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1800.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 160.0},
        ],
        "sourceTotalAmount": 1960.0,
        "totalAmount": 1960.0,
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def test_get_quote_returns_404_when_missing(client) -> None:
    test_client, _ = client

    response = test_client.get("/quotes/missing-quote")

    assert response.status_code == 404
    assert response.json() == {"detail": "Quote not found"}


def test_get_quote_bookability_returns_active_quote_status(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    response = test_client.get(f"/quotes/{quote.quote_reference}/bookability")

    assert response.status_code == 200
    assert response.json() == {
        "quoteId": quote.quote_reference,
        "bookable": True,
        "status": "ACTIVE",
        "reason": "VALIDITY_WINDOW_OPEN",
        "expired": False,
        "validUntil": quote.valid_until.isoformat(),
    }


def test_get_quote_bookability_returns_expired_quote_status(client) -> None:
    test_client, session_factory = client
    quote = _seed_expired_quote(session_factory)

    response = test_client.get(f"/quotes/{quote.id}/bookability")

    assert response.status_code == 200
    assert response.json() == {
        "quoteId": quote.quote_reference,
        "bookable": False,
        "status": "EXPIRED",
        "reason": "VALIDITY_WINDOW_EXPIRED",
        "expired": True,
        "validUntil": quote.valid_until.isoformat(),
    }


def test_get_quote_materializes_expired_lifecycle_and_outbox_event(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote.id))
        assert stored_quote is not None
        stored_quote.valid_until = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()

    response = test_client.get(f"/quotes/{quote.id}")

    assert response.status_code == 200
    assert response.json()["lifecycleState"] == "EXPIRED"

    with session_factory() as session:
        refreshed_quote = session.scalar(select(Quote).where(Quote.id == quote.id))
        expired_event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == quote.id,
                OutboxEvent.event_type == "quote.expired",
            )
        )

    assert refreshed_quote is not None
    assert refreshed_quote.lifecycle_state == QuoteLifecycleState.EXPIRED
    assert expired_event is not None
    assert expired_event.payload["quoteId"] == quote.id
    assert expired_event.payload["lifecycleState"] == "EXPIRED"
    assert expired_event.payload["pricingProvenance"] == quote.pricing_provenance


def test_get_quote_bookability_only_emits_one_expired_event(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote.id))
        assert stored_quote is not None
        stored_quote.valid_until = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()

    first_response = test_client.get(f"/quotes/{quote.id}/bookability")
    second_response = test_client.get(f"/quotes/{quote.id}/bookability")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["status"] == "EXPIRED"
    assert second_response.json()["status"] == "EXPIRED"

    with session_factory() as session:
        expired_events = session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == quote.id,
                OutboxEvent.event_type == "quote.expired",
            )
        ).all()

    assert len(expired_events) == 1


def test_get_quote_bookability_returns_404_when_missing(client) -> None:
    test_client, _ = client

    response = test_client.get("/quotes/missing-quote/bookability")

    assert response.status_code == 404
    assert response.json() == {"detail": "Quote not found"}


def test_validate_quote_rate_coverage_returns_covered_route_details(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes/coverage/validate",
        json={
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "departureDate": "2026-08-18",
            "equipment": [
                {"type": "20FT", "quantity": 2},
                {"type": "40FT_HC", "quantity": 1},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "covered": True,
        "reason": "RATE_AVAILABLE",
        "pricingBasis": "PUBLIC_TARIFF",
        "referenceDataVersion": REFERENCE_DATA_VERSION,
        "route": {
            "originPort": "NLRTM",
            "destinationPort": "USNYC",
            "departureDate": "2026-08-18",
        },
        "coverage": [
            {
                "equipmentType": "20FT",
                "quantity": 2,
                "covered": True,
                "rateTableId": response.json()["coverage"][0]["rateTableId"],
                "validFrom": "2026-04-01",
                "validTo": "2026-12-31",
            },
            {
                "equipmentType": "40FT_HC",
                "quantity": 1,
                "covered": True,
                "rateTableId": response.json()["coverage"][1]["rateTableId"],
                "validFrom": "2026-04-01",
                "validTo": "2026-12-31",
            },
        ],
        "uncoveredEquipment": [],
    }


def test_validate_quote_rate_coverage_reports_missing_equipment_rates(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes/coverage/validate",
        json={
            "originPort": "BRSSZ",
            "destinationPort": "USLAX",
            "departureDate": "2026-07-12",
            "equipment": [
                {"type": "20FT", "quantity": 1},
                {"type": "40FT", "quantity": 1},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "covered": False,
        "reason": "RATE_MISSING",
        "pricingBasis": "PUBLIC_TARIFF",
        "referenceDataVersion": REFERENCE_DATA_VERSION,
        "route": {
            "originPort": "BRSSZ",
            "destinationPort": "USLAX",
            "departureDate": "2026-07-12",
        },
        "coverage": [
            {
                "equipmentType": "20FT",
                "quantity": 1,
                "covered": False,
                "rateTableId": None,
                "validFrom": None,
                "validTo": None,
            },
            {
                "equipmentType": "40FT",
                "quantity": 1,
                "covered": False,
                "rateTableId": None,
                "validFrom": None,
                "validTo": None,
            },
        ],
        "uncoveredEquipment": ["20FT", "40FT"],
    }


def test_scenario_peak_season_quote_returns_the_documented_commercial_payload(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201
    assert set(response.json()) == {
        "id",
        "quoteReference",
        "validUntil",
        "currency",
        "sourceCurrency",
        "responseCurrency",
        "lifecycleState",
        "approvalReasons",
        "approvalDecision",
        "fx",
        "roundingPolicy",
        "lineItems",
        "sourceTotalAmount",
        "totalAmount",
    }
    assert response.json()["quoteReference"].startswith("QTE-")
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 950.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
        {"description": "Peak Season Surcharge", "amount": 120.0},
    ]
    assert response.json()["totalAmount"] == 1300.0


def test_scenario_quote_lookup_accepts_uuid_and_quote_reference(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    lookup_by_id = test_client.get(f"/quotes/{quote.id}")
    lookup_by_reference = test_client.get(f"/quotes/{quote.quote_reference}")

    assert lookup_by_id.status_code == 200
    assert lookup_by_id.json()["id"] == quote.id
    assert lookup_by_id.json()["quoteReference"] == quote.quote_reference
    assert lookup_by_reference.status_code == 200
    assert lookup_by_reference.json() == lookup_by_id.json()


def test_scenario_booking_can_validate_quote_bookability(client) -> None:
    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    response = test_client.get(f"/quotes/{quote.quote_reference}/bookability")

    assert response.status_code == 200
    assert response.json()["quoteId"] == quote.quote_reference
    assert response.json()["bookable"] is True
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["reason"] == "VALIDITY_WINDOW_OPEN"


def test_scenario_route_coverage_validation_distinguishes_quoteable_lanes(client) -> None:
    test_client, _ = client

    covered_response = test_client.post(
        "/quotes/coverage/validate",
        json={
            "originPort": "CNSHA",
            "destinationPort": "DEHAM",
            "departureDate": "2026-06-05",
            "equipment": [{"type": "20FT", "quantity": 1}],
        },
    )
    uncovered_response = test_client.post(
        "/quotes/coverage/validate",
        json={
            "originPort": "BRSSZ",
            "destinationPort": "USLAX",
            "departureDate": "2026-07-12",
            "equipment": [{"type": "20FT", "quantity": 1}],
        },
    )

    assert covered_response.status_code == 200
    assert covered_response.json()["covered"] is True
    assert covered_response.json()["uncoveredEquipment"] == []
    assert uncovered_response.status_code == 200
    assert uncovered_response.json()["covered"] is False
    assert uncovered_response.json()["uncoveredEquipment"] == ["20FT"]


def test_scenario_quote_lifecycle_events_are_written_to_the_outbox(client) -> None:
    test_client, session_factory = client

    create_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert create_response.status_code == 201

    quote_id = create_response.json()["id"]
    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == quote_id))
        assert stored_quote is not None
        stored_quote.valid_until = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()

    expired_response = test_client.get(f"/quotes/{quote_id}/bookability")

    assert expired_response.status_code == 200
    assert expired_response.json()["status"] == "EXPIRED"

    with session_factory() as session:
        event_types = session.scalars(
            select(OutboxEvent.event_type)
            .where(OutboxEvent.aggregate_id == quote_id)
            .order_by(OutboxEvent.occurred_at)
        ).all()

    assert event_types == ["quote.created", "quote.expired"]


def test_scenario_contract_pricing_uses_customer_context_and_deterministic_precedence(client) -> None:
    test_client, _ = client

    customer_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )
    account_response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "accountId": "acct-acme-premium",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert customer_response.status_code == 201
    assert account_response.status_code == 201
    assert customer_response.json()["totalAmount"] == 930.0
    assert account_response.json()["totalAmount"] == 800.0


def test_scenario_derive_quote_validity_from_customer_specific_policy(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "customerId": "cust-acme",
            "accountId": "acct-acme-premium",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.pricing_basis == PricingBasis.CONTRACT
    assert timedelta(days=13, hours=23) <= stored_quote.valid_until - stored_quote.created_at <= timedelta(days=14, minutes=1)
    assert stored_quote.pricing_provenance["validityPolicy"] == _validity_policy_snapshot(
        policy_id="validity-account-acme-premium-14d",
        policy_name="ACME premium account validity",
        validity_hours=336,
        customer_id="cust-acme",
        account_id="acct-acme-premium",
        contract_id=stored_quote.contract_id,
        pricing_basis=PricingBasis.CONTRACT,
        market_signals={},
    )


def test_market_pricing_can_use_a_shorter_high_volatility_validity_policy(client) -> None:
    test_client, session_factory = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "pricingModeHint": "MARKET",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
        },
    )

    assert response.status_code == 201

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.pricing_basis == PricingBasis.MARKET
    assert timedelta(hours=11, minutes=59) <= stored_quote.valid_until - stored_quote.created_at <= timedelta(hours=12, minutes=1)
    assert stored_quote.pricing_provenance["validityPolicy"] == _validity_policy_snapshot(
        policy_id="validity-volatile-market-12h",
        policy_name="High-volatility market validity",
        validity_hours=12,
        customer_id=None,
        account_id=None,
        contract_id=None,
        pricing_basis=PricingBasis.MARKET,
        market_signals={
            "capacityPressureIndex": 0.62,
            "utilizationIndex": 0.81,
            "seasonalityIndex": 0.58,
        },
        matched_pricing_basis=PricingBasis.MARKET.value,
        matched_market_signals={
            "capacityPressureIndex": 0.62,
            "utilizationIndex": 0.81,
            "seasonalityIndex": 0.58,
        },
    )


def test_scenario_requested_currency_quotes_include_fx_provenance(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 18000,
            "currency": "EUR",
        },
    )

    assert response.status_code == 201
    assert response.json()["sourceCurrency"] == "USD"
    assert response.json()["responseCurrency"] == "EUR"
    assert response.json()["fx"] == _fx_snapshot(currency="EUR", rate=0.92)
    assert response.json()["sourceTotalAmount"] == 1300.0
    assert response.json()["totalAmount"] == 1196.0


def test_scenario_known_schedule_without_rate_returns_a_commercial_validation_error(client) -> None:
    test_client, _ = client

    response = test_client.post(
        "/quotes",
        json={
            "scheduleId": "1ce1ab21-9d58-4a6d-b867-afc93098352f",
            "equipment": [{"type": "20FT", "quantity": 1}],
            "cargoWeightKg": 10000,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "No rate available for 20FT on selected schedule"}
