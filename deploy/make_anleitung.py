"""Erzeugt eine einfache, übersichtliche Benutzer-Kurzanleitung als PDF.

Aufruf (im Projektordner):  .venv/bin/python deploy/make_anleitung.py
Ergebnis:  Kurzanleitung-Rechnungstool.pdf
Nutzt fpdf2 + die mitgelieferten DejaVu-Schriften und das BEKA-Logo.
"""
from pathlib import Path
from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "app" / "static" / "fonts"
LOGO = ROOT / "app" / "static" / "img" / "beka-logo.png"
OUT = ROOT / "Kurzanleitung-Rechnungstool.pdf"

NAVY = (31, 58, 92)
ORANGE = (230, 126, 34)
BOXBG = (238, 243, 249)
GRAY = (70, 70, 70)
ML = 18          # linker Rand
CW = 174         # Inhaltsbreite (210 - 2*18)


class Guide(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_draw_color(220, 224, 230)
        self.line(ML, self.get_y(), ML + CW, self.get_y())
        self.set_y(-11)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(CW / 2, 5, "Rechnungstool · Montageservice Beka")
        self.cell(CW / 2, 5, f"Seite {self.page_no()}", align="R")


def new_pdf():
    pdf = Guide(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(ML, 16, ML)
    pdf.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    return pdf


def page_header(pdf, title, subtitle):
    if LOGO.exists():
        pdf.image(str(LOGO), x=ML, y=14, h=15)
    pdf.set_xy(ML + 42, 14)
    pdf.set_font("DejaVu", "B", 22)
    pdf.set_text_color(*NAVY)
    pdf.cell(CW - 42, 10, title)
    pdf.set_xy(ML + 42, 24)
    pdf.set_font("DejaVu", "", 11)
    pdf.set_text_color(*GRAY)
    pdf.cell(CW - 42, 6, subtitle)
    pdf.set_y(34)
    pdf.set_draw_color(*ORANGE)
    pdf.set_line_width(0.8)
    pdf.line(ML, pdf.get_y(), ML + CW, pdf.get_y())
    pdf.ln(6)


def h2(pdf, text):
    pdf.ln(2)
    y = pdf.get_y()
    pdf.set_fill_color(*ORANGE)
    pdf.rect(ML, y + 0.5, 2.5, 6, style="F")          # orangener Balken links
    pdf.set_xy(ML + 5, y)
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.cell(CW - 5, 7, text)
    pdf.ln(10)


def step(pdf, num, title, body):
    y = pdf.get_y()
    cx, cy, r = ML + 4, y + 3.2, 4.2
    pdf.set_fill_color(*ORANGE)
    pdf.ellipse(cx - r, cy - r, 2 * r, 2 * r, style="F")
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(cx - r, cy - r - 0.3)
    pdf.cell(2 * r, 2 * r, str(num), align="C")
    x = ML + 14
    pdf.set_xy(x, y)
    pdf.set_font("DejaVu", "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.multi_cell(CW - 14, 6, title)
    pdf.set_x(x)
    pdf.set_font("DejaVu", "", 10.5)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(CW - 14, 5.3, body)
    pdf.ln(3.5)


def box(pdf, title, lines, accent=NAVY):
    pdf.ln(1)
    pad = 5
    line_h = 5.6
    inner = CW - 2 * pad
    # Höhe vorab berechnen
    pdf.set_font("DejaVu", "", 10.5)
    total = 9
    for ln in lines:
        total += pdf.get_string_width("•  " + ln)  # nur zum Zeilen schätzen
    # einfacher: pro Eintrag Zeilen via multi_cell-Probe
    h = 8 + 4
    for ln in lines:
        n = max(1, _wrapped_lines(pdf, ln, inner - 6))
        h += n * line_h + 1.5
    y0 = pdf.get_y()
    pdf.set_fill_color(*BOXBG)
    pdf.set_draw_color(*accent)
    pdf.set_line_width(0.3)
    pdf.rect(ML, y0, CW, h, style="DF")
    pdf.set_fill_color(*accent)
    pdf.rect(ML, y0, 2.5, h, style="F")
    pdf.set_xy(ML + pad + 2, y0 + 4)
    pdf.set_font("DejaVu", "B", 11.5)
    pdf.set_text_color(*accent)
    pdf.cell(inner, 6, title)
    pdf.set_y(y0 + 12)
    pdf.set_font("DejaVu", "", 10.5)
    pdf.set_text_color(50, 50, 50)
    for ln in lines:
        pdf.set_x(ML + pad + 2)
        pdf.set_text_color(*ORANGE)
        pdf.cell(5, line_h, "•")
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(inner - 6, line_h, ln)
        pdf.ln(1.5)
    pdf.set_y(y0 + h + 4)


def feature(pdf, title, body):
    pdf.set_font("DejaVu", "B", 11.5)
    pdf.set_text_color(*NAVY)
    pdf.set_x(ML)
    pdf.multi_cell(CW, 6, title)
    pdf.set_x(ML)
    pdf.set_font("DejaVu", "", 10.5)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(CW, 5.3, body)
    pdf.ln(3.5)


def _wrapped_lines(pdf, text, width):
    """grobe Zeilen-Schätzung für die Box-Höhe."""
    words = text.split()
    lines, cur = 1, ""
    for w in words:
        t = (cur + " " + w).strip()
        if pdf.get_string_width(t) > width:
            lines += 1
            cur = w
        else:
            cur = t
    return lines


def build():
    pdf = new_pdf()
    pdf.add_page()
    page_header(pdf, "Kurzanleitung", "Rechnungstool · Montageservice Beka")

    pdf.set_font("DejaVu", "", 11)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(CW, 5.6,
        "Mit diesem Programm schreiben Sie Rechnungen, Angebote und Mahnungen – einfach am "
        "Computer. Diese Anleitung zeigt die wichtigsten Schritte. Sie brauchen keine Vorkenntnisse.")
    pdf.ln(2)

    box(pdf, "Das Wichtigste in Kürze", [
        "Starten: Doppelklick auf das Symbol „Rechnungstool“ auf dem Desktop.",
        "Alles passiert in einem Fenster. Links wechseln Sie zwischen Übersicht, Kunden, "
        "Rechnungen, Katalog und Einstellungen.",
        "Ihre Daten werden jeden Tag automatisch gesichert – Sie müssen nichts tun.",
        "Zum Beenden einfach das Fenster schließen.",
    ])

    h2(pdf, "In 6 Schritten zur Rechnung")
    step(pdf, 1, "Kunde anlegen",
         "Links auf „Kunden“ klicken, dann „+ Neuer Kunde“. Name und Adresse eintragen "
         "und „Speichern“. Kunden, die es schon gibt, müssen Sie nicht neu anlegen.")
    step(pdf, 2, "Neue Rechnung starten",
         "Links auf „Rechnungen“ klicken, dann oben rechts „+ Neue Rechnung“.")
    step(pdf, 3, "Kunde auswählen",
         "Im Feld „Kunde“ den Namen eintippen und aus der Liste wählen. Bei „Betreff“ "
         "können Sie das Bauvorhaben angeben.")
    step(pdf, 4, "Leistungen eintragen",
         "Mit „+ Position“ eine Zeile hinzufügen oder eine Leistung „aus Katalog übernehmen“. "
         "Menge und Preis eingeben – die Summe rechnet sich von selbst aus.")
    step(pdf, 5, "Als PDF erstellen",
         "Oben auf „Als PDF erstellen“ klicken. Die Rechnung bekommt eine Nummer und ist fertig. "
         "Wichtig: Danach kann sie nicht mehr geändert werden.")
    step(pdf, 6, "Verschicken",
         "Auf „Per E-Mail senden“ klicken (die Adresse ist schon ausgefüllt) oder die PDF "
         "herunterladen und ausdrucken. Die Rechnung wird automatisch als „versendet“ markiert.")

    # ---- Seite 2 ----
    pdf.add_page()
    page_header(pdf, "Weitere Funktionen", "Rechnungstool · Montageservice Beka")

    feature(pdf, "Zahlung eintragen",
            "Hat der Kunde bezahlt? Rechnung öffnen und unten bei „Zahlungen“ den Betrag "
            "eintragen. So sehen Sie immer, was noch offen ist.")
    feature(pdf, "Mahnung schreiben",
            "Ist eine Rechnung nach 14 Tagen nicht bezahlt, erscheint sie als „mahnfällig“. "
            "Rechnung öffnen und „Mahnung erstellen“ – Text und neue Zahlungsfrist sind schon fertig. "
            "Beim nächsten Mal wird automatisch die nächste Stufe (1./2. Mahnung) genommen.")
    feature(pdf, "Angebot schreiben",
            "Oben auf „+ Angebot“. Sagt der Kunde zu, öffnen Sie das Angebot und klicken "
            "„In Rechnung umwandeln“ – alle Positionen werden übernommen.")
    feature(pdf, "Etwas suchen",
            "In jeder Liste gibt es oben ein Suchfeld – z. B. nach Kundenname, Ort oder "
            "Rechnungsnummer suchen.")

    box(pdf, "Gut zu wissen", [
        "„Als PDF erstellen“ ist endgültig (gesetzliche Vorschrift). Ein Fehler wird über "
        "„Stornieren“ korrigiert – danach schreiben Sie eine neue, richtige Rechnung.",
        "Datensicherung läuft automatisch jeden Tag. Unter „Einstellungen“ können Sie jederzeit "
        "„Sicherung jetzt erstellen“ und mit „Selbsttest“ prüfen, ob alles in Ordnung ist.",
        "Bewahren Sie eine Sicherung zusätzlich auf einem zweiten Medium auf (USB-Stick oder "
        "externe Festplatte) – für den Fall der Fälle.",
    ], accent=ORANGE)

    pdf.ln(1)
    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(CW, 5,
        "Bei Fragen oder Problemen wenden Sie sich an malitech solutions.")

    pdf.output(str(OUT))
    print("Erstellt:", OUT)


if __name__ == "__main__":
    build()
