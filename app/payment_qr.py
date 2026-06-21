"""GiroCode / EPC-QR-Code (EPC069-12) für die SEPA-Überweisung.

Erzeugt einen QR-Code, den der Kunde in seiner Banking-App scannen kann –
IBAN, Empfänger, Betrag und Verwendungszweck (Rechnungsnummer) sind dann
vorausgefüllt. Reine Python-Bibliothek (segno), keine nativen Abhängigkeiten.
"""
from __future__ import annotations

import io

import segno

from .money import money


def girocode_png(name: str, iban: str, bic: str, amount, reference: str,
                 dark: str = "#1F3A5C") -> bytes | None:
    """PNG-Bytes des GiroCodes – oder None, wenn nicht sinnvoll (keine IBAN,
    Betrag <= 0)."""
    iban = (iban or "").replace(" ", "").strip()
    if not iban:
        return None
    amt = money(amount)
    if amt <= 0:
        return None

    # EPC069-12 Datensatz (Service Tag BCD)
    fields = [
        "BCD",                 # Service Tag
        "002",                 # Version (002: BIC optional bei DE)
        "1",                   # Zeichensatz: UTF-8
        "SCT",                 # SEPA Credit Transfer
        (bic or "").replace(" ", ""),
        (name or "")[:70],
        iban,
        f"EUR{amt:.2f}",       # Betrag
        "",                    # Zweckcode (optional)
        "",                    # strukturierte Referenz (optional)
        (reference or "")[:140],   # Verwendungszweck (unstrukturiert)
        "",                    # Hinweis (optional)
    ]
    payload = "\n".join(fields).rstrip("\n")

    qr = segno.make(payload, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=1, dark=dark, light="white")
    return buf.getvalue()
