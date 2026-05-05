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
    if "pricing_provenance" in quote_columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE quotes ADD COLUMN pricing_provenance JSON NOT NULL DEFAULT '{}'"))


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
