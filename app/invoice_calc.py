"""Rechnungsberechnung: Positionssummen, USt-Aufschlüsselung, Gesamtsummen.

Berücksichtigt Rabatte je Position, Steueraufschlüsselung je Steuersatz
(gerundet pro Gruppe – so wie im deutschen Rechnungswesen üblich) und die
Sondermodi §19 (Kleinunternehmer) und §13b (Reverse-Charge), bei denen keine
Umsatzsteuer ausgewiesen wird.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .money import D, money


@dataclass
class CalcLine:
    position: int
    item_type: str
    article_number: str
    name: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount_percent: Decimal
    tax_rate: Decimal
    line_net: Decimal = Decimal("0")


@dataclass
class TaxGroup:
    rate: Decimal
    net: Decimal
    tax: Decimal


@dataclass
class CalcResult:
    lines: list[CalcLine] = field(default_factory=list)
    tax_groups: list[TaxGroup] = field(default_factory=list)
    total_net: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")
    total_gross: Decimal = Decimal("0")
    tax_mode: str = "regel"


def compute(items: list[dict], tax_mode: str = "regel") -> CalcResult:
    """Berechnet eine Rechnung aus einer Liste von Positions-Dicts.

    Bei tax_mode 'kleinunternehmer' oder 'reverse_charge' wird keine USt
    ausgewiesen (effektiver Steuersatz 0).
    """
    no_vat = tax_mode in ("kleinunternehmer", "reverse_charge")
    result = CalcResult(tax_mode=tax_mode)
    groups: dict[str, Decimal] = {}

    for idx, it in enumerate(items, start=1):
        item_type = it.get("item_type", "leistung")
        qty = D(it.get("quantity", 0))
        price = D(it.get("unit_price", 0))
        disc = D(it.get("discount_percent", 0))
        rate = Decimal("0") if no_vat else D(it.get("tax_rate", 0))

        if item_type == "text":
            line_net = Decimal("0")
        else:
            gross_line = qty * price
            line_net = money(gross_line * (Decimal("1") - disc / Decimal("100")))

        line = CalcLine(
            position=int(it.get("position", idx)),
            item_type=item_type,
            article_number=it.get("article_number", ""),
            name=it.get("name", ""),
            description=it.get("description", ""),
            quantity=qty,
            unit=it.get("unit", ""),
            unit_price=money(price),
            discount_percent=disc,
            tax_rate=rate,
            line_net=line_net,
        )
        result.lines.append(line)

        if item_type != "text":
            key = str(rate)
            groups[key] = groups.get(key, Decimal("0")) + line_net

    total_net = Decimal("0")
    total_tax = Decimal("0")
    for rate_str in sorted(groups.keys(), key=lambda r: Decimal(r)):
        net = money(groups[rate_str])
        if net == 0:
            continue  # leere/0-Euro-Steuergruppe nicht ausweisen
        rate = Decimal(rate_str)
        tax = money(net * rate / Decimal("100"))
        result.tax_groups.append(TaxGroup(rate=rate, net=net, tax=tax))
        total_net += net
        total_tax += tax

    result.total_net = money(total_net)
    result.total_tax = money(total_tax)
    result.total_gross = money(total_net + total_tax)
    return result


def is_small_amount(total_gross) -> bool:
    """Kleinbetragsrechnung bis 250 € brutto (§ 33 UStDV)."""
    return money(total_gross) <= Decimal("250.00")
