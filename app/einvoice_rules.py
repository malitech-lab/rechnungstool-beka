"""Geschäftsregel-Prüfung der E-Rechnung (EN 16931 / BR-DE).

Die erzeugte E-Rechnung wird beim Serialisieren bereits gegen das XSD-Schema
geprüft (Struktur). Diese Prüfung ergänzt die wichtigsten **Geschäftsregeln**
(BR-* der EN 16931, BR-DE-* für XRechnung) – das ist genau das, was der offizielle
KoSIT-Validator zusätzlich macht. Es ist eine pragmatische Teilmenge der KoSIT-
Schematron-Regeln (kein Java/keine externe Abhängigkeit); für eine vollständige
B2G-Abnahme bleibt der KoSIT-Validator die Referenz.
"""
from __future__ import annotations

from .money import money


def check(ctx: dict) -> dict:
    """Prüft den Render-Kontext gegen die wichtigsten EN-16931-/BR-DE-Regeln.
    Gibt {ok, errors, warnings, checked} zurück (ok = keine Fehler)."""
    company = ctx.get("company", {})
    buyer = ctx.get("buyer", {})
    inv = ctx.get("invoice", {})
    calc = ctx.get("calc")
    errors: list[str] = []
    warnings: list[str] = []

    def err(rule, msg):
        errors.append(f"{rule}: {msg}")

    def warn(rule, msg):
        warnings.append(f"{rule}: {msg}")

    buyer_name = (buyer.get("name_full") or " ".join(buyer.get("name_lines", []))
                  or buyer.get("company_name") or buyer.get("contact_name") or "")

    # ---- EN 16931 Kernregeln (Pflicht – verletzen = E-Rechnung fehlerhaft) ----
    if not inv.get("number"):
        err("BR-02", "Rechnungsnummer fehlt.")
    if not inv.get("invoice_date"):
        err("BR-03", "Ausstellungsdatum fehlt.")
    if not company.get("name"):
        err("BR-06", "Name des Verkäufers fehlt.")
    if not buyer_name.strip():
        err("BR-07", "Name des Käufers fehlt.")
    for k, lbl in (("street", "Straße"), ("zip", "PLZ"), ("city", "Ort")):
        if not company.get(k):
            err("BR-08", f"Verkäufer-Anschrift unvollständig: {lbl} fehlt.")
    for k, lbl in (("zip", "PLZ"), ("city", "Ort")):
        if not buyer.get(k):
            err("BR-10", f"Käufer-Anschrift unvollständig: {lbl} fehlt.")
    if not (company.get("vat_id") or company.get("tax_number")):
        err("BR-CO-26", "Verkäufer ohne USt-IdNr. UND ohne Steuernummer.")

    # ---- Rechnerische Konsistenz (BR-CO-*) ----
    if calc is not None:
        net, tax, gross = calc.total_net, calc.total_tax, calc.total_gross
        if money(net) + money(tax) != money(gross):
            err("BR-CO-15", f"Gesamtbetrag {money(gross)} € ≠ Netto {money(net)} + USt {money(tax)}.")
        for g in getattr(calc, "tax_groups", []) or []:
            base, rate, vat = g.net, g.rate, g.tax
            if money(money(base) * money(rate) / 100) != money(vat):
                warn("BR-CO-17", f"USt der {float(rate):g}%-Gruppe rechnerisch unstimmig "
                                 f"({money(base)} × {float(rate):g}% ≠ {money(vat)}).")

    # ---- BR-DE (XRechnung/B2G): bei ZUGFeRD EN16931 nicht zwingend -> Hinweise ----
    if not company.get("iban"):
        warn("BR-DE-1", "Keine Zahlungsverbindung (IBAN) hinterlegt.")
    if not company.get("email"):
        warn("BR-DE-5", "Keine Verkäufer-E-Mail (für XRechnung/B2G erforderlich).")
    if not company.get("phone"):
        warn("BR-DE-4", "Keine Verkäufer-Telefonnummer (für XRechnung/B2G erforderlich).")

    raw = buyer.get("_raw") or {}
    if raw.get("kind") == "B2G" and not buyer.get("leitweg_id"):
        err("BR-DE-15", "Behörde (B2G) ohne Leitweg-ID – die XRechnung würde abgelehnt.")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "checked": 13}
