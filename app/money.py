"""Geldbeträge exakt rechnen (Decimal, kaufmännische Rundung auf Cent)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    # robust gegen deutsche Eingaben "1.234,56"
    if isinstance(value, str):
        value = value.strip().replace(".", "").replace(",", ".") if ("," in value) else value.strip()
    return Decimal(str(value))


def money(value) -> Decimal:
    """Auf zwei Nachkommastellen kaufmännisch runden."""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value) -> str:
    """Deutsche Darstellung: 1.234,56"""
    q = money(value)
    s = f"{q:,.2f}"  # 1,234.56 (englisch)
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_eur(value) -> str:
    return fmt(value) + " €"


def fmt_qty(value) -> str:
    """Menge ohne überflüssige Nullen: 6, 10,5, 0,25."""
    s = fmt(value)
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s
