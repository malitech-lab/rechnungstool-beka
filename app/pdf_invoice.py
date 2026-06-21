"""Erzeugt die PDF-Rechnung im Corporate Design (fpdf2).

Klassisches deutsches Handwerker-Layout: Briefkopf, Anschriftenfeld (DIN-5008-
Position für Fensterumschlag), Info-Block, Positionstabelle, Steueraufschlüsselung,
Pflichthinweise und Fußzeile mit Steuer-/Bankangaben.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from fpdf import FPDF

from .money import fmt, fmt_eur, fmt_qty, D
from .legal import format_de
from . import config, payment_qr

FONT_DIR = Path(__file__).parent / "static" / "fonts"


def _hex(color: str):
    color = (color or "#000000").lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


class InvoicePDF(FPDF):
    def __init__(self, company: dict, primary, accent, **kw):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.company = company
        self.primary = primary
        self.accent = accent
        self.has_unicode = False
        self.set_auto_page_break(auto=True, margin=32)
        self.set_margins(20, 15, 20)
        self._register_fonts()

    def _register_fonts(self):
        regular = FONT_DIR / "DejaVuSans.ttf"
        bold = FONT_DIR / "DejaVuSans-Bold.ttf"
        if regular.exists() and bold.exists():
            self.add_font("dejavu", "", str(regular))
            self.add_font("dejavu", "B", str(bold))
            self.base_font = "dejavu"
            self.has_unicode = True
        else:
            self.base_font = "helvetica"

    def t(self, s: str) -> str:
        """Text fürs Core-Font absichern (€ -> EUR), wenn keine Unicode-Schrift."""
        if self.has_unicode:
            return s
        return (s or "").replace("€", "EUR").replace("–", "-").replace("·", "-")

    def footer(self):
        self.set_y(-30)
        self.set_draw_color(*self.primary)
        self.set_line_width(0.3)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(1.5)
        c = self.company
        self.set_font(self.base_font, "", 7.5)
        self.set_text_color(90, 90, 90)
        col_w = 56.6
        addr = f"{c.get('name','')}\n{c.get('street','')}\n{c.get('zip','')} {c.get('city','')}"
        contact = f"Tel.: {c.get('phone','')}\nE-Mail: {c.get('email','')}\n{c.get('website','')}"
        tax = c.get("tax_number", "")
        vat = c.get("vat_id", "")
        taxline = []
        if tax:
            taxline.append(f"Steuer-Nr.: {tax}")
        if vat:
            taxline.append(f"USt-IdNr.: {vat}")
        bank = []
        if c.get("bank_name"):
            bank.append(c["bank_name"])
        if c.get("iban"):
            bank.append(f"IBAN: {c['iban']}")
        if c.get("bic"):
            bank.append(f"BIC: {c['bic']}")
        finance = "\n".join(taxline + bank) or " "
        y0 = self.get_y()
        self.set_xy(20, y0)
        self.multi_cell(col_w, 3.4, self.t(addr), align="L")
        self.set_xy(20 + col_w, y0)
        self.multi_cell(col_w, 3.4, self.t(contact), align="L")
        self.set_xy(20 + 2 * col_w, y0)
        self.multi_cell(col_w, 3.4, self.t(finance), align="L")
        # Seitenzahl
        self.set_xy(20, -8)
        self.set_font(self.base_font, "", 7)
        self.cell(170, 4, self.t(f"Seite {self.page_no()} von {{nb}}"), align="R")


def render(ctx: dict) -> bytes:
    company = ctx["company"]
    buyer = ctx["buyer"]
    inv = ctx["invoice"]
    calc = ctx["calc"]
    notes = ctx.get("notes", [])
    primary = _hex(company.get("color_primary", "#1F4E79"))
    accent = _hex(company.get("color_accent", "#C0392B"))

    pdf = InvoicePDF(company, primary, accent)
    pdf.set_title(f"Rechnung {inv.get('number','')}")
    pdf.set_author(company.get("name", ""))
    pdf.alias_nb_pages()
    pdf.add_page()
    bf = pdf.base_font

    # ---- Briefkopf -------------------------------------------------------
    logo = ctx.get("logo_path")
    top_y = 14
    has_logo = False
    if logo and os.path.exists(logo):
        try:
            pdf.image(logo, x=20, y=top_y, w=62)  # Logo enthält bereits den Firmennamen
            has_logo = True
        except Exception:
            has_logo = False
    if not has_logo:
        pdf.set_xy(20, top_y)
        pdf.set_text_color(*primary)
        pdf.set_font(bf, "B", 20)
        pdf.cell(120, 9, pdf.t(company.get("name", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(20, 36)
    pdf.set_font(bf, "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(120, 5, pdf.t("Markenqualität · Festpreis · Alles aus einer Hand"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # ---- Absenderzeile + Empfänger (DIN 5008) ---------------------------
    pdf.set_xy(20, 45)
    pdf.set_font(bf, "", 7)
    pdf.set_text_color(110, 110, 110)
    sender = f"{company.get('name','')} · {company.get('street','')} · {company.get('zip','')} {company.get('city','')}"
    pdf.cell(90, 4, pdf.t(sender), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(bf, "", 11)
    for line in buyer.get("name_lines", []):
        pdf.set_x(20)
        pdf.cell(90, 5.2, pdf.t(line), new_x="LMARGIN", new_y="NEXT")
    if buyer.get("street"):
        pdf.set_x(20)
        pdf.cell(90, 5.2, pdf.t(buyer["street"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(20)
    pdf.cell(90, 5.2, pdf.t(f"{buyer.get('zip','')} {buyer.get('city','')}"),
             new_x="LMARGIN", new_y="NEXT")
    if buyer.get("country") and buyer.get("country") != "DE":
        pdf.set_x(20)
        pdf.cell(90, 5.2, pdf.t(buyer["country"]), new_x="LMARGIN", new_y="NEXT")

    # ---- Info-Block rechts ----------------------------------------------
    info_y = 52
    pdf.set_xy(125, info_y)
    pdf.set_font(bf, "", 9)
    is_offer = inv.get("doc_type") == "angebot"
    is_dunning = inv.get("doc_type") == "mahnung"
    nr_label = ("Angebot-Nr." if is_offer else
                "Mahnung-Nr." if is_dunning else "Rechnungs-Nr.")
    rows = [
        (nr_label, inv.get("number", "")),
        ("Datum", format_de(inv.get("invoice_date", ""))),
    ]
    if is_dunning:     # Mahnung: neue Zahlungsfrist statt Leistungsdatum
        rows.append(("Zahlbar bis", format_de(inv.get("due_date", ""))))
    elif not is_offer:  # Angebot hat noch kein Leistungsdatum
        rows.append((inv.get("service_label", "Leistungsdatum"), inv.get("service_value", "")))
    rows.append(("Kunden-Nr.", buyer.get("customer_number", "")))
    if buyer.get("vat_id"):
        rows.append(("USt-IdNr. Kunde", buyer["vat_id"]))
    if inv.get("reference_number"):
        rows.append(("Bezug Rechnung", inv["reference_number"]))
    for label, value in rows:
        pdf.set_x(125)
        pdf.set_font(bf, "", 9)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(30, 5, pdf.t(label), new_x="RIGHT", new_y="TOP")
        pdf.set_text_color(0, 0, 0)
        val = pdf.t(str(value))
        pdf.set_font(bf, "", 8 if pdf.get_string_width(val) > 34 else 9)
        pdf.cell(35, 5, val, new_x="LMARGIN", new_y="NEXT", align="R")
    pdf.set_font(bf, "", 9)

    # ---- Titel -----------------------------------------------------------
    pdf.set_y(max(pdf.get_y(), 88))
    pdf.set_x(20)
    pdf.set_font(bf, "B", 15)
    pdf.set_text_color(*primary)
    title_map = {"storno": "Stornorechnung", "korrektur": "Korrekturrechnung",
                 "kleinbetrag": "Kleinbetragsrechnung", "angebot": "Angebot"}
    if is_dunning:
        lvl = int(inv.get("mahn_level") or 1)
        htitle = "Zahlungserinnerung" if lvl <= 1 else f"{lvl - 1}. Mahnung"
    else:
        htitle = title_map.get(inv.get("doc_type"), "Rechnung")
    pdf.cell(170, 8, pdf.t(f"{htitle} Nr. {inv.get('number','')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    if inv.get("title"):
        pdf.set_font(bf, "B", 10)
        pdf.set_x(20)
        pdf.cell(170, 6, pdf.t(inv["title"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # ---- Einleitung (Standardtext, keine persönliche Anrede) ------------
    if inv.get("intro_text"):
        pdf.set_font(bf, "", 10)
        pdf.set_x(20)
        pdf.multi_cell(170, 5, pdf.t(inv["intro_text"]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # ---- Positionstabelle ------------------------------------------------
    # Spalten: Pos | Bezeichnung | Menge | Einheit | Einzel € | Gesamt €
    cols = [10, 80, 18, 16, 22, 24]
    headers = ["Pos", "Bezeichnung", "Menge", "Einheit", "Einzel €", "Gesamt €"]
    aligns = ["C", "L", "R", "L", "R", "R"]

    def header_row():
        pdf.set_font(bf, "B", 9)
        pdf.set_fill_color(*primary)
        pdf.set_text_color(255, 255, 255)
        pdf.set_x(20)
        for w, h, a in zip(cols, headers, aligns):
            pdf.cell(w, 7, pdf.t(h), border=0, align=a, fill=True)
        pdf.ln(7)
        pdf.set_text_color(0, 0, 0)

    NAME_H = 4.8
    DESC_H = 4.4

    def measure(text, w, line_h, style):
        pdf.set_font(bf, style, 9 if style == "B" else 8.5)
        try:
            lines = pdf.multi_cell(w, line_h, pdf.t(text), dry_run=True, output="LINES")
            return max(1, len(lines))
        except Exception:
            # Fallback: grobe Schätzung
            return max(1, int(pdf.get_string_width(pdf.t(text)) // (w - 1)) + 1)

    header_row()
    pdf.set_font(bf, "", 9)
    fill = False
    for i, line in enumerate(calc.lines, start=1):
        desc = line.description or ""
        if D(line.discount_percent) > 0:
            extra = f"abzgl. {('%g' % float(line.discount_percent))} % Rabatt"
            desc = (desc + "  —  " + extra) if desc else extra

        name_lines = measure(line.name, cols[1], NAME_H, "B")
        desc_lines = measure(desc, cols[1], DESC_H, "") if desc else 0
        row_h = 1.2 + name_lines * NAME_H + (desc_lines * DESC_H if desc else 0) + 1.2
        row_h = max(row_h, 7)

        if pdf.get_y() + row_h > pdf.page_break_trigger:
            pdf.add_page()
            header_row()
            pdf.set_font(bf, "", 9)

        y0 = pdf.get_y()
        x0 = 20
        if fill:
            pdf.set_fill_color(244, 247, 251)
            pdf.rect(x0, y0, sum(cols), row_h, style="F")
        fill = not fill

        if line.item_type == "text":
            pdf.set_xy(x0 + 1, y0 + 1.2)
            pdf.set_font(bf, "B", 9)
            pdf.multi_cell(sum(cols) - 2, NAME_H, pdf.t(line.name), new_x="LMARGIN", new_y="NEXT")
            if desc:
                pdf.set_x(x0 + 1)
                pdf.set_font(bf, "", 8.5)
                pdf.set_text_color(90, 90, 90)
                pdf.multi_cell(sum(cols) - 2, DESC_H, pdf.t(desc))
                pdf.set_text_color(0, 0, 0)
            pdf.set_y(y0 + row_h)
            continue

        # Zahlen-/Pos-Spalten zuerst (einzeilig, oben ausgerichtet)
        pdf.set_font(bf, "", 9)
        pdf.set_xy(x0, y0 + 1.2)
        pdf.cell(cols[0], NAME_H, pdf.t(str(i)), align="C")
        pdf.set_xy(x0 + cols[0] + cols[1], y0 + 1.2)
        pdf.cell(cols[2], NAME_H, pdf.t(fmt_qty(line.quantity)), align="R")
        pdf.cell(cols[3], NAME_H, pdf.t(" " + (line.unit or "")), align="L")
        pdf.cell(cols[4], NAME_H, pdf.t(fmt(line.unit_price)), align="R")
        pdf.cell(cols[5], NAME_H, pdf.t(fmt(line.line_net)), align="R")
        # Bezeichnung + Beschreibung (untereinander)
        pdf.set_xy(x0 + cols[0], y0 + 1.2)
        pdf.set_font(bf, "B", 9)
        pdf.multi_cell(cols[1], NAME_H, pdf.t(line.name), new_x="LMARGIN", new_y="NEXT")
        if desc:
            pdf.set_x(x0 + cols[0])
            pdf.set_font(bf, "", 8.5)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(cols[1], DESC_H, pdf.t(desc))
            pdf.set_text_color(0, 0, 0)
        pdf.set_y(y0 + row_h)

    pdf.set_draw_color(*primary)
    pdf.set_line_width(0.3)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(3)

    # ---- Summenblock (rechts) -------------------------------------------
    # Mahnung: keine MwSt-Aufschlüsselung (die Steuer steckt in der Originalrechnung)
    no_vat = is_dunning or inv.get("tax_mode") in ("kleinunternehmer", "reverse_charge")
    sum_x = 110
    sum_w_label = 50
    sum_w_val = 30

    def sum_row(label, value, bold=False, big=False):
        pdf.set_x(sum_x)
        pdf.set_font(bf, "B" if bold else "", 11 if big else 9.5)
        pdf.cell(sum_w_label, 6 if big else 5, pdf.t(label), align="L")
        pdf.cell(sum_w_val, 6 if big else 5, pdf.t(value), align="R", new_x="LMARGIN", new_y="NEXT")

    if no_vat:
        sum_row("Offener Betrag" if is_dunning else "Gesamtbetrag",
                fmt_eur(calc.total_net), bold=True, big=True)
    else:
        sum_row("Zwischensumme netto", fmt_eur(calc.total_net))
        for g in calc.tax_groups:
            sum_row(f"zzgl. {('%g' % float(g.rate))}% MwSt auf {fmt(g.net)}", fmt_eur(g.tax))
        pdf.set_x(sum_x)
        pdf.set_draw_color(*primary)
        pdf.line(sum_x, pdf.get_y() + 0.5, 190, pdf.get_y() + 0.5)
        pdf.ln(1.5)
        pdf.set_text_color(*accent)
        total_label = "Angebotssumme" if inv.get("doc_type") == "angebot" else "Rechnungsbetrag"
        sum_row(total_label, fmt_eur(calc.total_gross), bold=True, big=True)
        pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # ---- GiroCode (QR) für die Überweisung ------------------------------
    qr_png = None
    if inv.get("doc_type") not in ("storno", "angebot"):
        # Bei der Mahnung verweist der Verwendungszweck auf die Original-Rechnung
        qr_ref = inv.get("reference_number") if is_dunning else inv.get("number", "")
        qr_png = payment_qr.girocode_png(
            # Empfänger = Kontoinhaber (Inhaber), nicht der Firmenname
            company.get("owner") or company.get("name", ""),
            company.get("iban", ""), company.get("bic", ""),
            calc.total_net if no_vat else calc.total_gross,
            f"Rechnung {qr_ref}", dark=_rgb_to_hex(primary))
    block_y = pdf.get_y()
    text_w = 170
    if qr_png:
        qr_size = 30
        qr_x = 190 - qr_size
        try:
            pdf.image(io.BytesIO(qr_png), x=qr_x, y=block_y, w=qr_size, h=qr_size)
            pdf.set_xy(qr_x - 6, block_y + qr_size + 0.5)
            pdf.set_font(bf, "", 6.8)
            pdf.set_text_color(110, 110, 110)
            pdf.multi_cell(qr_size + 12, 3, pdf.t("Per QR-Code (GiroCode)\nin der Banking-App bezahlen"), align="C")
            pdf.set_text_color(0, 0, 0)
            text_w = qr_x - 20 - 4   # Textspalte links neben dem QR
        except Exception:
            qr_png = None

    # ---- Pflichthinweise (Zahlungsfrist steht im Schlusstext) -----------
    pdf.set_xy(20, block_y)
    if notes:
        pdf.set_font(bf, "", 8.5)
        pdf.set_text_color(70, 70, 70)
        for n in notes:
            pdf.set_x(20)
            pdf.multi_cell(text_w, 4.4, pdf.t("• " + n), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    # nicht über den QR-Block hinaus zusammenlaufen lassen
    if qr_png:
        pdf.set_y(max(pdf.get_y(), block_y + 30 + 7))
    pdf.ln(1)
    if inv.get("footer_text"):
        pdf.set_font(bf, "", 9.5)
        pdf.set_x(20)
        pdf.multi_cell(170, 5, pdf.t(inv["footer_text"]), new_x="LMARGIN", new_y="NEXT")

    out = pdf.output()
    return bytes(out)


def _rgb_to_hex(rgb) -> str:
    return "#%02X%02X%02X" % (rgb[0], rgb[1], rgb[2])
