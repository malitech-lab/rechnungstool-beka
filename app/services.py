"""Anwendungslogik: Stammdaten, Kunden, Katalog, Rechnungen, Festschreibung.

Bündelt Datenbankzugriff, Berechnung, Validierung, Belegerzeugung (PDF/E-Rechnung)
und die GoBD-Festschreibung (Nummernvergabe, Snapshot, Unveränderbarkeit,
revisionssichere Archivierung, Audit-Log).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sqlite3
from pathlib import Path

from . import db, config, numbering, audit

# Mitgeliefertes Standard-Logo (wird genutzt, solange kein eigenes hochgeladen wird)
DEFAULT_LOGO = Path(__file__).parent / "static" / "img" / "beka-logo.png"
from .invoice_calc import compute, is_small_amount, CalcResult
from .validation import validate, errors as v_errors
from .legal import (legal_notes, payment_term_text, format_de,
                    service_period, service_period_full)
from .money import money


# ====================== Firmenstammdaten ======================

def get_company(conn) -> dict:
    row = db.query_one(conn, "SELECT * FROM company WHERE id = 1")
    return dict(row) if row else {}


def update_company(conn, data: dict) -> None:
    allowed = [
        "name", "owner", "legal_form", "street", "zip", "city", "country",
        "phone", "email", "website", "tax_number", "vat_id", "bank_name",
        "iban", "bic", "logo_file", "kleinunternehmer", "default_tax_rate",
        "payment_terms_days", "invoice_prefix", "customer_prefix",
        "intro_text", "footer_text", "color_primary", "color_accent",
        "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_security",
    ]
    fields = [k for k in allowed if k in data]
    sets = ", ".join(f"{k} = ?" for k in fields) + ", updated_at = datetime('now')"
    conn.execute(f"UPDATE company SET {sets} WHERE id = 1", [data[k] for k in fields])
    audit.log(conn, "Firmenstammdaten geändert", "company", 1)
    conn.commit()


# ====================== Kunden ======================

def list_customers(conn, include_inactive=True) -> list[dict]:
    sql = "SELECT * FROM customers"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY company_name, contact_name"
    return [dict(r) for r in db.query(conn, sql)]


def get_customer(conn, cid) -> dict | None:
    row = db.query_one(conn, "SELECT * FROM customers WHERE id = ?", (cid,))
    return dict(row) if row else None


def save_customer(conn, data: dict, cid=None) -> int:
    fields = ["kind", "company_name", "contact_name", "first_name", "last_name",
              "salutation", "street", "zip", "city", "country", "email", "phone",
              "vat_id", "leitweg_id", "e_address", "is_bauleistend", "freistellung_48",
              "freistellung_bis", "notes", "active"]
    vals = [data.get(f, "") for f in fields]
    if cid:
        sets = ", ".join(f"{f} = ?" for f in fields)
        conn.execute(f"UPDATE customers SET {sets} WHERE id = ?", vals + [cid])
        audit.log(conn, "Kunde geändert", "customer", cid)
    else:
        company = get_company(conn)
        number = numbering.next_customer_number(conn, company.get("customer_prefix", "K"))
        cols = ", ".join(fields) + ", customer_number"
        ph = ", ".join("?" for _ in fields) + ", ?"
        cur = conn.execute(f"INSERT INTO customers ({cols}) VALUES ({ph})", vals + [number])
        cid = cur.lastrowid
        audit.log(conn, "Kunde angelegt", "customer", cid, number)
    conn.commit()
    return cid


# ====================== Katalog ======================

def list_catalog(conn, include_inactive=True) -> list[dict]:
    sql = "SELECT * FROM catalog_items"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY kind, name"
    return [dict(r) for r in db.query(conn, sql)]


def get_catalog_item(conn, iid) -> dict | None:
    row = db.query_one(conn, "SELECT * FROM catalog_items WHERE id = ?", (iid,))
    return dict(row) if row else None


def save_catalog_item(conn, data: dict, iid=None) -> int:
    fields = ["kind", "article_number", "name", "description", "unit",
              "unit_price", "tax_rate", "active"]
    vals = [data.get(f, "") for f in fields]
    if iid:
        sets = ", ".join(f"{f} = ?" for f in fields)
        conn.execute(f"UPDATE catalog_items SET {sets} WHERE id = ?", vals + [iid])
    else:
        cols = ", ".join(fields)
        ph = ", ".join("?" for _ in fields)
        cur = conn.execute(f"INSERT INTO catalog_items ({cols}) VALUES ({ph})", vals)
        iid = cur.lastrowid
    conn.commit()
    return iid


# ====================== Rechnungen ======================

def list_invoices(conn, status=None) -> list[dict]:
    sql = ("SELECT i.*, c.company_name AS c_company, c.contact_name AS c_contact "
           "FROM invoices i LEFT JOIN customers c ON c.id = i.customer_id")
    params = []
    if status:
        sql += " WHERE i.status = ?"
        params.append(status)
    sql += " ORDER BY COALESCE(i.finalized_at, i.created_at) DESC, i.id DESC"
    rows = [dict(r) for r in db.query(conn, sql, params)]
    for r in rows:
        r["buyer_name"] = r.get("c_company") or r.get("c_contact") or "—"
        r["paid"] = paid_amount(conn, r["id"])
        r["open"] = float(money(r["total_gross"])) - r["paid"]
        r["mahn_faellig"] = mahn_faellig(r)
    return rows


def get_invoice(conn, iid) -> dict | None:
    row = db.query_one(conn, "SELECT * FROM invoices WHERE id = ?", (iid,))
    if not row:
        return None
    inv = dict(row)
    inv["items"] = [dict(r) for r in db.query(
        conn, "SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY position, id", (iid,))]
    return inv


def create_draft(conn, customer_id=None, doc_type="standard") -> int:
    company = get_company(conn)
    today = _dt.date.today().isoformat()
    tax_mode = "kleinunternehmer" if company.get("kleinunternehmer") else "regel"
    cur = conn.execute(
        "INSERT INTO invoices (customer_id, doc_type, invoice_date, service_date,"
        " service_date_end, due_date, payment_terms_days, tax_mode, intro_text, footer_text)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (customer_id, doc_type, today, today, "", today,
         company.get("payment_terms_days") or 14, tax_mode,
         company.get("intro_text", ""), company.get("footer_text", "")),
    )
    iid = cur.lastrowid
    label = "Angebotsentwurf angelegt" if doc_type == "angebot" else "Rechnungsentwurf angelegt"
    audit.log(conn, label, "invoice", iid)
    conn.commit()
    return iid


def _ensure_draft(inv: dict):
    if inv["status"] != "entwurf":
        raise PermissionError(
            "Diese Rechnung wurde bereits als PDF erstellt und ist unveränderbar "
            "(GoBD). Korrekturen sind nur über eine Stornorechnung möglich.")


def update_draft(conn, iid: int, head: dict, items: list[dict]) -> None:
    inv = get_invoice(conn, iid)
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    _ensure_draft(inv)
    hfields = ["customer_id", "title", "project_ref", "invoice_date", "service_date",
               "service_date_end", "due_date", "payment_terms_days", "tax_mode",
               "intro_text", "footer_text", "notes", "skonto_percent", "skonto_days",
               "doc_type"]
    sets = ", ".join(f"{f} = ?" for f in hfields)
    conn.execute(f"UPDATE invoices SET {sets} WHERE id = ?",
                 [head.get(f, inv.get(f)) for f in hfields] + [iid])
    conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (iid,))
    # leere/unausgefüllte Zeilen verwerfen (Name leer und Preis 0, kein Text)
    items = [it for it in items if it.get("item_type") == "text"
             or str(it.get("name", "")).strip() or float(it.get("unit_price") or 0) != 0]
    default_rate = get_company(conn).get("default_tax_rate") or 19.0
    for pos, it in enumerate(items, start=1):
        # fehlenden Steuersatz auf den Standard (19 %) setzen; ein explizit
        # gewähltes 0 % (z. B. Reverse-Charge) bleibt erhalten
        rate = it.get("tax_rate")
        rate = default_rate if rate in (None, "") else rate
        conn.execute(
            "INSERT INTO invoice_items (invoice_id, position, item_type, article_number,"
            " name, description, quantity, unit, unit_price, discount_percent, tax_rate)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iid, pos, it.get("item_type", "leistung"), it.get("article_number", ""),
             it.get("name", ""), it.get("description", ""), it.get("quantity", 0) or 0,
             it.get("unit", ""), it.get("unit_price", 0) or 0,
             it.get("discount_percent", 0) or 0, rate),
        )
    # Kleinbetrag automatisch erkennen (sofern nicht Storno/Korrektur)
    calc = compute(items, head.get("tax_mode", inv.get("tax_mode")))
    if head.get("doc_type") not in ("storno", "korrektur", "angebot"):
        dt = "kleinbetrag" if is_small_amount(calc.total_gross) else "standard"
        conn.execute("UPDATE invoices SET doc_type = ? WHERE id = ?", (dt, iid))
    conn.commit()


def delete_draft(conn, iid: int) -> None:
    inv = get_invoice(conn, iid)
    if not inv:
        return
    _ensure_draft(inv)
    conn.execute("DELETE FROM invoices WHERE id = ?", (iid,))
    audit.log(conn, "Rechnungsentwurf gelöscht", "invoice", iid)
    conn.commit()


# ---- Berechnung / Validierung / Kontext ----

def compute_invoice(conn, inv: dict) -> CalcResult:
    return compute(inv["items"], inv.get("tax_mode", "regel"))


def buyer_from_customer(cust: dict | None) -> dict:
    if not cust:
        return {"name_lines": ["—"], "name_full": "—", "street": "", "zip": "",
                "city": "", "country": "DE", "customer_number": "", "vat_id": "",
                "leitweg_id": "", "salutation_line": "Sehr geehrte Damen und Herren,",
                "_raw": None}
    name_lines = []
    if cust.get("company_name"):
        name_lines.append(cust["company_name"])
    sal = cust.get("salutation", "")
    contact = cust.get("contact_name", "")
    if contact:
        prefix = f"{sal} " if sal in ("Herr", "Frau") else ""
        name_lines.append((prefix + contact).strip())
    if not name_lines:
        name_lines = ["—"]
    if sal == "Herr" and contact:
        sl = f"Sehr geehrter Herr {contact.split()[-1]},"
    elif sal == "Frau" and contact:
        sl = f"Sehr geehrte Frau {contact.split()[-1]},"
    else:
        sl = "Sehr geehrte Damen und Herren,"
    return {
        "name_lines": name_lines,
        "name_full": cust.get("company_name") or cust.get("contact_name") or "—",
        "street": cust.get("street", ""), "zip": cust.get("zip", ""),
        "city": cust.get("city", ""), "country": cust.get("country", "DE"),
        "customer_number": cust.get("customer_number", ""),
        "vat_id": cust.get("vat_id", ""), "leitweg_id": cust.get("leitweg_id", ""),
        "last_name": cust.get("last_name") or (contact.split()[-1] if contact else ""),
        "salutation_line": sl, "_raw": cust,
    }


def _slug(s) -> str:
    """Dateinamen-tauglich machen (Sonderzeichen entfernen, Leerzeichen -> '-')."""
    s = str(s or "").strip()
    for ch in '/\\:*?"<>|\n\r\t':
        s = s.replace(ch, "")
    return "-".join(s.split())


def invoice_filename(inv: dict, ext: str = ".pdf") -> str:
    """Rechnungsnummer_Nachname_Datum.pdf"""
    buyer = {}
    if inv.get("buyer_json"):
        try:
            buyer = json.loads(inv["buyer_json"])
        except Exception:
            buyer = {}
    last = buyer.get("last_name") or ""
    if not last:
        full = (buyer.get("name_full") or "").split()
        last = full[-1] if full else ""
    parts = [inv.get("invoice_number") or "Rechnung", last, inv.get("invoice_date") or ""]
    return "_".join(_slug(p) for p in parts if _slug(p)) + ext


def _assemble_context(company: dict, buyer: dict, inv_like: dict, items: list[dict]) -> dict:
    """Baut den Render-Kontext aus Firma, Käufer, Rechnungsdaten und Positionen."""
    calc = compute(items, inv_like.get("tax_mode", "regel"))
    s_from = inv_like.get("service_date", "")
    s_to = inv_like.get("service_date_end", "")
    s_label, s_value = service_period(s_from, s_to)
    if inv_like.get("doc_type") == "angebot":
        intro = "Gerne unterbreiten wir Ihnen folgendes Angebot:"
        footer = ("Dieses Angebot ist 30 Tage gültig.\n\n"
                  "Wir freuen uns auf Ihren Auftrag und stehen für Rückfragen "
                  "gerne zur Verfügung.")
    elif inv_like.get("doc_type") == "mahnung":
        intro, footer = _dunning_texts(
            inv_like.get("mahn_level", 1), inv_like.get("reference_number", ""),
            inv_like.get("reference_date", ""), inv_like.get("due_date", ""))
    else:
        intro = company.get("intro_text") or inv_like.get("intro_text", "")
        footer = company.get("footer_text") or inv_like.get("footer_text", "")
    inv_ctx = {
        "number": inv_like.get("number") or "(Entwurf)",
        "doc_type": inv_like.get("doc_type", "standard"),
        "title": inv_like.get("title", ""),
        "invoice_date": inv_like.get("invoice_date", ""),
        "service_date": s_from,
        "service_date_end": s_to,
        "service_label": s_label,
        "service_value": s_value,
        "service_full": service_period_full(s_from, s_to),
        "due_date": inv_like.get("due_date", ""),
        "payment_terms_days": inv_like.get("payment_terms_days", 14),
        "tax_mode": inv_like.get("tax_mode", "regel"),
        # Einleitung/Schlusstext: bei Angeboten feste Texte, sonst aus den
        # Firmen-Einstellungen (Entwurf: aktuell, festgeschrieben: Snapshot).
        "intro_text": intro,
        "footer_text": footer,
        "skonto_percent": inv_like.get("skonto_percent", 0),
        "skonto_days": inv_like.get("skonto_days", 0),
        "reference_number": inv_like.get("reference_number", ""),
        "mahn_level": inv_like.get("mahn_level", 0),
    }
    logo = None
    if company.get("logo_file"):
        p = config.ASSETS_DIR / company["logo_file"]
        if p.exists():
            logo = str(p)
    if not logo and DEFAULT_LOGO.exists():
        logo = str(DEFAULT_LOGO)   # mitgeliefertes BEKA-Logo
    return {
        "company": company, "buyer": buyer, "invoice": inv_ctx, "calc": calc,
        "notes": legal_notes(company, buyer.get("_raw"), inv_ctx),
        "payment_text": payment_term_text(inv_ctx, company),
        "logo_path": logo, "is_small": is_small_amount(calc.total_gross),
    }


def build_context(conn, inv: dict) -> dict:
    """Render-Kontext für PDF/E-Rechnung. Nutzt bei festgeschriebenen Rechnungen
    den eingefrorenen Snapshot, sonst die Live-Stammdaten."""
    if inv["status"] != "entwurf" and inv.get("seller_json"):
        company = json.loads(inv["seller_json"])
        buyer = json.loads(inv["buyer_json"])
        buyer.setdefault("_raw", {"kind": buyer.get("kind", "B2C")})
    else:
        company = get_company(conn)
        cust = get_customer(conn, inv["customer_id"]) if inv.get("customer_id") else None
        buyer = buyer_from_customer(cust)
    inv_like = dict(inv)
    inv_like["number"] = inv.get("invoice_number") or "(Entwurf)"
    # Mahnung: Original-Rechnung (Nummer + Datum) für Bezug/Text/QR auflösen
    if inv.get("doc_type") == "mahnung" and inv.get("references_invoice_id"):
        orig = db.query_one(conn, "SELECT invoice_number, invoice_date FROM invoices WHERE id = ?",
                            (inv["references_invoice_id"],))
        if orig:
            inv_like["reference_number"] = orig["invoice_number"] or ""
            inv_like["reference_date"] = orig["invoice_date"] or ""
    return _assemble_context(company, buyer, inv_like, inv["items"])


def preview_context(conn, head: dict, items: list[dict]) -> dict:
    """Render-Kontext aus noch nicht gespeicherten Formulardaten (Live-Vorschau)."""
    company = get_company(conn)
    cust = get_customer(conn, head.get("customer_id")) if head.get("customer_id") else None
    buyer = buyer_from_customer(cust)
    inv_like = dict(head)
    inv_like["number"] = "Entwurf – Vorschau"
    return _assemble_context(company, buyer, inv_like, items)


def validate_invoice(conn, inv: dict):
    company = get_company(conn)
    cust = get_customer(conn, inv["customer_id"]) if inv.get("customer_id") else None
    calc = compute(inv["items"], inv.get("tax_mode", "regel"))
    inv_for_val = {
        "invoice_date": inv.get("invoice_date"), "service_date": inv.get("service_date"),
        "service_date_end": inv.get("service_date_end"),
        "tax_mode": inv.get("tax_mode", "regel"), "doc_type": inv.get("doc_type"),
    }
    return validate(company, cust, inv_for_val, inv["items"], calc.total_gross)


# ---- Festschreibung (GoBD) ----

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive(name: str, data: bytes) -> str:
    config.ensure_dirs()
    path = config.ARCHIVE_DIR / name
    path.write_bytes(data)
    return name


def finalize_invoice(conn, iid: int) -> dict:
    """Rechnung rechtssicher festschreiben: Nummer vergeben, Snapshot einfrieren,
    PDF + E-Rechnung erzeugen, archivieren, unveränderbar setzen."""
    from . import pdf_invoice, einvoice  # späte Importe (PDF/E-Rechnung)

    inv = get_invoice(conn, iid)
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    _ensure_draft(inv)

    findings = validate_invoice(conn, inv)
    errs = v_errors(findings)
    if errs:
        raise ValueError("Rechnung kann nicht als PDF erstellt werden:\n" +
                         "\n".join(f"• {e.message}" for e in errs))

    company = get_company(conn)
    ctx = build_context(conn, inv)
    is_offer = inv.get("doc_type") == "angebot"
    is_dunning = inv.get("doc_type") == "mahnung"
    no_einvoice = is_offer or is_dunning

    # Nummer in derselben Transaktion vergeben (lückenlos)
    if is_offer:
        number = numbering.next_offer_number(
            conn, company.get("offer_prefix", "AG"), _date(inv.get("invoice_date")))
    elif is_dunning:
        number = numbering.next_dunning_number(
            conn, company.get("dunning_prefix", "MA"), _date(inv.get("invoice_date")))
    else:
        number = numbering.next_invoice_number(
            conn, company.get("invoice_prefix", "RE"), _date(inv.get("invoice_date")))
    ctx["invoice"]["number"] = number

    calc = ctx["calc"]
    # Snapshots einfrieren
    seller_json = json.dumps(ctx["company"], ensure_ascii=False)
    buyer_snap = dict(ctx["buyer"])
    buyer_snap["kind"] = (ctx["buyer"].get("_raw") or {}).get("kind", "B2C")
    buyer_snap.pop("_raw", None)
    buyer_json = json.dumps(buyer_snap, ensure_ascii=False)

    # Belege erzeugen (Angebote/Mahnungen bekommen nur eine PDF, keine E-Rechnung)
    pdf_bytes = pdf_invoice.render(ctx)
    xml_bytes = zugferd_bytes = None
    if not no_einvoice:
        try:
            xml_bytes = einvoice.cii_xml(ctx)
            zugferd_bytes = einvoice.zugferd_pdf(pdf_bytes, xml_bytes)
        except Exception as exc:  # E-Rechnung darf Festschreibung nicht verhindern
            xml_bytes, zugferd_bytes = None, None
            audit.log(conn, "E-Rechnung konnte nicht erzeugt werden", "invoice", iid, str(exc))

    base = number.replace("/", "-")
    pdf_name = _archive(f"{base}.pdf", pdf_bytes)
    xml_name = _archive(f"{base}-erechnung.xml", xml_bytes) if xml_bytes else ""
    zug_name = _archive(f"{base}-zugferd.pdf", zugferd_bytes) if zugferd_bytes else ""

    conn.execute(
        "UPDATE invoices SET invoice_number = ?, status = 'festgeschrieben',"
        " total_net = ?, total_tax = ?, total_gross = ?, seller_json = ?, buyer_json = ?,"
        " pdf_file = ?, xml_file = ?, zugferd_file = ?, pdf_sha256 = ?,"
        " finalized_at = datetime('now') WHERE id = ?",
        (number, float(calc.total_net), float(calc.total_tax), float(calc.total_gross),
         seller_json, buyer_json, pdf_name, xml_name, zug_name, _sha256(pdf_bytes), iid),
    )
    audit.log(conn, "Angebot erstellt" if is_offer else
              ("Mahnung erstellt" if is_dunning else "Rechnung festgeschrieben"),
              "invoice", iid, number)
    conn.commit()
    return get_invoice(conn, iid)


def _date(iso: str | None) -> _dt.date:
    try:
        y, m, d = str(iso).split("-")
        return _dt.date(int(y), int(m), int(d))
    except Exception:
        return _dt.date.today()


def create_storno(conn, iid: int) -> int:
    """Stornorechnung als neuen Entwurf anlegen (negative Beträge, Bezug zum Original)."""
    orig = get_invoice(conn, iid)
    if not orig or orig["status"] != "festgeschrieben":
        raise ValueError("Nur festgeschriebene Rechnungen können storniert werden.")
    if db.query_one(conn, "SELECT id FROM invoices WHERE references_invoice_id = ? AND doc_type='storno'", (iid,)):
        raise ValueError("Zu dieser Rechnung existiert bereits eine Stornorechnung.")
    today = _dt.date.today().isoformat()
    cur = conn.execute(
        "INSERT INTO invoices (customer_id, doc_type, invoice_date, service_date,"
        " service_date_end, due_date, tax_mode, title, references_invoice_id,"
        " intro_text, footer_text)"
        " VALUES (?, 'storno', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (orig["customer_id"], today, orig.get("service_date", ""),
         orig.get("service_date_end", ""), today,
         orig.get("tax_mode", "regel"),
         f"Storno zu Rechnung {orig.get('invoice_number','')}", iid,
         f"hiermit stornieren wir die Rechnung {orig.get('invoice_number','')} vollständig:",
         orig.get("footer_text", "")),
    )
    sid = cur.lastrowid
    for it in orig["items"]:
        conn.execute(
            "INSERT INTO invoice_items (invoice_id, position, item_type, article_number,"
            " name, description, quantity, unit, unit_price, discount_percent, tax_rate)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, it["position"], it["item_type"], it["article_number"], it["name"],
             it["description"], -float(it["quantity"]), it["unit"], it["unit_price"],
             it["discount_percent"], it["tax_rate"]),
        )
    audit.log(conn, "Stornorechnung angelegt", "invoice", sid,
              f"Bezug {orig.get('invoice_number','')}")
    conn.commit()
    return sid


def create_invoice_from_offer(conn, iid: int) -> int:
    """Aus einem festgeschriebenen Angebot einen neuen Rechnungs-Entwurf erzeugen.

    Übernimmt Kunde, Betreff, Steuermodus und alle Positionen. Die Rechnung
    bleibt zunächst Entwurf und erhält ihre RE-Nummer erst beim Festschreiben.
    """
    offer = get_invoice(conn, iid)
    if not offer or offer.get("doc_type") != "angebot":
        raise ValueError("Nur Angebote können in eine Rechnung umgewandelt werden.")
    if offer["status"] != "festgeschrieben":
        raise ValueError("Das Angebot muss zuerst als PDF erstellt werden.")
    company = get_company(conn)
    today = _dt.date.today().isoformat()
    cur = conn.execute(
        "INSERT INTO invoices (customer_id, doc_type, invoice_date, service_date,"
        " service_date_end, due_date, payment_terms_days, tax_mode, title,"
        " references_invoice_id, intro_text, footer_text)"
        " VALUES (?, 'standard', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (offer["customer_id"], today, today, "", today,
         company.get("payment_terms_days") or 14, offer.get("tax_mode", "regel"),
         offer.get("title", ""), iid,
         company.get("intro_text", ""), company.get("footer_text", "")),
    )
    rid = cur.lastrowid
    for it in offer["items"]:
        conn.execute(
            "INSERT INTO invoice_items (invoice_id, position, item_type, article_number,"
            " name, description, quantity, unit, unit_price, discount_percent, tax_rate)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rid, it["position"], it["item_type"], it["article_number"], it["name"],
             it["description"], it["quantity"], it["unit"], it["unit_price"],
             it["discount_percent"], it["tax_rate"]),
        )
    audit.log(conn, "Rechnung aus Angebot erstellt", "invoice", rid,
              f"aus {offer.get('invoice_number','')}")
    conn.commit()
    return rid


# ====================== Mahnwesen ======================

MAHN_FAELLIG_TAGE = 14      # offene Rechnung gilt nach 14 Tagen als mahnfällig
MAHN_FRIST_TAGE = 7         # neue Zahlungsfrist je Mahnung


def _days_since(iso: str | None) -> int:
    try:
        return (_dt.date.today() - _date(iso)).days
    except Exception:
        return 0


def mahn_faellig(inv: dict) -> bool:
    """True, wenn eine festgeschriebene Rechnung seit >=14 Tagen offen ist."""
    return (inv.get("status") == "festgeschrieben"
            and inv.get("doc_type") in ("standard", "kleinbetrag", "korrektur")
            and float(inv.get("open") or 0) > 0.005
            and _days_since(inv.get("invoice_date")) >= MAHN_FAELLIG_TAGE)


def _dunning_title(level) -> str:
    level = int(level or 1)
    return "Zahlungserinnerung" if level <= 1 else f"{level - 1}. Mahnung"


def _dunning_texts(level, ref_no: str, ref_date_iso: str, due_iso: str) -> tuple[str, str]:
    """(Einleitung, Schlusstext) je Mahnstufe."""
    level = int(level or 1)
    ref = f"Rechnung {ref_no} vom {format_de(ref_date_iso)}"
    bis = format_de(due_iso)
    if level <= 1:
        intro = (f"sicher ist es Ihrer Aufmerksamkeit entgangen: unsere {ref} ist bisher "
                 f"ohne Ausgleich geblieben.\n\nWir bitten Sie, den unten ausgewiesenen "
                 f"offenen Betrag bis zum {bis} auf das angegebene Konto zu überweisen. "
                 f"Sollten Sie die Zahlung zwischenzeitlich veranlasst haben, betrachten "
                 f"Sie dieses Schreiben bitte als gegenstandslos.")
        footer = "Vielen Dank für die Begleichung des offenen Betrags."
    elif level == 2:
        intro = (f"trotz unserer Zahlungserinnerung konnten wir zu unserer {ref} bisher "
                 f"keinen Zahlungseingang feststellen.\n\nWir fordern Sie auf, den offenen "
                 f"Betrag bis zum {bis} zu begleichen.")
        footer = "Bitte überweisen Sie den offenen Betrag fristgerecht."
    else:
        intro = (f"trotz mehrfacher Aufforderung ist unsere {ref} weiterhin offen.\n\nWir "
                 f"setzen Ihnen hiermit eine letzte Frist bis zum {bis}. Sollte auch diese "
                 f"Frist fruchtlos verstreichen, behalten wir uns ohne weitere Ankündigung "
                 f"weitere Schritte (gerichtliches Mahnverfahren / Inkasso) vor.")
        footer = "Wir bitten dringend um fristgerechte Zahlung."
    return intro, footer


def create_dunning(conn, iid: int) -> int:
    """Aus einer offenen, festgeschriebenen Rechnung eine Mahnung (Entwurf) erzeugen.

    Die Mahnstufe zählt automatisch hoch (1=Zahlungserinnerung, 2=1. Mahnung, …),
    übernimmt den offenen Betrag und setzt eine neue Zahlungsfrist (heute + 7 Tage).
    """
    orig = get_invoice(conn, iid)
    if not orig:
        raise ValueError("Rechnung nicht gefunden.")
    if orig["status"] != "festgeschrieben" or orig["doc_type"] not in (
            "standard", "kleinbetrag", "korrektur"):
        raise ValueError("Nur festgeschriebene Rechnungen können gemahnt werden.")
    open_amt = float(money(orig["total_gross"])) - paid_amount(conn, iid)
    if open_amt <= 0.005:
        raise ValueError("Diese Rechnung ist bereits vollständig bezahlt.")
    prev = db.query_one(conn, "SELECT COUNT(*) AS n FROM invoices"
                        " WHERE references_invoice_id = ? AND doc_type = 'mahnung'", (iid,))
    level = int(prev["n"] if prev else 0) + 1
    today = _dt.date.today().isoformat()
    due = (_dt.date.today() + _dt.timedelta(days=MAHN_FRIST_TAGE)).isoformat()
    bezug = f"{orig.get('invoice_number','')} vom {format_de(orig.get('invoice_date',''))}"
    cur = conn.execute(
        "INSERT INTO invoices (customer_id, doc_type, mahn_level, invoice_date,"
        " service_date, service_date_end, due_date, tax_mode, title, references_invoice_id)"
        " VALUES (?, 'mahnung', ?, ?, '', '', ?, 'regel', ?, ?)",
        (orig["customer_id"], level, today, due, f"zu Rechnung {bezug}", iid),
    )
    mid = cur.lastrowid
    conn.execute(
        "INSERT INTO invoice_items (invoice_id, position, item_type, article_number,"
        " name, description, quantity, unit, unit_price, discount_percent, tax_rate)"
        " VALUES (?, 1, 'leistung', '', ?, '', 1, '', ?, 0, 0)",
        (mid, f"Offener Betrag aus Rechnung {bezug}", open_amt),
    )
    audit.log(conn, "Mahnung angelegt", "invoice", mid,
              f"Stufe {level}, Bezug {orig.get('invoice_number','')}")
    conn.commit()
    return mid


# ====================== Versand (E-Mail / Post) ======================

def mark_sent(conn, iid: int, via: str) -> None:
    """Beleg im Versandprotokoll als versendet markieren (via 'E-Mail' oder 'Post')."""
    inv = get_invoice(conn, iid)
    if not inv:
        raise ValueError("Beleg nicht gefunden.")
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE invoices SET sent_at = ?, sent_via = ? WHERE id = ?", (ts, via, iid))
    audit.log(conn, f"Versendet ({via})", "invoice", iid, inv.get("invoice_number", ""))
    conn.commit()


def send_invoice_email(conn, iid: int, to: str, subject: str, body: str) -> None:
    """Festgeschriebenen Beleg als PDF per E-Mail senden und – bei Erfolg –
    automatisch im Versandprotokoll als 'E-Mail' markieren."""
    from . import mailer
    company = get_company(conn)
    inv = get_invoice(conn, iid)
    if not inv:
        raise ValueError("Beleg nicht gefunden.")
    if inv["status"] != "festgeschrieben" or not inv.get("pdf_file"):
        raise ValueError("Nur festgeschriebene Belege mit PDF können versendet werden.")
    # ZUGFeRD-PDF bevorzugen: gültiges PDF MIT eingebetteter E-Rechnung (XML).
    # Nur falls keins existiert (z. B. Mahnung/Angebot), das reine Layout-PDF.
    src = inv.get("zugferd_file") or inv.get("pdf_file")
    pdf_path = config.ARCHIVE_DIR / src
    if not pdf_path.exists():
        pdf_path = config.ARCHIVE_DIR / inv["pdf_file"]
    if not pdf_path.exists():
        raise ValueError("PDF-Datei nicht gefunden.")
    fname = f"{(inv.get('invoice_number') or 'Beleg').replace('/', '-')}.pdf"
    mailer.send(company, to, subject, body,
                [(fname, pdf_path.read_bytes(), "application/pdf")])
    # Mail ist raus -> Protokoll-Markierung ist best-effort (darf nicht als
    # Sendefehler erscheinen, sonst sendet der Nutzer doppelt).
    try:
        mark_sent(conn, iid, "E-Mail")
    except Exception:  # pragma: no cover
        pass


# ====================== Zahlungen ======================

def paid_amount(conn, iid) -> float:
    row = db.query_one(conn, "SELECT COALESCE(SUM(amount),0) AS s FROM payments WHERE invoice_id = ?", (iid,))
    return float(money(row["s"] if row else 0))


def add_payment(conn, iid: int, data: dict) -> None:
    from .money import D
    try:
        amount = float(D(data.get("amount")))   # robust gegen "1.234,56"
    except Exception:
        raise ValueError("Betrag ist keine gültige Zahl.")
    conn.execute(
        "INSERT INTO payments (invoice_id, date, amount, method, note) VALUES (?,?,?,?,?)",
        (iid, data.get("date") or _dt.date.today().isoformat(),
         amount, data.get("method", "Überweisung"), data.get("note", "")),
    )
    audit.log(conn, "Zahlung erfasst", "invoice", iid, str(data.get("amount")))
    conn.commit()


def list_payments(conn, iid) -> list[dict]:
    return [dict(r) for r in db.query(
        conn, "SELECT * FROM payments WHERE invoice_id = ? ORDER BY date, id", (iid,))]
