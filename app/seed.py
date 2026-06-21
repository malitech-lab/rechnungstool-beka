"""Erstbefüllung: Firmenstammdaten (Montageservice Beka) und Starter-Katalog.

Die öffentlichen Geschäftsdaten stammen von schornstein-beka.de. Steuernummer,
USt-IdNr. und Bankverbindung sind nicht öffentlich und werden beim ersten Start
in den Einstellungen ergänzt (Pflicht für die Rechnungs-Pflichtangaben).
"""
from __future__ import annotations

from . import db


COMPANY = dict(
    name="Montageservice Beka",
    owner="Nehat Beka",
    legal_form="Einzelunternehmen",
    street="Im Vogelgesang 6",
    zip="67346",
    city="Speyer",
    country="DE",
    phone="0176 62756847",
    email="info@schornstein-beka.de",
    website="www.schornstein-beka.de",
    tax_number="",          # >>> in Einstellungen ergänzen
    vat_id="",              # >>> falls vorhanden, in Einstellungen ergänzen
    bank_name="",           # >>> in Einstellungen ergänzen
    iban="",                # >>> in Einstellungen ergänzen
    bic="",                 # >>> in Einstellungen ergänzen
    kleinunternehmer=0,
    default_tax_rate=19.0,
    payment_terms_days=14,
    invoice_prefix="RE",
    customer_prefix="K",
    intro_text="Unsere Lieferung/Leistung stellen wir Ihnen wie folgt in Rechnung.",
    footer_text=(
        "Wir bedanken uns für das entgegengebrachte Vertrauen.\n\n"
        "Bitte begleichen Sie den Gesamtbetrag sofort bei Erhalt der Rechnung ohne Abzug.\n\n"
        "Vielen Dank für die gute Zusammenarbeit."
    ),
    color_primary="#182840",   # BEKA-Navy (aus Original-Logo)
    color_accent="#E07838",    # BEKA-Orange (aus Original-Logo)
)

# Starter-Katalog – Werte sind Vorschläge und können in der Anwendung editiert werden.
CATALOG = [
    # kind, art-nr, name, beschreibung, einheit, netto, steuersatz
    ("leistung", "AZ-MON", "Arbeitszeit Monteur", "Facharbeiterstunde Montage/Installation", "Std", 58.00, 19.0),
    ("leistung", "AZ-HELF", "Arbeitszeit Helfer", "Helferstunde", "Std", 42.00, 19.0),
    ("leistung", "ANF", "Anfahrtspauschale", "Anfahrt im Umkreis von 50 km um Speyer", "pauschal", 35.00, 19.0),
    ("leistung", "SCHO-SAN", "Schornsteinsanierung", "Sanierung/Innenrohr je laufender Meter", "lfm", 95.00, 19.0),
    ("leistung", "SCHO-EDS", "Edelstahlschornstein Montage", "Lieferung und Montage Edelstahlschornstein", "lfm", 145.00, 19.0),
    ("leistung", "OFEN-MON", "Ofen-/Kaminmontage", "Aufstellung und Anschluss Ofen/Kamin", "pauschal", 480.00, 19.0),
    ("leistung", "TROCK", "Trockenbauarbeiten", "Trockenbau je Quadratmeter", "m²", 38.00, 19.0),
    ("leistung", "FLIES", "Fliesenarbeiten", "Verlegung Fliesen je Quadratmeter", "m²", 49.00, 19.0),
    ("leistung", "RENOV", "Renovierungsarbeiten", "Renovierung nach Aufwand", "Std", 52.00, 19.0),
    ("material", "MAT", "Material lt. Aufstellung", "Materiallieferung gemäß Einzelnachweis", "Stk", 0.00, 19.0),
]


def ensure_seed() -> None:
    conn = db.connect()
    try:
        row = db.query_one(conn, "SELECT id FROM company WHERE id = 1")
        if row is None:
            cols = ", ".join(COMPANY.keys())
            ph = ", ".join("?" for _ in COMPANY)
            conn.execute(
                f"INSERT INTO company (id, {cols}) VALUES (1, {ph})",
                tuple(COMPANY.values()),
            )
        # Markenfarben bestehender Installationen auf das BEKA-Design heben
        conn.execute("UPDATE company SET color_primary='#182840' "
                     "WHERE id=1 AND color_primary IN ('#1F4E79','#1F3A5C','')")
        conn.execute("UPDATE company SET color_accent='#E07838' "
                     "WHERE id=1 AND color_accent IN ('#C0392B','#E8823C','')")
        count = db.query_one(conn, "SELECT COUNT(*) AS c FROM catalog_items")["c"]
        if count == 0:
            conn.executemany(
                "INSERT INTO catalog_items (kind, article_number, name, description, unit, unit_price, tax_rate)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                CATALOG,
            )
        conn.commit()
    finally:
        conn.close()
