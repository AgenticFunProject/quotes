from __future__ import annotations

from collections.abc import Iterator

import pytest

from app import db
from app.db import Base
from app.models import EquipmentType, RateTable, SurchargeRule, SurchargeType
from app.seed import RATE_TABLE_ROWS, SURCHARGE_RULE_ROWS, seed_reference_data


@pytest.fixture()
def sqlite_database(tmp_path, monkeypatch) -> Iterator[None]:
    database_path = tmp_path / "seed-test.sqlite"
    engine = db.create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    session_factory = db.sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(db, "DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr("app.seed.SessionLocal", session_factory)

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_seed_reference_data_populates_rate_tables_and_surcharges(sqlite_database) -> None:
    seed_reference_data()

    with db.SessionLocal() as session:
        rate_rows = session.query(RateTable).order_by(RateTable.origin_port, RateTable.equipment_type).all()
        surcharge_rows = session.query(SurchargeRule).order_by(SurchargeRule.description).all()

    assert len(rate_rows) == len(RATE_TABLE_ROWS)
    assert len(surcharge_rows) == len(SURCHARGE_RULE_ROWS)
    assert {row.equipment_type for row in rate_rows} == set(EquipmentType)
    assert {row.surcharge_type for row in surcharge_rows} == {
        SurchargeType.BAF,
        SurchargeType.PORT_CONGESTION,
        SurchargeType.HEAVY_CARGO,
        SurchargeType.PEAK_SEASON,
    }


def test_seed_reference_data_is_idempotent(sqlite_database) -> None:
    seed_reference_data()
    seed_reference_data()

    with db.SessionLocal() as session:
        assert session.query(RateTable).count() == len(RATE_TABLE_ROWS)
        assert session.query(SurchargeRule).count() == len(SURCHARGE_RULE_ROWS)
