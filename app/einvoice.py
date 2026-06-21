"""E-Rechnung nach EN 16931: strukturierte CII-XML (XRechnung-kompatibel) und
ZUGFeRD/Factur-X (PDF/A-3 mit eingebettetem XML) – erzeugt mit drafthorse.

Die erzeugte CII-XML entspricht dem EN-16931-Profil und ist die Basis sowohl
für die eigenständige E-Rechnungs-Datei als auch für die in das PDF eingebettete
ZUGFeRD-Datei. Für öffentliche Auftraggeber (B2G) wird die Leitweg-ID als
Käuferreferenz (BT-10) gesetzt.
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal

from drafthorse.models.document import Document
from drafthorse.models.tradelines import LineItem
from drafthorse.models.party import TaxRegistration
from drafthorse.models.note import IncludedNote
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.pdf import attach_xml

from .money import D
from .legal import legal_notes, format_de

# UN/ECE Rec 20 Mengeneinheiten-Codes
UNIT_CODES = {
    "std": "HUR", "stunde": "HUR", "stunden": "HUR", "h": "HUR",
    "m²": "MTK", "qm": "MTK", "m2": "MTK",
    "m³": "MTQ", "m3": "MTQ",
    "lfm": "MTR", "m": "MTR", "laufmeter": "MTR", "rm": "MTR",
    "stk": "H87", "stück": "H87", "st": "H87", "stueck": "H87",
    "pauschal": "C62", "psch": "C62", "pauschale": "C62",
    "kg": "KGM", "l": "LTR", "liter": "LTR",
    "tag": "DAY", "tage": "DAY", "km": "KMT",
}


def unit_code(unit: str) -> str:
    return UNIT_CODES.get((unit or "").strip().lower(), "C62")


def _vat_category(tax_mode: str, rate: Decimal):
    """(category_code, exemption_reason) nach EN 16931."""
    if tax_mode == "reverse_charge":
        return "AE", "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)"
    if tax_mode == "kleinunternehmer":
        return "E", "Steuerbefreit – Kleinunternehmer nach § 19 UStG"
    if rate == 0:
        return "Z", None
    return "S", None


def _iso(date_str: str) -> _dt.date:
    try:
        y, m, d = str(date_str).split("-")
        return _dt.date(int(y), int(m), int(d))
    except Exception:
        return _dt.date.today()


def build_document(ctx: dict) -> Document:
    company = ctx["company"]
    buyer = ctx["buyer"]
    inv = ctx["invoice"]
    calc = ctx["calc"]
    tax_mode = inv.get("tax_mode", "regel")

    doc = Document()
    # EN-16931-Profil (gültig für ZUGFeRD EN16931 und als EN16931-CII)
    doc.context.guideline_parameter.id = "urn:cen.eu:en16931:2017"

    is_storno = inv.get("doc_type") == "storno"
    doc.header.id = inv.get("number", "")
    # 380 = Handelsrechnung, 381 = Gutschrift/Storno (EN 16931 ExchangedDocument
    # kennt keinen Name/Title – der Typ ergibt sich aus dem TypeCode)
    doc.header.type_code = "381" if is_storno else "380"
    doc.header.issue_date_time = _iso(inv.get("invoice_date"))

    # Hinweise / Pflichttexte
    for note in legal_notes(company, buyer.get("_raw"), inv):
        n = IncludedNote()
        n.content = note
        doc.header.notes.add(n)
    if inv.get("service_date"):
        n = IncludedNote()
        label = inv.get("service_label", "Leistungsdatum")
        value = inv.get("service_full") or format_de(inv["service_date"])
        n.content = f"{label}: {value}"
        doc.header.notes.add(n)

    # ---- Verkäufer ----
    s = doc.trade.agreement.seller
    s.name = company.get("name", "")
    s.address.line_one = company.get("street", "")
    s.address.postcode = company.get("zip", "")
    s.address.city_name = company.get("city", "")
    s.address.country_id = company.get("country", "DE") or "DE"
    if company.get("vat_id"):
        s.tax_registrations.add(TaxRegistration(id=("VA", company["vat_id"])))
    if company.get("tax_number"):
        s.tax_registrations.add(TaxRegistration(id=("FC", company["tax_number"])))
    if company.get("email"):
        try:
            s.electronic_address = ("EM", company["email"])
        except Exception:
            pass

    # ---- Käufer ----
    b = doc.trade.agreement.buyer
    b.name = buyer.get("name_full") or " ".join(buyer.get("name_lines", [])) or "Endkunde"
    b.address.line_one = buyer.get("street", "")
    b.address.postcode = buyer.get("zip", "")
    b.address.city_name = buyer.get("city", "")
    b.address.country_id = buyer.get("country", "DE") or "DE"
    if buyer.get("vat_id"):
        b.tax_registrations.add(TaxRegistration(id=("VA", buyer["vat_id"])))
    # BT-10 Käuferreferenz / Leitweg-ID (Pflicht bei B2G/XRechnung)
    if buyer.get("leitweg_id"):
        doc.trade.agreement.buyer_reference = buyer["leitweg_id"]
    elif buyer.get("customer_number"):
        doc.trade.agreement.buyer_reference = buyer["customer_number"]

    # ---- Positionen ----
    pos = 0
    for line in calc.lines:
        if line.item_type == "text":
            continue
        pos += 1
        li = LineItem()
        li.document.line_id = str(pos)
        li.product.name = line.name or "Position"
        if line.description:
            li.product.description = line.description
        # Netto-Einzelpreis (Rabatt eingerechnet)
        qty = D(line.quantity) or Decimal("1")
        net_unit = (D(line.line_net) / qty) if qty != 0 else D(line.unit_price)
        li.agreement.gross.amount = D(line.unit_price)
        li.agreement.gross.basis_quantity = (Decimal("1"), unit_code(line.unit))
        li.agreement.net.amount = net_unit
        li.agreement.net.basis_quantity = (Decimal("1"), unit_code(line.unit))
        li.delivery.billed_quantity = (qty, unit_code(line.unit))
        cat, reason = _vat_category(tax_mode, D(line.tax_rate))
        li.settlement.trade_tax.type_code = "VAT"
        li.settlement.trade_tax.category_code = cat
        li.settlement.trade_tax.rate_applicable_percent = D(line.tax_rate)
        li.settlement.monetary_summation.total_amount = D(line.line_net)
        doc.trade.items.add(li)

    # ---- Steueraufschlüsselung (Belegebene) ----
    from drafthorse.models.accounting import ApplicableTradeTax
    if calc.tax_groups:
        for g in calc.tax_groups:
            tt = ApplicableTradeTax()
            tt.calculated_amount = D(g.tax)
            tt.basis_amount = D(g.net)
            tt.type_code = "VAT"
            cat, reason = _vat_category(tax_mode, D(g.rate))
            tt.category_code = cat
            tt.rate_applicable_percent = D(g.rate)
            if reason:
                tt.exemption_reason = reason
            doc.trade.settlement.trade_tax.add(tt)
    else:
        tt = ApplicableTradeTax()
        tt.calculated_amount = D(calc.total_tax)
        tt.basis_amount = D(calc.total_net)
        tt.type_code = "VAT"
        cat, reason = _vat_category(tax_mode, Decimal("0"))
        tt.category_code = cat
        tt.rate_applicable_percent = Decimal("0")
        if reason:
            tt.exemption_reason = reason
        doc.trade.settlement.trade_tax.add(tt)

    # ---- Zahlung ----
    doc.trade.settlement.currency_code = "EUR"
    if company.get("iban"):
        pm = PaymentMeans()
        pm.type_code = "58"  # SEPA-Überweisung
        pm.payee_account.iban = company["iban"].replace(" ", "")
        if company.get("bank_name"):
            pm.payee_account.account_name = company["name"]
        doc.trade.settlement.payment_means.add(pm)

    pt = PaymentTerms()
    pt.description = ctx.get("payment_text", "") or "Zahlbar nach Erhalt."
    if inv.get("due_date"):
        pt.due = _iso(inv["due_date"])
    doc.trade.settlement.terms.add(pt)

    # ---- Summen ----
    ms = doc.trade.settlement.monetary_summation
    ms.line_total = D(calc.total_net)
    ms.charge_total = Decimal("0.00")
    ms.allowance_total = Decimal("0.00")
    ms.tax_basis_total = D(calc.total_net)
    ms.tax_total = (D(calc.total_tax), "EUR")
    ms.grand_total = D(calc.total_gross)
    ms.prepaid_total = Decimal("0.00")
    ms.due_amount = D(calc.total_gross)

    return doc


def cii_xml(ctx: dict) -> bytes:
    """EN-16931-konforme CII-XML (XRechnung-kompatibel / Factur-X)."""
    doc = build_document(ctx)
    return doc.serialize(schema="FACTUR-X_EN16931")


def zugferd_pdf(pdf_bytes: bytes, xml_bytes: bytes) -> bytes:
    """Bettet die CII-XML in das PDF ein -> ZUGFeRD/Factur-X (EN 16931)."""
    return attach_xml(pdf_bytes, xml_bytes, level="EN 16931")
