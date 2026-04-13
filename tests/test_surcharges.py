from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models import EquipmentType, PortScope, SurchargeRule, SurchargeType
from app.surcharges import EquipmentSelection, calculate_surcharges, total_surcharges


def test_calculate_surcharges_applies_all_matching_rules() -> None:
    line_items = calculate_surcharges(
        equipment=[
            EquipmentSelection(equipment_type=EquipmentType.TWENTY_FT, quantity=2),
            EquipmentSelection(equipment_type=EquipmentType.FORTY_FT, quantity=1),
        ],
        cargo_weight_kg=Decimal("70000.00"),
        shipment_date=date(2026, 7, 15),
        origin_port="NLRTM",
        destination_port="USNYC",
        surcharge_rules=[
            _rule(SurchargeType.BAF, "Bunker Adjustment Factor (BAF)", "80.00"),
            _rule(
                SurchargeType.PORT_CONGESTION,
                "Port Surcharge - Destination",
                "50.00",
                port_code="USNYC",
                port_scope=PortScope.DESTINATION,
            ),
            _rule(
                SurchargeType.HEAVY_CARGO,
                "Heavy Cargo Surcharge",
                "125.00",
                weight_threshold_kg_per_teu="20000.00",
            ),
            _rule(
                SurchargeType.PEAK_SEASON,
                "Peak Season Surcharge (PSS)",
                "40.00",
                valid_from=date(2026, 7, 1),
                valid_to=date(2026, 8, 31),
            ),
        ],
    )

    assert [item.description for item in line_items] == [
        "Bunker Adjustment Factor (BAF)",
        "Port Surcharge - Destination",
        "Heavy Cargo Surcharge",
        "Peak Season Surcharge (PSS)",
    ]
    assert [item.amount for item in line_items] == [
        Decimal("240.00"),
        Decimal("150.00"),
        Decimal("375.00"),
        Decimal("120.00"),
    ]
    assert total_surcharges(line_items) == Decimal("885.00")


def test_heavy_cargo_uses_weight_per_teu_threshold() -> None:
    line_items = calculate_surcharges(
        equipment=[EquipmentSelection(equipment_type=EquipmentType.FORTY_FT, quantity=1)],
        cargo_weight_kg=Decimal("30000.00"),
        shipment_date=date(2026, 7, 15),
        origin_port="NLRTM",
        destination_port="USNYC",
        surcharge_rules=[
            _rule(
                SurchargeType.HEAVY_CARGO,
                "Heavy Cargo Surcharge",
                "125.00",
                weight_threshold_kg_per_teu="20000.00",
            )
        ],
    )

    assert line_items == []


def test_port_congestion_requires_matching_port_scope() -> None:
    line_items = calculate_surcharges(
        equipment=[EquipmentSelection(equipment_type=EquipmentType.TWENTY_FT, quantity=1)],
        cargo_weight_kg=Decimal("10000.00"),
        shipment_date=date(2026, 7, 15),
        origin_port="NLRTM",
        destination_port="USNYC",
        surcharge_rules=[
            _rule(
                SurchargeType.PORT_CONGESTION,
                "Port Surcharge - Destination",
                "50.00",
                port_code="SGSIN",
                port_scope=PortScope.DESTINATION,
            )
        ],
    )

    assert line_items == []


def test_peak_season_requires_shipment_date_in_window() -> None:
    line_items = calculate_surcharges(
        equipment=[EquipmentSelection(equipment_type=EquipmentType.TWENTY_FT, quantity=1)],
        cargo_weight_kg=Decimal("10000.00"),
        shipment_date=date(2026, 6, 30),
        origin_port="NLRTM",
        destination_port="USNYC",
        surcharge_rules=[
            _rule(
                SurchargeType.PEAK_SEASON,
                "Peak Season Surcharge (PSS)",
                "40.00",
                valid_from=date(2026, 7, 1),
                valid_to=date(2026, 8, 31),
            )
        ],
    )

    assert line_items == []


def _rule(
    surcharge_type: SurchargeType,
    description: str,
    amount_usd: str,
    *,
    port_code: str | None = None,
    port_scope: PortScope | None = None,
    weight_threshold_kg_per_teu: str | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> SurchargeRule:
    return SurchargeRule(
        surcharge_type=surcharge_type,
        description=description,
        amount_usd=Decimal(amount_usd),
        port_code=port_code,
        port_scope=port_scope,
        weight_threshold_kg_per_teu=(
            Decimal(weight_threshold_kg_per_teu) if weight_threshold_kg_per_teu is not None else None
        ),
        valid_from=valid_from,
        valid_to=valid_to,
    )
