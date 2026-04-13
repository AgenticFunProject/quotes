from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import EquipmentType, PortScope, RateTable, SurchargeRule, SurchargeType


RATE_TABLE_ROWS = (
    {
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "equipment_type": EquipmentType.TWENTY_FT,
        "base_rate_usd": Decimal("950.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "equipment_type": EquipmentType.FORTY_FT,
        "base_rate_usd": Decimal("1400.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "base_rate_usd": Decimal("1525.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "CNSHA",
        "destination_port": "DEHAM",
        "equipment_type": EquipmentType.TWENTY_FT,
        "base_rate_usd": Decimal("875.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "CNSHA",
        "destination_port": "DEHAM",
        "equipment_type": EquipmentType.FORTY_FT,
        "base_rate_usd": Decimal("1295.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "CNSHA",
        "destination_port": "DEHAM",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "base_rate_usd": Decimal("1380.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "SGSIN",
        "destination_port": "AEMSA",
        "equipment_type": EquipmentType.TWENTY_FT,
        "base_rate_usd": Decimal("720.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "SGSIN",
        "destination_port": "AEMSA",
        "equipment_type": EquipmentType.FORTY_FT,
        "base_rate_usd": Decimal("1040.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "origin_port": "SGSIN",
        "destination_port": "AEMSA",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "base_rate_usd": Decimal("1125.00"),
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
)

SURCHARGE_RULE_ROWS = (
    {
        "surcharge_type": SurchargeType.BAF,
        "description": "Bunker Adjustment Factor (BAF)",
        "amount_usd": Decimal("80.00"),
        "currency": "USD",
        "port_code": None,
        "port_scope": None,
        "weight_threshold_kg_per_teu": None,
        "valid_from": None,
        "valid_to": None,
    },
    {
        "surcharge_type": SurchargeType.PORT_CONGESTION,
        "description": "Port Congestion Surcharge - Destination USNYC",
        "amount_usd": Decimal("150.00"),
        "currency": "USD",
        "port_code": "USNYC",
        "port_scope": PortScope.DESTINATION,
        "weight_threshold_kg_per_teu": None,
        "valid_from": None,
        "valid_to": None,
    },
    {
        "surcharge_type": SurchargeType.PORT_CONGESTION,
        "description": "Port Congestion Surcharge - Origin CNSHA",
        "amount_usd": Decimal("95.00"),
        "currency": "USD",
        "port_code": "CNSHA",
        "port_scope": PortScope.ORIGIN,
        "weight_threshold_kg_per_teu": None,
        "valid_from": None,
        "valid_to": None,
    },
    {
        "surcharge_type": SurchargeType.HEAVY_CARGO,
        "description": "Heavy Cargo Surcharge",
        "amount_usd": Decimal("200.00"),
        "currency": "USD",
        "port_code": None,
        "port_scope": None,
        "weight_threshold_kg_per_teu": Decimal("20000.00"),
        "valid_from": None,
        "valid_to": None,
    },
    {
        "surcharge_type": SurchargeType.PEAK_SEASON,
        "description": "Peak Season Surcharge",
        "amount_usd": Decimal("120.00"),
        "currency": "USD",
        "port_code": None,
        "port_scope": None,
        "weight_threshold_kg_per_teu": None,
        "valid_from": date(2026, 8, 1),
        "valid_to": date(2026, 9, 30),
    },
)


def seed_reference_data() -> None:
    with SessionLocal() as session:
        has_rate_rows = session.scalar(select(RateTable.id).limit(1)) is not None
        has_surcharge_rows = session.scalar(select(SurchargeRule.id).limit(1)) is not None

        if has_rate_rows and has_surcharge_rows:
            return

        if not has_rate_rows:
            session.add_all(RateTable(**row) for row in RATE_TABLE_ROWS)

        if not has_surcharge_rows:
            session.add_all(SurchargeRule(**row) for row in SURCHARGE_RULE_ROWS)

        session.commit()
