"""DATEV-Export (EXTF-Buchungsstapel, Format 700) für den Steuerberater.

Erzeugt einen Buchungsstapel im DATEV-EXTF-Format. Die Kontenzuordnung
(Erlöskonten, Debitorenkonten, Kontenrahmen SKR03/SKR04) ist mit dem
Steuerberater abzustimmen – die Vorgaben unten sind SKR03-Standardwerte und
in den Konstanten anpassbar. Zusätzlich gibt es einen einfachen Umsatz-CSV.
"""
from __future__ import annotations

import csv
import io
import datetime as _dt

from .money import money, fmt

# --- Konto-Standardwerte (SKR03) – mit Steuerberater abstimmen --------------
ERLOES_KONTO = {19.0: "8400", 7.0: "8300", 0.0: "8200"}  # Erlöse 19/7/0 %
DEBITOR_SAMMEL = "10000"   # Sammel-Debitor, falls kein Einzeldebitor gepflegt
SACHKONTEN_LEN = 4


def _de_amount(value) -> str:
    return fmt(value).replace(".", "")  # DATEV: 1234,56 (ohne Tausenderpunkt)


def extf_buchungsstapel(invoices: list[dict], berater: str = "", mandant: str = "",
                        wj_beginn: str | None = None) -> str:
    """invoices: Liste von Dicts mit Schlüsseln number, invoice_date (ISO),
    total_gross, tax_groups (Liste (rate, net, tax)), buyer_name, doc_type."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")

    today = _dt.date.today()
    year = today.year
    wj = wj_beginn or f"{year}0101"
    dates = [i["invoice_date"].replace("-", "") for i in invoices if i.get("invoice_date")]
    von = min(dates) if dates else f"{year}0101"
    bis = max(dates) if dates else f"{year}1231"
    ts = today.strftime("%Y%m%d%H%M%S") + "000"

    # Kopfzeile (DATEV-Format-Header, Format 700, Buchungsstapel V13)
    header = ["EXTF", "700", "21", "Buchungsstapel", "13", ts, "", "", "", "",
              "", berater or "", mandant or "", wj, str(SACHKONTEN_LEN), von, bis,
              "Rechnungen Montageservice Beka", "", "1", "0", "0", "EUR",
              "", "", "", "", "", "", "", ""]
    w.writerow(header)

    # Spaltenüberschriften
    w.writerow([
        "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz",
        "Kurs", "Basis-Umsatz", "WKZ Basis-Umsatz", "Konto",
        "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum",
        "Belegfeld 1", "Belegfeld 2", "Skonto", "Buchungstext",
    ])

    for inv in invoices:
        beleg = inv["invoice_date"].replace("-", "")  # YYYYMMDD
        belegdatum = beleg[6:8] + beleg[4:6]          # TTMM
        sh = "S"  # Forderung: Debitor im Soll
        debitor = inv.get("debitor_konto") or DEBITOR_SAMMEL
        text = (inv.get("buyer_name") or "")[:60]
        # je Steuersatz eine Buchung auf das passende Erlöskonto
        groups = inv.get("tax_groups") or [(0.0, inv.get("total_net", 0), inv.get("total_tax", 0))]
        for rate, net, tax in groups:
            brutto = money(net) + money(tax)
            erloes = ERLOES_KONTO.get(float(rate), "8400")
            w.writerow([
                _de_amount(brutto), sh, "EUR", "", "", "", debitor, erloes, "",
                belegdatum, inv.get("number", ""), "", "",
                f"{text} {inv.get('number','')}".strip(),
            ])
    return out.getvalue()


def umsatz_csv(invoices: list[dict]) -> str:
    """Einfache, gut lesbare Umsatzliste (CSV, semikolongetrennt)."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow(["Rechnungsnummer", "Datum", "Kunde", "Netto", "USt", "Brutto",
                "Bezahlt", "Offen", "Status"])
    for inv in invoices:
        w.writerow([
            inv.get("number", ""), inv.get("invoice_date", ""), inv.get("buyer_name", ""),
            fmt(inv.get("total_net", 0)), fmt(inv.get("total_tax", 0)),
            fmt(inv.get("total_gross", 0)), fmt(inv.get("paid", 0)),
            fmt(inv.get("open", 0)), inv.get("status", ""),
        ])
    return out.getvalue()
