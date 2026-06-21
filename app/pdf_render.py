"""PDF-Seiten als PNG rendern (für die Bildschirm-Vorschau).

Die Vorschau wird als Bild ausgeliefert statt als eingebettetes PDF – das
funktioniert zuverlässig in jedem Browser (auch Safari) und in der eingebetteten
Vorschau. Bei mehrseitigen Rechnungen werden alle Seiten untereinander zu einem
Bild zusammengesetzt, damit man im scrollbaren Vorschaufenster alle Seiten sieht.
Nutzt pypdfium2 (PDFium, BSD-Lizenz).
"""
from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image


def pdf_to_png(pdf_bytes: bytes, scale: float = 1.9) -> bytes:
    """Rendert alle Seiten des PDFs und stapelt sie vertikal zu einem PNG."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        images = []
        for i in range(len(pdf)):
            bitmap = pdf[i].render(scale=scale)
            images.append(bitmap.to_pil().convert("RGB"))

        if not images:
            blank = Image.new("RGB", (827, 1169), "white")
            buf = io.BytesIO()
            blank.save(buf, format="PNG")
            return buf.getvalue()

        if len(images) == 1:
            out = images[0]
        else:
            gap = 18  # grauer Abstand zwischen den Seiten
            width = max(im.width for im in images)
            height = sum(im.height for im in images) + gap * (len(images) - 1)
            out = Image.new("RGB", (width, height), (235, 235, 235))
            y = 0
            for im in images:
                out.paste(im, ((width - im.width) // 2, y))
                y += im.height + gap

        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=False)
        return buf.getvalue()
    finally:
        pdf.close()
