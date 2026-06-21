"""Automatische Pflicht- und Hinweistexte je nach Rechnungs-/Kundensituation.

Diese Texte ergänzt das Tool selbsttätig, damit handwerkstypische Sonderfälle
korrekt abgebildet sind (Reverse-Charge, Kleinunternehmer, Aufbewahrungshinweis
für Privatkunden bei Bauleistungen, Skonto).
"""
from __future__ import annotations

from .money import D, fmt_eur


def legal_notes(company: dict, customer: dict | None, invoice: dict) -> list[str]:
    notes: list[str] = []
    tax_mode = invoice.get("tax_mode", "regel")
    klein = bool(company.get("kleinunternehmer")) or tax_mode == "kleinunternehmer"

    if klein:
        notes.append(
            "Gemäß § 19 UStG (Kleinunternehmerregelung) wird keine Umsatzsteuer berechnet."
        )
    if tax_mode == "reverse_charge":
        notes.append(
            "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG). "
            "Die Umsatzsteuer ist vom Leistungsempfänger anzumelden und abzuführen."
        )

    # Bauabzugsteuer §48 EStG – Hinweis, wenn keine Freistellung vorliegt (B2B)
    if (customer is not None and customer.get("kind") in ("B2B", "B2G")
            and not customer.get("freistellung_48")):
        notes.append(
            "Hinweis: Für diese Bauleistung kann der Steuerabzug nach § 48 EStG "
            "(Bauabzugsteuer) gelten, sofern keine gültige Freistellungsbescheinigung vorliegt."
        )

    # Skonto
    try:
        skonto = float(invoice.get("skonto_percent") or 0)
    except (TypeError, ValueError):
        skonto = 0
    if skonto > 0:
        days = invoice.get("skonto_days") or 0
        notes.append(
            f"Bei Zahlung innerhalb von {days} Tagen gewähren wir {fmt_eur(0).replace(' €','')}"
            .strip()
        )
        # sauberer formuliert:
        notes[-1] = f"Bei Zahlung innerhalb von {days} Tagen gewähren wir {('%g' % skonto)} % Skonto."

    return notes


def payment_term_text(invoice: dict, company: dict) -> str:
    due = invoice.get("due_date") or ""
    if due:
        return f"Zahlbar bis {format_de(due)} ohne Abzug."
    days = invoice.get("payment_terms_days") or company.get("payment_terms_days") or 14
    return f"Zahlbar innerhalb von {days} Tagen ohne Abzug."


def service_period(start: str, end: str) -> tuple[str, str]:
    """(Beschriftung, Wert) für das Leistungsdatum. Bei Zeitraum kompakt:
    'Leistungszeitraum' + '15.06.–19.06.2026'; bei einem Tag 'Leistungsdatum'."""
    if not start:
        return ("Leistungsdatum", "")
    s = format_de(start)
    if not end or end == start:
        return ("Leistungsdatum", s)
    sp, ep = str(start).split("-"), str(end).split("-")
    if len(sp) == 3 and len(ep) == 3 and sp[0] == ep[0]:
        return ("Leistungszeitraum", f"{sp[2]}.{sp[1]}.–{format_de(end)}")
    return ("Leistungszeitraum", f"{s}–{format_de(end)}")


def service_period_full(start: str, end: str) -> str:
    """Ausgeschriebener Zeitraum für die E-Rechnung: '15.06.2026 – 19.06.2026'."""
    if not start:
        return ""
    s = format_de(start)
    if not end or end == start:
        return s
    return f"{s} – {format_de(end)}"


def format_de(iso_date: str) -> str:
    """'2026-06-19' -> '19.06.2026'. Andere Eingaben unverändert zurück."""
    if not iso_date:
        return ""
    parts = str(iso_date).split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return str(iso_date)
