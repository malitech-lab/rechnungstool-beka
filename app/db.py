"""SQLite-Zugriff und Schema.

Bewusst stdlib-only (sqlite3), damit das Tool ohne Server/Datenbank-Installation
auf einem einzelnen Windows-Rechner läuft. Eine Datei = die komplette Buchhaltung,
einfach zu sichern.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from . import config

SCHEMA = r"""
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Firmenstammdaten (genau ein Datensatz, id = 1)
CREATE TABLE IF NOT EXISTS company (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    name            TEXT NOT NULL DEFAULT '',
    owner           TEXT NOT NULL DEFAULT '',
    legal_form      TEXT NOT NULL DEFAULT '',
    street          TEXT NOT NULL DEFAULT '',
    zip             TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    country         TEXT NOT NULL DEFAULT 'DE',
    phone           TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    website         TEXT NOT NULL DEFAULT '',
    tax_number      TEXT NOT NULL DEFAULT '',   -- Steuernummer
    vat_id          TEXT NOT NULL DEFAULT '',   -- USt-IdNr.
    bank_name       TEXT NOT NULL DEFAULT '',
    iban            TEXT NOT NULL DEFAULT '',
    bic             TEXT NOT NULL DEFAULT '',
    logo_file       TEXT NOT NULL DEFAULT '',   -- Dateiname in ASSETS_DIR
    kleinunternehmer INTEGER NOT NULL DEFAULT 0, -- §19 UStG
    default_tax_rate REAL NOT NULL DEFAULT 19.0,
    payment_terms_days INTEGER NOT NULL DEFAULT 14,
    invoice_prefix  TEXT NOT NULL DEFAULT 'RE',
    customer_prefix TEXT NOT NULL DEFAULT 'K',
    intro_text      TEXT NOT NULL DEFAULT '',    -- Standard-Einleitung
    footer_text     TEXT NOT NULL DEFAULT '',    -- Standard-Schlusstext
    color_primary   TEXT NOT NULL DEFAULT '#1F4E79',
    color_accent    TEXT NOT NULL DEFAULT '#C0392B',
    -- E-Mail-Versand (SMTP) für Rechnungen/Mahnungen
    smtp_host       TEXT NOT NULL DEFAULT '',
    smtp_port       INTEGER NOT NULL DEFAULT 587,
    smtp_user       TEXT NOT NULL DEFAULT '',
    smtp_password   TEXT NOT NULL DEFAULT '',
    smtp_from       TEXT NOT NULL DEFAULT '',
    smtp_security   TEXT NOT NULL DEFAULT 'starttls',  -- starttls | ssl | none
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Kunden
CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_number TEXT UNIQUE,
    kind            TEXT NOT NULL DEFAULT 'B2C',  -- B2B | B2C | B2G (öffentlich)
    company_name    TEXT NOT NULL DEFAULT '',
    contact_name    TEXT NOT NULL DEFAULT '',     -- kombiniert "Vorname Nachname"
    first_name      TEXT NOT NULL DEFAULT '',
    last_name       TEXT NOT NULL DEFAULT '',
    salutation      TEXT NOT NULL DEFAULT '',     -- Herr | Frau | Firma
    street          TEXT NOT NULL DEFAULT '',
    zip             TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    country         TEXT NOT NULL DEFAULT 'DE',
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    vat_id          TEXT NOT NULL DEFAULT '',     -- USt-IdNr. (B2B)
    leitweg_id      TEXT NOT NULL DEFAULT '',     -- Leitweg-ID (B2G/XRechnung)
    e_address       TEXT NOT NULL DEFAULT '',     -- elektr. Adresse f. E-Rechnung
    is_bauleistend  INTEGER NOT NULL DEFAULT 0,   -- §13b: Empfänger erbringt Bauleistungen
    freistellung_48 INTEGER NOT NULL DEFAULT 0,   -- §48 EStG Freistellungsbescheinigung liegt vor
    freistellung_bis TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Leistungs-/Materialkatalog (wiederverwendbare Positionen)
CREATE TABLE IF NOT EXISTS catalog_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL DEFAULT 'leistung', -- leistung | material
    article_number  TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT 'Stk',   -- Std, m², lfm, Stk, pauschal ...
    unit_price      REAL NOT NULL DEFAULT 0,       -- netto
    tax_rate        REAL NOT NULL DEFAULT 19.0,
    active          INTEGER NOT NULL DEFAULT 1
);

-- Rechnungen (Kopf). Stamm-/Adressdaten werden bei Festschreibung als
-- unveränderlicher Snapshot in seller_* / buyer_* gespeichert (GoBD).
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number  TEXT UNIQUE,                  -- erst bei Festschreibung vergeben
    doc_type        TEXT NOT NULL DEFAULT 'standard', -- standard | kleinbetrag | storno | korrektur | angebot | mahnung
    mahn_level      INTEGER NOT NULL DEFAULT 0,   -- Mahnstufe (1=Zahlungserinnerung, 2=1. Mahnung, ...)
    status          TEXT NOT NULL DEFAULT 'entwurf', -- entwurf | festgeschrieben | storniert
    customer_id     INTEGER REFERENCES customers(id),

    title           TEXT NOT NULL DEFAULT '',     -- Betreff / Bauvorhaben
    project_ref     TEXT NOT NULL DEFAULT '',
    invoice_date    TEXT NOT NULL DEFAULT (date('now')),   -- Ausstellungsdatum
    service_date    TEXT NOT NULL DEFAULT '',     -- Leistungszeitraum: von
    service_date_end TEXT NOT NULL DEFAULT '',    -- Leistungszeitraum: bis
    due_date        TEXT NOT NULL DEFAULT '',
    payment_terms_days INTEGER NOT NULL DEFAULT 14,

    tax_mode        TEXT NOT NULL DEFAULT 'regel', -- regel | kleinunternehmer | reverse_charge
    intro_text      TEXT NOT NULL DEFAULT '',
    footer_text     TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',

    skonto_percent  REAL NOT NULL DEFAULT 0,
    skonto_days     INTEGER NOT NULL DEFAULT 0,

    -- Summen (bei Festschreibung berechnet & eingefroren)
    total_net       REAL NOT NULL DEFAULT 0,
    total_tax       REAL NOT NULL DEFAULT 0,
    total_gross     REAL NOT NULL DEFAULT 0,

    references_invoice_id INTEGER REFERENCES invoices(id), -- Original bei Storno/Korrektur

    -- Verkäufer-Snapshot
    seller_json     TEXT NOT NULL DEFAULT '',
    -- Käufer-Snapshot
    buyer_json      TEXT NOT NULL DEFAULT '',

    -- Belegarchiv-Pfade (relativ zu ARCHIVE_DIR)
    pdf_file        TEXT NOT NULL DEFAULT '',
    xml_file        TEXT NOT NULL DEFAULT '',
    zugferd_file    TEXT NOT NULL DEFAULT '',
    pdf_sha256      TEXT NOT NULL DEFAULT '',

    finalized_at    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL DEFAULT 0,
    item_type       TEXT NOT NULL DEFAULT 'leistung', -- leistung | material | text
    article_number  TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    quantity        REAL NOT NULL DEFAULT 1,
    unit            TEXT NOT NULL DEFAULT 'Stk',
    unit_price      REAL NOT NULL DEFAULT 0,        -- netto
    discount_percent REAL NOT NULL DEFAULT 0,
    tax_rate        REAL NOT NULL DEFAULT 19.0
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    date            TEXT NOT NULL DEFAULT (date('now')),
    amount          REAL NOT NULL DEFAULT 0,
    method          TEXT NOT NULL DEFAULT 'Überweisung',
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Lückenlose Nummernkreise je Beleg-Typ und Jahr (GoBD)
CREATE TABLE IF NOT EXISTS counters (
    name            TEXT NOT NULL,   -- z.B. 'rechnung', 'kunde'
    year            INTEGER NOT NULL,
    value           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (name, year)
);

-- Revisionssicheres Protokoll (wer, wann, was)
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL DEFAULT (datetime('now')),
    user            TEXT NOT NULL DEFAULT '',
    action          TEXT NOT NULL,
    entity          TEXT NOT NULL DEFAULT '',
    entity_id       TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '',
    -- Manipulationsschutz: fortlaufende SHA-256-Kette (GoBD-Unveränderbarkeit)
    prev_hash       TEXT NOT NULL DEFAULT '',
    entry_hash      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_items_invoice ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Absturz-/Stromausfall-Sicherheit: WAL überlebt abruptes Herunterfahren ohne
    # Korruption, synchronous=FULL macht jede gespeicherte Buchung dauerhaft
    # (fsync je Commit). busy_timeout vermeidet "database is locked".
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    """Schema anlegen (idempotent) und Grunddaten sicherstellen."""
    config.ensure_dirs()
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
    # Seed erst nach Schema (Import hier, um Zirkelbezug zu vermeiden)
    from . import seed
    seed.ensure_seed()


def _add_col(conn: sqlite3.Connection, table: str, col: str, ddl: str) -> bool:
    """Spalte idempotent ergänzen. Gibt True zurück, wenn neu angelegt.

    Jede Spalte wird einzeln geprüft – so bleibt die Migration auch nach einem
    harten Abbruch mitten in einer Gruppe wiederholbar (kein 'duplicate column')."""
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col in have:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    return True


def _migrate(conn: sqlite3.Connection) -> None:
    """Leichte, idempotente Schema-Migrationen für bestehende Datenbanken."""
    _add_col(conn, "invoices", "service_date_end", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "invoices", "mahn_level", "INTEGER NOT NULL DEFAULT 0")
    _add_col(conn, "invoices", "sent_at", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "invoices", "sent_via", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "company", "smtp_host", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "company", "smtp_port", "INTEGER NOT NULL DEFAULT 587")
    _add_col(conn, "company", "smtp_user", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "company", "smtp_password", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "company", "smtp_from", "TEXT NOT NULL DEFAULT ''")
    _add_col(conn, "company", "smtp_security", "TEXT NOT NULL DEFAULT 'starttls'")
    if _add_col(conn, "audit_log", "entry_hash", "TEXT NOT NULL DEFAULT ''"):
        _add_col(conn, "audit_log", "prev_hash", "TEXT NOT NULL DEFAULT ''")
        # bestehende Einträge nachträglich in die Hash-Kette aufnehmen
        from . import audit
        prev = ""
        for r in conn.execute("SELECT id, ts, user, action, entity, entity_id, detail"
                              " FROM audit_log ORDER BY id ASC").fetchall():
            h = audit.entry_hash(prev, r[1], r[2], r[3], r[4], r[5], r[6])
            conn.execute("UPDATE audit_log SET prev_hash=?, entry_hash=? WHERE id=?",
                         (prev, h, r[0]))
            prev = h
    else:
        _add_col(conn, "audit_log", "prev_hash", "TEXT NOT NULL DEFAULT ''")
    ccols = {r[1] for r in conn.execute("PRAGMA table_info(customers)")}
    if "last_name" not in ccols:
        conn.execute("ALTER TABLE customers ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE customers ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
        # bestehende Namen aufteilen: letztes Wort = Nachname
        for r in conn.execute("SELECT id, contact_name FROM customers").fetchall():
            cn = (r[1] or "").strip()
            if cn:
                parts = cn.split()
                conn.execute("UPDATE customers SET first_name=?, last_name=? WHERE id=?",
                             (" ".join(parts[:-1]), parts[-1], r[0]))


# ---- kleine Query-Helfer -------------------------------------------------

def query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def query_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(params)).fetchone()


def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    cur = conn.execute(sql, tuple(params))
    return cur.lastrowid
