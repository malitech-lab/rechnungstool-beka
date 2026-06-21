"""Lückenlose, fortlaufende Nummernkreise (GoBD).

Format für Rechnungen/Angebote: PREFIX-JJJJMM-NNN, z. B. RE-202606-100.
Der Zähler beginnt je Monat bei 100 und wird lückenlos hochgezählt. Die Nummer
wird erst bei der PDF-Erstellung (Festschreibung) vergeben.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3

START = 100  # erste Nummer je Monat


def _yyyymm(when: _dt.date) -> int:
    return when.year * 100 + when.month


def _next_value(conn: sqlite3.Connection, name: str, period: int) -> int:
    conn.execute(
        "INSERT INTO counters (name, year, value) VALUES (?, ?, 0)"
        " ON CONFLICT(name, year) DO NOTHING",
        (name, period),
    )
    conn.execute(
        "UPDATE counters SET value = value + 1 WHERE name = ? AND year = ?",
        (name, period),
    )
    row = conn.execute(
        "SELECT value FROM counters WHERE name = ? AND year = ?", (name, period)
    ).fetchone()
    return int(row[0])


def next_doc_number(conn: sqlite3.Connection, kind: str, prefix: str,
                    when: _dt.date | None = None) -> str:
    """Nächste Belegnummer PREFIX-JJJJMM-NNN (NNN ab 100, je Monat lückenlos)."""
    when = when or _dt.date.today()
    ym = _yyyymm(when)
    seq = _next_value(conn, kind, ym) + (START - 1)
    return f"{prefix}-{ym}-{seq}"


def next_invoice_number(conn, prefix: str = "RE", when=None) -> str:
    return next_doc_number(conn, "rechnung", prefix, when)


def next_offer_number(conn, prefix: str = "AG", when=None) -> str:
    return next_doc_number(conn, "angebot", prefix, when)


def next_dunning_number(conn, prefix: str = "MA", when=None) -> str:
    return next_doc_number(conn, "mahnung", prefix, when)


def peek_doc_number(conn, kind: str, prefix: str, when: _dt.date | None = None) -> str:
    """Vorschau der nächsten Nummer ohne Hochzählen."""
    when = when or _dt.date.today()
    ym = _yyyymm(when)
    row = conn.execute(
        "SELECT value FROM counters WHERE name = ? AND year = ?", (kind, ym)
    ).fetchone()
    seq = (int(row[0]) if row else 0) + 1 + (START - 1)
    return f"{prefix}-{ym}-{seq}"


def peek_invoice_number(conn, prefix: str = "RE", when=None) -> str:
    return peek_doc_number(conn, "rechnung", prefix, when)


def next_customer_number(conn: sqlite3.Connection, prefix: str = "K") -> str:
    # Kundennummer ist jahresübergreifend fortlaufend.
    seq = _next_value(conn, "kunde", 0)
    return f"{prefix}-{seq:04d}"
