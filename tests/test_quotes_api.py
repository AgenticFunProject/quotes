from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import db
from app.db import Base, get_db
from app.main import app
from app.models import Quote
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
        "id": response.json()["id"],
        "quoteReference": response.json()["quoteReference"],
        "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
        "equipment": [
            {"type": "20FT", "quantity": 2},
            {"type": "40FT", "quantity": 1},
        ],
        "cargoWeightKg": 70000.0,
        "currency": "USD",
        "lineItems": [
            {"description": "Ocean Freight - 20FT x 2", "amount": 1900.0},
            {"description": "Ocean Freight - 40FT x 1", "amount": 1400.0},
            {"description": "Bunker Adjustment Factor (BAF)", "amount": 240.0},
            {"description": "Port Congestion Surcharge - Destination USNYC", "amount": 450.0},
            {"description": "Peak Season Surcharge", "amount": 360.0},
        ],
        "totalAmount": 4350.0,
        "validUntil": response.json()["validUntil"],
        "createdAt": response.json()["createdAt"],
    }
    assert response.json()["quoteReference"].endswith("-00001")
    assert response.json()["quoteReference"].startswith("QTE-")

    valid_until = datetime.fromisoformat(response.json()["validUntil"])
    created_at = datetime.fromisoformat(response.json()["createdAt"])
    assert valid_until > created_at

    with session_factory() as session:
        stored_quote = session.scalar(select(Quote).where(Quote.id == response.json()["id"]))

    assert stored_quote is not None
    assert stored_quote.quote_reference == response.json()["quoteReference"]
    assert float(stored_quote.total_amount) == response.json()["totalAmount"]


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
