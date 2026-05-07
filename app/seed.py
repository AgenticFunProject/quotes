from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Contract, ContractMatchType, ContractRateRule, EquipmentType, ExchangeRate, MarketRateSnapshot, PortScope, PricingStrategyVersion, RateTable, SurchargeRule, SurchargeType


REFERENCE_DATA_VERSION = "seed-2026-04-01"
FX_REFERENCE_DATA_VERSION = "seed-fx-2026-05-06"
FX_PROVIDER = "seeded-governed-fx"
FX_OBSERVED_AT = datetime(2026, 5, 6, 0, 0, tzinfo=timezone.utc)
MARKET_RATE_SOURCE = "approved-spot-market-feed"
MARKET_RATE_CAPTURED_AT = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
MARKET_RATE_APPROVED_AT = datetime(2026, 5, 6, 9, 30, tzinfo=timezone.utc)


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

CONTRACT_ROWS = (
    {
        "id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001",
        "customer_id": "cust-acme",
        "account_id": None,
        "match_type": ContractMatchType.CUSTOMER,
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "waived_surcharge_types": [SurchargeType.PEAK_SEASON.value],
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002",
        "customer_id": "cust-acme",
        "account_id": "acct-acme-premium",
        "match_type": ContractMatchType.ACCOUNT,
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "waived_surcharge_types": [SurchargeType.BAF.value, SurchargeType.PEAK_SEASON.value],
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
    {
        "id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300003",
        "customer_id": "cust-globex",
        "account_id": None,
        "match_type": ContractMatchType.CUSTOMER,
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "waived_surcharge_types": [SurchargeType.PORT_CONGESTION.value],
        "valid_from": date(2026, 4, 1),
        "valid_to": date(2026, 12, 31),
    },
)

CONTRACT_RATE_RULE_ROWS = (
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001",
        "equipment_type": EquipmentType.TWENTY_FT,
        "base_rate_usd": Decimal("700.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001",
        "equipment_type": EquipmentType.FORTY_FT,
        "base_rate_usd": Decimal("1100.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300001",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "base_rate_usd": Decimal("1225.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002",
        "equipment_type": EquipmentType.TWENTY_FT,
        "base_rate_usd": Decimal("650.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002",
        "equipment_type": EquipmentType.FORTY_FT,
        "base_rate_usd": Decimal("1025.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300002",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "base_rate_usd": Decimal("1150.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300003",
        "equipment_type": EquipmentType.TWENTY_FT,
        "base_rate_usd": Decimal("820.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300003",
        "equipment_type": EquipmentType.FORTY_FT,
        "base_rate_usd": Decimal("1260.00"),
    },
    {
        "contract_id": "7c9cc0a4-bd6d-4e6f-9c1c-e5c3a1300003",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "base_rate_usd": Decimal("1340.00"),
    },
)

EXCHANGE_RATE_ROWS = (
    {
        "id": "fx-usd-usd",
        "base_currency": "USD",
        "quote_currency": "USD",
        "rate": Decimal("1.000000"),
        "provider": FX_PROVIDER,
        "observed_at": FX_OBSERVED_AT,
        "reference_data_version": FX_REFERENCE_DATA_VERSION,
    },
    {
        "id": "fx-usd-eur",
        "base_currency": "USD",
        "quote_currency": "EUR",
        "rate": Decimal("0.920000"),
        "provider": FX_PROVIDER,
        "observed_at": FX_OBSERVED_AT,
        "reference_data_version": FX_REFERENCE_DATA_VERSION,
    },
    {
        "id": "fx-usd-gbp",
        "base_currency": "USD",
        "quote_currency": "GBP",
        "rate": Decimal("0.790000"),
        "provider": FX_PROVIDER,
        "observed_at": FX_OBSERVED_AT,
        "reference_data_version": FX_REFERENCE_DATA_VERSION,
    },
)

MARKET_RATE_SNAPSHOT_ROWS = (
    {
        "id": "market-nlrtm-usnyc-20ft",
        "source_name": MARKET_RATE_SOURCE,
        "source_reference": "spot-quote-2026-05-05-nlrtm-usnyc-20ft",
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "equipment_type": EquipmentType.TWENTY_FT,
        "rate_usd": Decimal("1085.00"),
        "valid_from": date(2026, 8, 1),
        "valid_to": date(2026, 8, 31),
        "capacity_pressure_index": Decimal("0.62"),
        "utilization_index": Decimal("0.81"),
        "seasonality_index": Decimal("0.58"),
        "captured_at": MARKET_RATE_CAPTURED_AT,
        "approved_at": MARKET_RATE_APPROVED_AT,
        "approved_by": "pricing.manager@quotes",
    },
    {
        "id": "market-nlrtm-usnyc-40ft",
        "source_name": MARKET_RATE_SOURCE,
        "source_reference": "spot-quote-2026-05-05-nlrtm-usnyc-40ft",
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "equipment_type": EquipmentType.FORTY_FT,
        "rate_usd": Decimal("1560.00"),
        "valid_from": date(2026, 8, 1),
        "valid_to": date(2026, 8, 31),
        "capacity_pressure_index": Decimal("0.62"),
        "utilization_index": Decimal("0.81"),
        "seasonality_index": Decimal("0.58"),
        "captured_at": MARKET_RATE_CAPTURED_AT,
        "approved_at": MARKET_RATE_APPROVED_AT,
        "approved_by": "pricing.manager@quotes",
    },
    {
        "id": "market-nlrtm-usnyc-40ft-hc",
        "source_name": MARKET_RATE_SOURCE,
        "source_reference": "spot-quote-2026-05-05-nlrtm-usnyc-40ft-hc",
        "origin_port": "NLRTM",
        "destination_port": "USNYC",
        "equipment_type": EquipmentType.FORTY_FT_HC,
        "rate_usd": Decimal("1690.00"),
        "valid_from": date(2026, 8, 1),
        "valid_to": date(2026, 8, 31),
        "capacity_pressure_index": Decimal("0.62"),
        "utilization_index": Decimal("0.81"),
        "seasonality_index": Decimal("0.58"),
        "captured_at": MARKET_RATE_CAPTURED_AT,
        "approved_at": MARKET_RATE_APPROVED_AT,
        "approved_by": "pricing.manager@quotes",
    },
)

PRICING_STRATEGY_VERSION_ROWS = (
    {
        "id": "strategy-market-optimization-v1",
        "strategy_name": "market-optimization",
        "rules": {
            "capacityPressureThreshold": 0.75,
            "utilizationThreshold": 0.9,
            "seasonalityThreshold": 0.7,
            "selectionMode": "ANY_SIGNAL"
        },
    },
)


def seed_reference_data() -> None:
    with SessionLocal() as session:
        has_rate_rows = session.scalar(select(RateTable.id).limit(1)) is not None
        has_surcharge_rows = session.scalar(select(SurchargeRule.id).limit(1)) is not None
        has_contract_rows = session.scalar(select(Contract.id).limit(1)) is not None
        has_contract_rate_rows = session.scalar(select(ContractRateRule.id).limit(1)) is not None
        has_exchange_rate_rows = session.scalar(select(ExchangeRate.id).limit(1)) is not None
        has_market_rate_rows = session.scalar(select(MarketRateSnapshot.id).limit(1)) is not None
        has_pricing_strategy_rows = session.scalar(select(PricingStrategyVersion.id).limit(1)) is not None

        if has_rate_rows and has_surcharge_rows and has_contract_rows and has_contract_rate_rows and has_exchange_rate_rows and has_market_rate_rows and has_pricing_strategy_rows:
            return

        if not has_rate_rows:
            session.add_all(RateTable(**row) for row in RATE_TABLE_ROWS)

        if not has_surcharge_rows:
            session.add_all(SurchargeRule(**row) for row in SURCHARGE_RULE_ROWS)

        if not has_contract_rows:
            session.add_all(Contract(**row) for row in CONTRACT_ROWS)

        if not has_contract_rate_rows:
            session.add_all(ContractRateRule(**row) for row in CONTRACT_RATE_RULE_ROWS)

        if not has_exchange_rate_rows:
            session.add_all(ExchangeRate(**row) for row in EXCHANGE_RATE_ROWS)

        if not has_market_rate_rows:
            session.add_all(MarketRateSnapshot(**row) for row in MARKET_RATE_SNAPSHOT_ROWS)

        if not has_pricing_strategy_rows:
            session.add_all(PricingStrategyVersion(**row) for row in PRICING_STRATEGY_VERSION_ROWS)

        session.commit()
