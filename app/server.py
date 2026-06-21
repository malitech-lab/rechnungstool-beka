"""Lokaler Flask-Webserver – die Bedienoberfläche des Rechnungstools.

Läuft ausschließlich lokal (127.0.0.1). Bietet Stammdaten, Kunden, Katalog,
Rechnungserstellung mit Festschreibung, Beleg-Downloads (PDF/XRechnung/ZUGFeRD),
Zahlungserfassung, DATEV-Export und das GoBD-Protokoll.
"""
from __future__ import annotations

import json
import io
import datetime as _dt

from flask import (Flask, g, request, redirect, url_for, render_template,
                   flash, Response, send_file, abort)

from . import db, config, services as S, __version__, __app_name__
from .money import money, fmt, fmt_eur, fmt_qty
from .legal import format_de
from .validation import errors as v_errors, warnings as v_warnings
from . import datev_export


def _load_secret_key() -> str:
    """Zufälligen Session-Schlüssel im geschützten Datenordner ablegen/lesen –
    statt eines fest eingebauten Werts (gleicht sonst auf jeder Installation)."""
    import os
    config.ensure_dirs()
    keyfile = config.DATA_DIR / "secret.key"
    try:
        if keyfile.exists():
            k = keyfile.read_text().strip()
            if k:
                return k
        k = os.urandom(32).hex()
        keyfile.write_text(k)
        try:
            os.chmod(keyfile, 0o600)
        except OSError:
            pass
        return k
    except OSError:
        return os.urandom(32).hex()   # Notfall: flüchtiger Schlüssel


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = _load_secret_key()   # lokal erzeugt, nicht im Code
    db.init_db()

    # ---- DB-Verbindung je Request ----
    def get_conn():
        if "conn" not in g:
            g.conn = db.connect()
        return g.conn

    @app.teardown_appcontext
    def _close(exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    # ---- Template-Hilfen ----
    @app.context_processor
    def _inject():
        return dict(company=S.get_company(get_conn()), app_name=__app_name__,
                    version=__version__, fmt=fmt, fmt_eur=fmt_eur, fmt_qty=fmt_qty,
                    format_de=format_de, today=_dt.date.today().isoformat())

    app.jinja_env.filters["eur"] = fmt_eur
    app.jinja_env.filters["de"] = format_de

    # ===================== Dashboard =====================
    @app.route("/")
    def dashboard():
        conn = get_conn()
        invoices = S.list_invoices(conn)
        # Angebote und Mahnungen zählen nicht als Umsatz/offene Posten
        finalized = [i for i in invoices if i["status"] == "festgeschrieben"
                     and i["doc_type"] not in ("angebot", "mahnung")]
        year = _dt.date.today().year
        umsatz = sum(float(money(i["total_net"])) for i in finalized
                     if str(i.get("invoice_date", "")).startswith(str(year))
                     and i["doc_type"] != "storno")
        offen = [i for i in finalized if i["doc_type"] != "storno" and i["open"] > 0.005]
        offen_sum = sum(i["open"] for i in offen)
        # Überfällig = mahnfällig (offen + seit >=14 Tagen unbezahlt)
        overdue = [i for i in offen if i.get("mahn_faellig")]
        anzahl = len([i for i in finalized
                      if str(i.get("invoice_date", "")).startswith(str(year))
                      and i["doc_type"] != "storno"])
        return render_template("dashboard.html", invoices=invoices[:8],
                               umsatz=umsatz, offen=offen, offen_sum=offen_sum,
                               overdue=overdue, year=year, anzahl=anzahl)

    # ===================== Rechnungen =====================
    @app.route("/rechnungen")
    def invoices():
        conn = get_conn()
        status = request.args.get("status") or None
        # Textsuche läuft live im Browser (siehe base.html); der Server liefert alle
        # Zeilen des gewählten Status, q dient nur zum Vorbelegen des Suchfelds.
        return render_template("invoices.html", invoices=S.list_invoices(conn, status),
                               status=status, q=request.args.get("q", ""))

    @app.route("/rechnungen/neu", methods=["POST"])
    def invoice_new():
        conn = get_conn()
        cid = request.form.get("customer_id") or None
        iid = S.create_draft(conn, cid)
        return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/angebote/neu", methods=["POST"])
    def offer_new():
        conn = get_conn()
        cid = request.form.get("customer_id") or None
        iid = S.create_draft(conn, cid, doc_type="angebot")
        return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>")
    def invoice_edit(iid):
        conn = get_conn()
        inv = S.get_invoice(conn, iid)
        if not inv:
            abort(404)
        findings = S.validate_invoice(conn, inv) if inv["status"] == "entwurf" else []
        ctx = S.build_context(conn, inv)
        paid = S.paid_amount(conn, iid)
        inv["open"] = float(money(inv["total_gross"])) - paid
        inv["mahn_faellig"] = S.mahn_faellig(inv)
        inv["mahn_tage"] = S._days_since(inv.get("invoice_date"))
        from . import mailer
        cust = S.get_customer(conn, inv["customer_id"]) if inv.get("customer_id") else None
        return render_template("invoice_edit.html", inv=inv,
                               customers=S.list_customers(conn, include_inactive=False),
                               catalog=S.list_catalog(conn, include_inactive=False),
                               calc=ctx["calc"], notes=ctx["notes"],
                               errors=v_errors(findings), warnings=v_warnings(findings),
                               payments=S.list_payments(conn, iid),
                               paid=paid,
                               cust_email=(cust or {}).get("email", ""),
                               mail_ready=mailer.is_configured(S.get_company(conn)))

    @app.route("/rechnungen/<int:iid>/speichern", methods=["POST"])
    def invoice_save(iid):
        conn = get_conn()
        head = {k: request.form.get(k, "") for k in (
            "customer_id", "title", "project_ref", "invoice_date", "service_date",
            "service_date_end", "tax_mode", "doc_type")}
        head["customer_id"] = head["customer_id"] or None
        head["due_date"] = head.get("invoice_date", "")   # sofort fällig = Rechnungsdatum
        try:
            items = json.loads(request.form.get("items_json") or "[]")
        except json.JSONDecodeError:
            items = []
        ajax = request.args.get("ajax") == "1"   # Autospeichern: keine Weiterleitung
        try:
            S.update_draft(conn, iid, head, items)
            if not ajax:
                flash("Entwurf gespeichert.", "success")
        except (PermissionError, ValueError) as e:
            if ajax:
                return (str(e), 409)
            flash(str(e), "error")
        if ajax:
            return ("", 204)
        if request.form.get("_action") == "festschreiben":
            # festschreiben ist POST-only (GoBD-Zustandsänderung, keine GET-CSRF-
            # Flanke). 307 erhält die POST-Methode beim Weiterleiten; ein normaler
            # 302 würde der Browser per GET nachladen und liefe in einen 405.
            return redirect(url_for("invoice_finalize", iid=iid), code=307)
        return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/festschreiben", methods=["POST"])
    def invoice_finalize(iid):
        conn = get_conn()
        try:
            inv = S.finalize_invoice(conn, iid)
            flash(f"Rechnung {inv['invoice_number']} wurde als PDF erstellt.", "success")
        except (PermissionError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/storno", methods=["POST"])
    def invoice_storno(iid):
        conn = get_conn()
        try:
            sid = S.create_storno(conn, iid)
            flash("Stornorechnung als Entwurf angelegt. Bitte prüfen und als PDF erstellen.", "success")
            return redirect(url_for("invoice_edit", iid=sid))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/in-rechnung", methods=["POST"])
    def offer_to_invoice(iid):
        conn = get_conn()
        try:
            rid = S.create_invoice_from_offer(conn, iid)
            flash("Rechnungs-Entwurf aus Angebot erstellt. Bitte Leistungsdatum prüfen "
                  "und als PDF erstellen.", "success")
            return redirect(url_for("invoice_edit", iid=rid))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/mahnung", methods=["POST"])
    def invoice_dunning(iid):
        conn = get_conn()
        try:
            mid = S.create_dunning(conn, iid)
            fin = S.finalize_invoice(conn, mid)
            flash(f"{S._dunning_title(fin.get('mahn_level'))} {fin['invoice_number']} erstellt.",
                  "success")
            return redirect(url_for("invoice_edit", iid=mid))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/email", methods=["POST"])
    def invoice_email(iid):
        conn = get_conn()
        try:
            S.send_invoice_email(conn, iid,
                                 to=request.form.get("to", ""),
                                 subject=request.form.get("subject", ""),
                                 body=request.form.get("body", ""))
            flash("Beleg per E-Mail versendet und im Versandprotokoll vermerkt.", "success")
        except Exception as e:
            flash(str(e), "error")
        return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/versendet", methods=["POST"])
    def invoice_mark_sent(iid):
        conn = get_conn()
        try:
            S.mark_sent(conn, iid, request.form.get("via", "Post"))
            flash("Als versendet markiert.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("invoice_edit", iid=iid))

    @app.route("/rechnungen/<int:iid>/loeschen", methods=["POST"])
    def invoice_delete(iid):
        conn = get_conn()
        try:
            S.delete_draft(conn, iid)
            flash("Entwurf gelöscht.", "success")
        except (PermissionError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("invoices"))

    @app.route("/rechnungen/<int:iid>/zahlung", methods=["POST"])
    def invoice_payment(iid):
        conn = get_conn()
        try:
            S.add_payment(conn, iid, {
                "amount": request.form.get("amount", ""),
                "date": request.form.get("date"), "method": request.form.get("method"),
                "note": request.form.get("note", "")})
            flash("Zahlung erfasst.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("invoice_edit", iid=iid))

    # ---- Beleg-Downloads ----
    def _send_archive(inv, key, mime, suffix, as_attachment=True):
        name = inv.get(key)
        if not name:
            abort(404)
        path = config.ARCHIVE_DIR / name
        if not path.exists():
            abort(404)
        # Dateiname: Rechnungsnummer_Nachname_Datum.<ext>
        download_name = S.invoice_filename(inv, suffix)
        return send_file(path, mimetype=mime, as_attachment=as_attachment,
                         download_name=download_name)

    @app.route("/rechnungen/<int:iid>/pdf")
    def invoice_pdf(iid):
        conn = get_conn()
        inv = S.get_invoice(conn, iid)
        if not inv:
            abort(404)
        # inline=1 -> Anzeige in der Vorschau; sonst Download
        inline = request.args.get("inline") == "1"
        if inv["status"] != "entwurf":
            # Standard-Download ist das ZUGFeRD-PDF (Hybrid: sieht aus wie eine
            # normale PDF, enthält aber die E-Rechnungs-Daten). Fallback: einfaches PDF.
            key = "zugferd_file" if inv.get("zugferd_file") else "pdf_file"
            return _send_archive(inv, key, "application/pdf", ".pdf",
                                 as_attachment=not inline)
        # Entwurf: Live-Vorschau wird inline angezeigt
        from . import pdf_invoice
        ctx = S.build_context(conn, inv)
        data = pdf_invoice.render(ctx)
        return send_file(io.BytesIO(data), mimetype="application/pdf",
                         as_attachment=False, download_name="Entwurf-Vorschau.pdf")

    @app.route("/rechnungen/<int:iid>/vorschau", methods=["POST"])
    def invoice_preview(iid):
        """Live-Vorschau (als PNG-Bild) aus den ungespeicherten Formulardaten."""
        from . import pdf_invoice, pdf_render
        conn = get_conn()
        inv = S.get_invoice(conn, iid)
        if not inv or inv["status"] != "entwurf":
            abort(404)
        head = {k: request.form.get(k, "") for k in (
            "customer_id", "title", "project_ref", "invoice_date", "service_date",
            "service_date_end", "tax_mode", "doc_type")}
        head["customer_id"] = head["customer_id"] or None
        head["due_date"] = head.get("invoice_date", "")   # sofort fällig = Rechnungsdatum
        try:
            items = json.loads(request.form.get("items_json") or "[]")
        except json.JSONDecodeError:
            items = []
        ctx = S.preview_context(conn, head, items)
        png = pdf_render.pdf_to_png(pdf_invoice.render(ctx))
        return Response(png, mimetype="image/png")

    @app.route("/rechnungen/<int:iid>/preview.png")
    def invoice_preview_png(iid):
        """Vorschaubild (PNG) einer Rechnung – aus dem Archiv-PDF bzw. live gerendert."""
        from . import pdf_invoice, pdf_render
        conn = get_conn()
        inv = S.get_invoice(conn, iid)
        if not inv:
            abort(404)
        pdf_bytes = None
        if inv["status"] != "entwurf" and inv.get("pdf_file"):
            path = config.ARCHIVE_DIR / inv["pdf_file"]
            if path.exists():
                pdf_bytes = path.read_bytes()
        if pdf_bytes is None:
            pdf_bytes = pdf_invoice.render(S.build_context(conn, inv))
        return Response(pdf_render.pdf_to_png(pdf_bytes), mimetype="image/png")

    @app.route("/rechnungen/<int:iid>/xml")
    def invoice_xml(iid):
        conn = get_conn()
        inv = S.get_invoice(conn, iid)
        if not inv:
            abort(404)
        return _send_archive(inv, "xml_file", "application/xml", "-xrechnung.xml")

    @app.route("/rechnungen/<int:iid>/zugferd")
    def invoice_zugferd(iid):
        conn = get_conn()
        inv = S.get_invoice(conn, iid)
        if not inv:
            abort(404)
        return _send_archive(inv, "zugferd_file", "application/pdf", "-zugferd.pdf")

    # ===================== Kunden =====================
    @app.route("/kunden")
    def customers():
        return render_template("customers.html", customers=S.list_customers(get_conn()),
                               q=request.args.get("q", ""))

    @app.route("/kunden/neu", methods=["GET", "POST"])
    @app.route("/kunden/<int:cid>", methods=["GET", "POST"])
    def customer_edit(cid=None):
        conn = get_conn()
        if request.method == "POST":
            data = {k: request.form.get(k, "") for k in (
                "company_name", "first_name", "last_name", "salutation", "street",
                "zip", "city", "email", "phone")}
            data["contact_name"] = (data["first_name"] + " " + data["last_name"]).strip()
            # entfallene Felder mit Standardwerten belegen (Privatkunde, Inland)
            data.update(kind="B2C", country="DE", vat_id="", leitweg_id="",
                        e_address="", is_bauleistend=0, freistellung_48=0,
                        freistellung_bis="", notes="", active=1)
            cid = S.save_customer(conn, data, cid)
            flash("Kunde gespeichert.", "success")
            return redirect(url_for("customers"))
        cust = S.get_customer(conn, cid) if cid else None
        return render_template("customer_edit.html", cust=cust)

    # ===================== Katalog =====================
    @app.route("/katalog")
    def catalog():
        return render_template("catalog.html", items=S.list_catalog(get_conn()),
                               q=request.args.get("q", ""))

    @app.route("/katalog/neu", methods=["GET", "POST"])
    @app.route("/katalog/<int:iid>", methods=["GET", "POST"])
    def catalog_edit(iid=None):
        conn = get_conn()
        if request.method == "POST":
            data = {k: request.form.get(k, "") for k in (
                "kind", "article_number", "name", "description", "unit")}
            data["unit_price"] = (request.form.get("unit_price") or "0").replace(",", ".")
            data["tax_rate"] = (request.form.get("tax_rate") or "19").replace(",", ".")
            data["active"] = 1 if request.form.get("active", "1") else 0
            S.save_catalog_item(conn, data, iid)
            flash("Katalogposition gespeichert.", "success")
            return redirect(url_for("catalog"))
        item = S.get_catalog_item(conn, iid) if iid else None
        return render_template("catalog_edit.html", item=item)

    # ===================== Einstellungen =====================
    @app.route("/einstellungen", methods=["GET", "POST"])
    def settings():
        conn = get_conn()
        if request.method == "POST":
            data = {k: request.form.get(k, "") for k in (
                "name", "owner", "legal_form", "street", "zip", "city",
                "phone", "email", "website", "tax_number", "vat_id", "bank_name",
                "iban", "bic", "default_tax_rate",
                "invoice_prefix", "customer_prefix", "intro_text", "footer_text",
                "color_primary", "color_accent",
                "smtp_host", "smtp_port", "smtp_user", "smtp_from", "smtp_security")}
            # Passwort nur überschreiben, wenn ein neues eingegeben wurde
            if request.form.get("smtp_password"):
                data["smtp_password"] = request.form.get("smtp_password")
            data["smtp_port"] = data.get("smtp_port") or "587"
            data["country"] = "DE"
            data["kleinunternehmer"] = 1 if request.form.get("kleinunternehmer") else 0
            logo = request.files.get("logo")
            if logo and logo.filename:
                config.ensure_dirs()
                ext = logo.filename.rsplit(".", 1)[-1].lower()
                fname = f"logo.{ext}"
                logo.save(config.ASSETS_DIR / fname)
                data["logo_file"] = fname
            S.update_company(conn, data)
            flash("Firmenstammdaten gespeichert.", "success")
            return redirect(url_for("settings"))
        from . import backup as _bk
        return render_template("settings.html", backups=_bk.list_backups())

    @app.route("/einstellungen/sicherung", methods=["POST"])
    def settings_backup():
        from . import backup as _bk, audit
        import os, tempfile
        action = request.form.get("action")
        try:
            if action == "create":
                out = _bk.make_backup(_bk.default_backup_dir())
                audit.log(get_conn(), "Sicherung erstellt", "system", "", out.name)
                get_conn().commit()
                flash(f"Sicherung erstellt: {out.name}", "success")
            elif action == "selftest":
                r = _bk.self_test()
                if not r["ok"]:
                    flash(f"Selbsttest FEHLGESCHLAGEN: {r['error']}", "error")
                elif r.get("mode") == "probelauf":
                    flash("Backup-Mechanismus funktioniert – es gibt aber noch keine "
                          "Sicherung. Bitte einmal „Sicherung jetzt erstellen“.", "success")
                else:
                    flash(f"Neueste Sicherung geprüft, alles in Ordnung: {r['invoices']} "
                          f"Rechnungen und {r['belege']} Belege lesbar ({r['archive']}).",
                          "success")
            elif action == "restore":
                up = request.files.get("backup_zip")
                tmp_path = None
                if up and up.filename:
                    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
                    os.close(fd)
                    up.save(tmp_path)
                    src = tmp_path
                else:
                    name = request.form.get("name", "")
                    cand = (_bk.default_backup_dir() / name).resolve()
                    if not (name and cand.parent == _bk.default_backup_dir().resolve()
                            and cand.exists()):
                        flash("Kein gültiges Backup ausgewählt.", "error")
                        return redirect(url_for("settings"))
                    src = str(cand)
                # offene DB-Verbindung schließen (Dateisperre unter Windows)
                c = g.pop("conn", None)
                if c is not None:
                    c.close()
                try:
                    res = _bk.restore(src)
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)   # Upload-Temp immer aufräumen
                conn2 = db.connect()   # in der wiederhergestellten DB protokollieren
                audit.log(conn2, "Datensicherung wiederhergestellt", "system", "",
                          f"Sicherheitskopie: {res.get('safety') or '-'}")
                conn2.commit()
                conn2.close()
                flash("Daten wiederhergestellt. Bitte starten Sie das Programm neu, "
                      "damit alle Änderungen sicher greifen.", "success")
            else:
                flash("Unbekannte Aktion.", "error")
        except Exception as e:
            flash(f"Fehler: {e}", "error")
        return redirect(url_for("settings"))

    # ===================== Export / Protokoll =====================
    def _period_suffix(von, bis):
        if von and bis:
            return f"_{von}_bis_{bis}"
        return f"_ab_{von}" if von else (f"_bis_{bis}" if bis else "")

    @app.route("/export/datev")
    def export_datev():
        conn = get_conn()
        von, bis = request.args.get("von") or None, request.args.get("bis") or None
        rows = _finalized_for_export(conn, von=von, bis=bis)
        data = datev_export.extf_buchungsstapel(
            rows, mandant=request.args.get("mandant", ""),
            berater=request.args.get("berater", ""))
        fn = f"DATEV-EXTF{_period_suffix(von, bis) or '-' + str(_dt.date.today())}.csv"
        return Response(data.encode("latin-1", "replace"), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={fn}"})

    @app.route("/export/umsatz")
    def export_umsatz():
        conn = get_conn()
        von, bis = request.args.get("von") or None, request.args.get("bis") or None
        rows = _finalized_for_export(conn, with_open=True, von=von, bis=bis)
        data = datev_export.umsatz_csv(rows)
        fn = f"Umsatzliste{_period_suffix(von, bis) or '-' + str(_dt.date.today())}.csv"
        return Response("﻿" + data, mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={fn}"})

    def _finalized_for_export(conn, with_open=False, von=None, bis=None):
        out = []
        for inv in S.list_invoices(conn, status="festgeschrieben"):
            if inv["doc_type"] in ("angebot", "mahnung"):   # nicht an den Steuerberater
                continue
            d = inv.get("invoice_date") or ""
            if (von and d < von) or (bis and d > bis):       # Zeitraum-Filter
                continue
            full = S.get_invoice(conn, inv["id"])
            calc = S.compute_invoice(conn, full)
            out.append({
                "number": inv["invoice_number"], "invoice_date": inv["invoice_date"],
                "buyer_name": inv["buyer_name"], "total_net": inv["total_net"],
                "total_tax": inv["total_tax"], "total_gross": inv["total_gross"],
                "doc_type": inv["doc_type"], "status": inv["status"],
                "paid": inv.get("paid", 0), "open": inv.get("open", 0),
                "tax_groups": [(float(g.rate), float(g.net), float(g.tax)) for g in calc.tax_groups],
            })
        return out

    @app.route("/protokoll")
    def audit_log():
        conn = get_conn()
        rows = [dict(r) for r in db.query(
            conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 500")]
        return render_template("audit.html", rows=rows)

    @app.route("/protokoll/pruefen")
    def audit_verify():
        from . import audit
        res = audit.verify_chain(get_conn())
        if res["ok"]:
            flash(f"Protokoll unverändert: {res['count']} Einträge, Hash-Kette lückenlos.",
                  "success")
        else:
            flash(f"WARNUNG: Hash-Kette gebrochen ab Eintrag #{res['broken_id']} – "
                  f"das Protokoll wurde nachträglich verändert!", "error")
        return redirect(url_for("audit_log"))

    return app
