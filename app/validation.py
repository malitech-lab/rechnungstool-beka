"""Prüfung der Rechnungs-Pflichtangaben (§§ 14, 14a UStG, § 33 UStDV).

Fehler (level 'error') blockieren die Festschreibung, Hinweise (level 'warn')
informieren nur. Das Tool stellt damit sicher, dass keine Rechnung ohne die
gesetzlich vorgeschriebenen Angaben festgeschrieben wird.
"""
from __future__ import annotations

from dataclasses import dataclass

from .invoice_calc import is_small_amount


@dataclass
class Finding:
    level: str   # 'error' | 'warn'
    field: str
    message: str


def _missing(d: dict, key: str) -> bool:
    v = d.get(key)
    return v is None or str(v).strip() == ""


def _is_iso(value) -> bool:
    s = str(value or "")
    return len(s) == 10 and s[4] == "-" and s[7] == "-"


def validate(company: dict, customer: dict | None, invoice: dict,
             items: list[dict], total_gross) -> list[Finding]:
    f: list[Finding] = []
    small = is_small_amount(total_gross)
    tax_mode = invoice.get("tax_mode", "regel")
    klein = company.get("kleinunternehmer") or tax_mode == "kleinunternehmer"

    # --- Leistender Unternehmer (Firma) -----------------------------------
    for key, label in (("name", "Firmenname"), ("street", "Straße"),
                        ("zip", "PLZ"), ("city", "Ort")):
        if _missing(company, key):
            f.append(Finding("error", f"company.{key}",
                             f"Firmenstammdaten unvollständig: {label} fehlt (Einstellungen)."))
    if _missing(company, "tax_number") and _missing(company, "vat_id"):
        f.append(Finding("error", "company.tax_number",
                         "Steuernummer oder USt-IdNr. fehlt – Pflichtangabe (§ 14 Abs. 4 UStG). "
                         "In den Einstellungen ergänzen."))
    if _missing(company, "iban"):
        f.append(Finding("warn", "company.iban",
                         "Keine IBAN hinterlegt – ohne Bankverbindung kann der Kunde nicht zahlen."))

    # --- Leistungsempfänger ------------------------------------------------
    if customer is None:
        f.append(Finding("error", "customer", "Kein Kunde ausgewählt."))
    else:
        if _missing(customer, "city") or _missing(customer, "zip"):
            f.append(Finding("error", "customer.address", "Anschrift des Empfängers unvollständig (PLZ/Ort)."))
        name_ok = not (_missing(customer, "company_name") and _missing(customer, "contact_name"))
        if not name_ok:
            f.append(Finding("error", "customer.name", "Name des Leistungsempfängers fehlt."))
        if not small and _missing(customer, "street"):
            f.append(Finding("error", "customer.street", "Straße des Empfängers fehlt (bei Rechnungen über 250 € erforderlich)."))
        if tax_mode == "reverse_charge" and _missing(customer, "vat_id"):
            f.append(Finding("warn", "customer.vat_id",
                             "§ 13b: USt-IdNr. des Empfängers empfohlen."))

    # --- Beleg-Pflichtangaben ---------------------------------------------
    if _missing(invoice, "invoice_date"):
        f.append(Finding("error", "invoice.invoice_date", "Ausstellungsdatum fehlt."))
    if invoice.get("doc_type") not in ("angebot", "mahnung") and _missing(invoice, "service_date"):
        f.append(Finding("error", "invoice.service_date",
                         "Leistungsdatum/-zeitraum fehlt – Pflichtangabe (§ 14 Abs. 4 Nr. 6 UStG)."))
    elif (_is_iso(invoice.get("service_date")) and _is_iso(invoice.get("service_date_end"))
          and str(invoice["service_date_end"]) < str(invoice["service_date"])):
        f.append(Finding("error", "invoice.service_date_end",
                         "Leistungszeitraum: das Bis-Datum liegt vor dem Von-Datum."))

    # --- Positionen --------------------------------------------------------
    real_items = [it for it in items if it.get("item_type") != "text"]
    if not real_items:
        f.append(Finding("error", "items", "Die Rechnung enthält keine berechenbare Position."))
    for i, it in enumerate(items, start=1):
        if it.get("item_type") == "text":
            continue
        if _missing(it, "name"):
            f.append(Finding("error", f"items.{i}.name", f"Position {i}: Leistungsbeschreibung fehlt."))
        try:
            if float(it.get("quantity") or 0) == 0:
                f.append(Finding("warn", f"items.{i}.quantity", f"Position {i}: Menge ist 0."))
        except (TypeError, ValueError):
            f.append(Finding("error", f"items.{i}.quantity", f"Position {i}: Menge ist keine Zahl."))

    # --- Steuer / Sondermodi ----------------------------------------------
    if not klein and tax_mode == "regel":
        for it in real_items:
            try:
                if float(it.get("tax_rate") or 0) not in (0.0, 7.0, 19.0):
                    f.append(Finding("warn", "items.tax_rate",
                                     "Ungewöhnlicher Steuersatz – bitte prüfen (üblich: 0 %, 7 %, 19 %)."))
                    break
            except (TypeError, ValueError):
                pass

    return f


def errors(findings: list[Finding]) -> list[Finding]:
    return [x for x in findings if x.level == "error"]


def warnings(findings: list[Finding]) -> list[Finding]:
    return [x for x in findings if x.level == "warn"]
