from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db
from app.db import Base, get_db
from app.main import app
from app.models import PricingBasis, Quote, QuoteLifecycleState
from app.seed import seed_reference_data


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
        "quoteId": response.json()["quoteId"],
        "validUntil": response.json()["validUntil"],
        "currency": "USD",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1900.0},
            {"description": "Ocean Freight - 40FT x 1", "amount": 1400.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 240.0},
            {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 450.0},
            {"description": "Peak Season Surcharge", "amount": 360.0},
        ],
        "totalAmount": 4350.0,
    }
    assert response.json()["quoteId"].endswith("-00001")
    assert response.json()["quoteId"].startswith("QTE-")

    valid_until = datetime.fromisoformat(response.json()["validUntil"])

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.quote_reference == response.json()["quoteId"]))

    assert stored_quote is not None
    created_at = stored_quote.created_at
    assert valid_until > created_at
    assert timedelta(days=6, hours=23) <= valid_until - created_at <= timedelta(days=7, minutes=1)
    assert stored_quote.quote_reference == response.json()["quoteId"]
    assert float(stored_quote.total_amount) == response.json()["totalAmount"]
    assert stored_quote.lifecycle_state == QuoteLifecycleState.ISSUED
    assert stored_quote.pricing_basis == PricingBasis.PUBLIC_TARIFF
    assert stored_quote.idempotency_key is None
    assert stored_quote.schedule_snapshot == {
        "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        "originPort": "NLRTM",
        "destinationPort": "USNYC",
        "departureDate": "2026-08-18",
    }


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
    assert first_response.json()["quoteId"].endswith("-00001")
    assert second_response.json()["quoteId"].endswith("-00002")


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
            pricing_basis=PricingBasis.PUBLIC_TARIFF,
            idempotency_key="booking-request-42",
            line_items=[
                {"description": "Ocean Freight - 20FT x 2", "amount": 1800.0},
                {"description": "Bunker Adjustment Factor (BAF)", "amount": 320.0},
            ],
            total_amount=Decimal("2120.00"),
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
        "pricingBasis": "PUBLIC_TARIFF",
        "idempotencyKey": "booking-request-42",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1800.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 320.0},
        ],
        "totalAmount": 2120.0,
        "validUntil": quote.valid_until.isoformat(),
        "createdAt": quote.created_at.isoformat(),
    }


def test_get_quote_by_reference_returns_404(client) -> None:
    test_client, session_factory = client
    _seed_quote(session_factory)

    response = test_client.get("/quotes/QTE-2026-00108")

    assert response.status_code == 404
    assert response.json() == {"detail": "Quote not found"}


def test_get_quote_returns_404_when_missing(client) -> None:
    test_client, _ = client

    response = test_client.get("/quotes/missing-quote")

    assert response.status_code == 404
    assert response.json() == {"detail": "Quote not found"}


def test_scenario_peak_season_quote_returns_the_documented_commercial_payload(client) -> None:
    """Scenario: Create a quote on a seeded peak-season lane

    Given the service has the seeded schedule and reference pricing data
    When a client requests a quote for the Rotterdam to New York schedule
    Then the API returns the commercial quote response shape documented in v1
    And the response includes the seasonal and congestion surcharges for that lane
    """

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
    assert set(response.json()) == {"quoteId", "validUntil", "currency", "lineItems", "totalAmount"}
    assert response.json()["quoteId"].startswith("QTE-")
    assert response.json()["lineItems"] == [
        {"description": "Ocean Freight - 20FT x 1", "amount": 950.0},
        {"description": "Bunker Adjustment Factor (BAF)", "amount": 80.0},
        {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 150.0},
        {"description": "Peak Season Surcharge", "amount": 120.0},
    ]
    assert response.json()["totalAmount"] == 1300.0


def test_scenario_quote_lookup_accepts_uuid_but_not_quote_reference(client) -> None:
    """Scenario: Retrieve a stored quote

    Given a quote has been stored by the service
    When the client looks it up by internal UUID
    Then the API returns the full stored quote record
    But when the client uses the human-readable quote reference
    Then the API returns quote not found
    """

    test_client, session_factory = client
    quote = _seed_quote(session_factory)

    lookup_by_id = test_client.get(f"/quotes/{quote.id}")
    lookup_by_reference = test_client.get(f"/quotes/{quote.quote_reference}")

    assert lookup_by_id.status_code == 200
    assert lookup_by_id.json()["id"] == quote.id
    assert lookup_by_id.json()["quoteReference"] == quote.quote_reference
    assert lookup_by_reference.status_code == 404
    assert lookup_by_reference.json() == {"detail": "Quote not found"}


def test_scenario_known_schedule_without_rate_returns_a_commercial_validation_error(client) -> None:
    """Scenario: Request a quote for a seeded schedule without an effective rate

    Given the service recognizes the schedule identifier
    And no seeded base freight row exists for that route and equipment
    When the client requests a quote
    Then the API rejects the request with a commercial validation error
    """

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
