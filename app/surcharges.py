from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models import EquipmentType, PortScope, SurchargeRule, SurchargeType


_MONEY_PRECISION = Decimal("0.01")
_TEU_PER_EQUIPMENT = {
    EquipmentType.TWENTY_FT: Decimal("1"),
    EquipmentType.FORTY_FT: Decimal("2"),
    EquipmentType.FORTY_FT_HC: Decimal("2"),
}


@dataclass(frozen=True)
class EquipmentSelection:
    equipment_type: EquipmentType
    quantity: int


@dataclass(frozen=True)
class SurchargeLineItem:
    description: str
    amount: Decimal

    def as_dict(self) -> dict[str, object]:
        return {"description": self.description, "amount": float(self.amount)}


def calculate_surcharges(
    *,
    equipment: list[EquipmentSelection],
    cargo_weight_kg: Decimal,
    shipment_date: date,
    origin_port: str,
    destination_port: str,
    surcharge_rules: list[SurchargeRule],
) -> list[SurchargeLineItem]:
    total_containers = sum(item.quantity for item in equipment)
    if total_containers <= 0:
        return []

    total_teu = sum(_TEU_PER_EQUIPMENT[item.equipment_type] * item.quantity for item in equipment)
    weight_per_teu = cargo_weight_kg / total_teu if total_teu else Decimal("0")

    line_items: list[SurchargeLineItem] = []
    for rule in surcharge_rules:
        if not _rule_applies(
            rule=rule,
            shipment_date=shipment_date,
            origin_port=origin_port,
            destination_port=destination_port,
            weight_per_teu=weight_per_teu,
        ):
            continue

        amount = (rule.amount_usd * total_containers).quantize(_MONEY_PRECISION)
        if amount <= 0:
            continue

        line_items.append(SurchargeLineItem(description=rule.description, amount=amount))

    return line_items


def total_surcharges(line_items: list[SurchargeLineItem]) -> Decimal:
    return sum((item.amount for item in line_items), start=Decimal("0.00")).quantize(_MONEY_PRECISION)


def _rule_applies(
    *,
    rule: SurchargeRule,
    shipment_date: date,
    origin_port: str,
    destination_port: str,
    weight_per_teu: Decimal,
) -> bool:
    if rule.surcharge_type == SurchargeType.BAF:
        return True

    if rule.surcharge_type == SurchargeType.PORT_CONGESTION:
        return _matches_port(rule=rule, origin_port=origin_port, destination_port=destination_port)

    if rule.surcharge_type == SurchargeType.HEAVY_CARGO:
        return rule.weight_threshold_kg_per_teu is not None and weight_per_teu > rule.weight_threshold_kg_per_teu

    if rule.surcharge_type == SurchargeType.PEAK_SEASON:
        if rule.valid_from is not None and shipment_date < rule.valid_from:
            return False
        if rule.valid_to is not None and shipment_date > rule.valid_to:
            return False
        return True

    return False


def _matches_port(*, rule: SurchargeRule, origin_port: str, destination_port: str) -> bool:
    if not rule.port_code or rule.port_scope is None:
        return False

    if rule.port_scope == PortScope.ORIGIN:
        return rule.port_code == origin_port

    if rule.port_scope == PortScope.DESTINATION:
        return rule.port_code == destination_port

    return False
