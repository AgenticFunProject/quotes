from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _default_database_url() -> str:
    return "sqlite:///./db.sqlite"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _apply_sqlite_schema_fixes() -> None:
    if not str(engine.url).startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "quotes" not in inspector.get_table_names():
        return

    quote_columns = {column["name"] for column in inspector.get_columns("quotes")}
    with engine.begin() as connection:
        if "customer_id" not in quote_columns:
            connection.execute(text("ALTER TABLE quotes ADD COLUMN customer_id VARCHAR(64)"))
        if "account_id" not in quote_columns:
            connection.execute(text("ALTER TABLE quotes ADD COLUMN account_id VARCHAR(64)"))
        if "contract_id" not in quote_columns:
            connection.execute(text("ALTER TABLE quotes ADD COLUMN contract_id VARCHAR(36)"))
        if "pricing_provenance" not in quote_columns:
            connection.execute(text("ALTER TABLE quotes ADD COLUMN pricing_provenance JSON NOT NULL DEFAULT '{}'"))

    _backfill_managed_commercial_columns("rate_tables")
    _backfill_managed_commercial_columns("surcharge_rules")


def _backfill_managed_commercial_columns(table_name: str) -> None:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return

    managed_columns = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as connection:
        if "version" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
        if "is_active" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "created_by" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN created_by VARCHAR(64)"))
        if "updated_by" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN updated_by VARCHAR(64)"))
        if "activated_by" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN activated_by VARCHAR(64)"))
        if "created_at" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN created_at DATETIME"))
        if "updated_at" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN updated_at DATETIME"))
        if "activated_at" not in managed_columns:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN activated_at DATETIME"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_schema_fixes()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
