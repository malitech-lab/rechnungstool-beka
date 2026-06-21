"""Automatisierte Tests der rechnungs- und steuerrelevanten Kernlogik.

Ausführen:  python -m unittest discover -s tests   (im Projektordner, venv aktiv)
Die Steuer-/Rechnungslogik ist sicherheitskritisch – diese Tests prüfen
Berechnung, Pflichtangaben, Festschreibung (GoBD) und E-Rechnung.
"""
import os
import tempfile
import unittest
from decimal import Decimal

# Isoliertes Datenverzeichnis VOR dem Import der App setzen
_TMP = tempfile.mkdtemp(prefix="beka_test_")
os.environ["RECHNUNGSTOOL_DATEN"] = _TMP

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, services as S, invoice_calc as ic, numbering, money, einvoice  # noqa: E402
from app.validation import errors as v_errors  # noqa: E402


class TestMoney(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual(money.money("10.005"), Decimal("10.01"))
        self.assertEqual(money.money(0.1) + money.money(0.2), Decimal("0.30"))

    def test_format_de(self):
        self.assertEqual(money.fmt(1234.5), "1.234,50")
        self.assertEqual(money.fmt_qty(6.0), "6")
        self.assertEqual(money.fmt_qty(10.5), "10,5")


class TestCalc(unittest.TestCase):
    items = [
        {"item_type": "leistung", "name": "A", "quantity": 6, "unit": "lfm",
         "unit_price": 95.0, "discount_percent": 0, "tax_rate": 19.0},
        {"item_type": "leistung", "name": "B", "quantity": 8, "unit": "Std",
         "unit_price": 58.0, "discount_percent": 10, "tax_rate": 19.0},
        {"item_type": "material", "name": "C", "quantity": 1, "unit": "Stk",
         "unit_price": 210.50, "discount_percent": 0, "tax_rate": 7.0},
    ]

    def test_totals_and_groups(self):
        r = ic.compute(self.items, "regel")
        self.assertEqual(r.total_net, Decimal("1198.10"))
        self.assertEqual(r.total_tax, Decimal("202.38"))
        self.assertEqual(r.total_gross, Decimal("1400.48"))
        rates = {str(g.rate): g.tax for g in r.tax_groups}
        self.assertEqual(rates["7.0"], Decimal("14.74"))
        self.assertEqual(rates["19.0"], Decimal("187.64"))

    def test_reverse_charge_no_vat(self):
        r = ic.compute(self.items, "reverse_charge")
        self.assertEqual(r.total_tax, Decimal("0.00"))
        self.assertEqual(r.total_gross, r.total_net)

    def test_kleinunternehmer_no_vat(self):
        r = ic.compute(self.items, "kleinunternehmer")
        self.assertEqual(r.total_tax, Decimal("0.00"))

    def test_small_amount(self):
        self.assertTrue(ic.is_small_amount(250))
        self.assertFalse(ic.is_small_amount(250.01))

    def test_zero_group_skipped(self):
        items = [{"item_type": "leistung", "name": "X", "quantity": 1, "unit_price": 0,
                  "discount_percent": 0, "tax_rate": 19.0}]
        r = ic.compute(items, "regel")
        self.assertEqual(r.tax_groups, [])


class TestServicePeriod(unittest.TestCase):
    def test_single_day(self):
        from app.legal import service_period, service_period_full
        self.assertEqual(service_period("2026-06-15", ""), ("Leistungsdatum", "15.06.2026"))
        self.assertEqual(service_period("2026-06-15", "2026-06-15"), ("Leistungsdatum", "15.06.2026"))
        self.assertEqual(service_period_full("2026-06-15", ""), "15.06.2026")

    def test_range_same_year(self):
        from app.legal import service_period, service_period_full
        self.assertEqual(service_period("2026-06-15", "2026-06-19"),
                         ("Leistungszeitraum", "15.06.–19.06.2026"))
        self.assertEqual(service_period_full("2026-06-15", "2026-06-19"),
                         "15.06.2026 – 19.06.2026")


class TestFilename(unittest.TestCase):
    def test_filename_with_lastname(self):
        import json
        inv = {"invoice_number": "RE-2026-0014", "invoice_date": "2026-06-19",
               "buyer_json": json.dumps({"last_name": "Mustermann", "name_full": "Max Mustermann"})}
        self.assertEqual(S.invoice_filename(inv), "RE-2026-0014_Mustermann_2026-06-19.pdf")

    def test_filename_fallback_from_full(self):
        import json
        inv = {"invoice_number": "RE-2026-0015", "invoice_date": "2026-06-19",
               "buyer_json": json.dumps({"name_full": "Erika Beispiel"})}
        self.assertEqual(S.invoice_filename(inv), "RE-2026-0015_Beispiel_2026-06-19.pdf")


class TestNumbering(unittest.TestCase):
    def test_sequential_gapless(self):
        db.init_db()
        conn = db.connect()
        a = numbering.next_invoice_number(conn, "RE")
        b = numbering.next_invoice_number(conn, "RE")
        self.assertNotEqual(a, b)
        na = int(a.split("-")[-1]); nb = int(b.split("-")[-1])
        self.assertEqual(nb, na + 1)
        peek = numbering.peek_invoice_number(conn, "RE")
        self.assertEqual(int(peek.split("-")[-1]), nb + 1)
        conn.close()


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.conn = db.connect()
        S.update_company(self.conn, {"tax_number": "27/123/45678",
                                     "iban": "DE12545500100123456789",
                                     "bank_name": "Sparkasse", "bic": "MALADE51LUH"})

    def tearDown(self):
        self.conn.close()

    def _full_invoice(self):
        cid = S.save_customer(self.conn, {"kind": "B2C", "salutation": "Herr",
            "contact_name": "Max Mustermann", "street": "Hauptstr 12",
            "zip": "67434", "city": "Neustadt", "country": "DE"})
        iid = S.create_draft(self.conn, cid)
        items = [{"item_type": "leistung", "name": "Schornsteinsanierung",
                  "quantity": 6, "unit": "lfm", "unit_price": 95.0,
                  "discount_percent": 0, "tax_rate": 19.0}]
        S.update_draft(self.conn, iid, {"customer_id": cid, "title": "T",
            "service_date": "2026-06-10", "service_date_end": "2026-06-12",
            "tax_mode": "regel"}, items)
        return iid

    def test_validation_blocks_without_taxnumber(self):
        # leere Firma -> Fehler
        c = db.connect()
        c.execute("UPDATE company SET tax_number='', vat_id='' WHERE id=1")
        c.commit()
        iid = self._full_invoice()
        inv = S.get_invoice(c, iid)
        findings = S.validate_invoice(c, inv)
        self.assertTrue(any("Steuernummer" in f.message for f in v_errors(findings)))
        c.close()

    def test_finalize_and_immutability(self):
        iid = self._full_invoice()
        inv = S.finalize_invoice(self.conn, iid)
        self.assertEqual(inv["status"], "festgeschrieben")
        self.assertTrue(inv["invoice_number"].startswith("RE-"))
        self.assertTrue(inv["pdf_file"])
        self.assertTrue(inv["xml_file"])
        self.assertTrue(inv["zugferd_file"])
        self.assertEqual(len(inv["pdf_sha256"]), 64)
        # Belegdateien existieren
        from app import config
        self.assertTrue((config.ARCHIVE_DIR / inv["pdf_file"]).exists())
        # Unveränderbarkeit
        with self.assertRaises(PermissionError):
            S.update_draft(self.conn, iid, {}, [])

    def test_storno(self):
        iid = self._full_invoice()
        S.finalize_invoice(self.conn, iid)
        sid = S.create_storno(self.conn, iid)
        sfin = S.finalize_invoice(self.conn, sid)
        self.assertEqual(sfin["doc_type"], "storno")
        self.assertLess(sfin["total_gross"], 0)
        # kein zweites Storno
        with self.assertRaises(ValueError):
            S.create_storno(self.conn, iid)

    def test_payment_open_items(self):
        iid = self._full_invoice()
        fin = S.finalize_invoice(self.conn, iid)
        S.add_payment(self.conn, iid, {"amount": 100.0})
        self.assertEqual(S.paid_amount(self.conn, iid), 100.0)
        self.assertGreater(fin["total_gross"], 100.0)

    def test_dunning(self):
        iid = self._full_invoice()
        fin = S.finalize_invoice(self.conn, iid)
        # Stufe 1 (Zahlungserinnerung)
        m = S.finalize_invoice(self.conn, S.create_dunning(self.conn, iid))
        self.assertEqual(m["doc_type"], "mahnung")
        self.assertTrue(m["invoice_number"].startswith("MA-"))
        self.assertEqual(m["mahn_level"], 1)
        self.assertEqual(m["references_invoice_id"], iid)
        self.assertFalse(m["xml_file"])      # Mahnung hat keine E-Rechnung
        self.assertAlmostEqual(m["total_gross"], fin["total_gross"], places=2)
        # Stufe zählt hoch
        m2 = S.finalize_invoice(self.conn, S.create_dunning(self.conn, iid))
        self.assertEqual(m2["mahn_level"], 2)
        # vollständig bezahlte Rechnung kann nicht gemahnt werden
        S.add_payment(self.conn, iid, {"amount": fin["total_gross"]})
        with self.assertRaises(ValueError):
            S.create_dunning(self.conn, iid)

    def test_mailer_and_versand(self):
        from app import mailer
        company = {"smtp_host": "smtp.example.com", "smtp_from": "a@b.de"}
        self.assertTrue(mailer.is_configured(company))
        msg = mailer.build_message(company, "kunde@x.de", "Betreff", "Hallo",
                                   [("RE-1.pdf", b"%PDF-1.4 test", "application/pdf")])
        self.assertEqual(msg["To"], "kunde@x.de")
        self.assertEqual(msg["From"], "a@b.de")
        atts = list(msg.iter_attachments())
        self.assertEqual(len(atts), 1)
        self.assertEqual(atts[0].get_filename(), "RE-1.pdf")
        # nicht eingerichtet -> klarer Fehler statt Absturz
        with self.assertRaises(mailer.MailError):
            mailer.send({}, "k@x.de", "s", "b", [])
        # Versandprotokoll
        iid = self._full_invoice()
        S.finalize_invoice(self.conn, iid)
        S.mark_sent(self.conn, iid, "Post")
        inv = S.get_invoice(self.conn, iid)
        self.assertTrue(inv["sent_at"])
        self.assertEqual(inv["sent_via"], "Post")

    def test_zz_backup_restore(self):
        from app import backup
        S.finalize_invoice(self.conn, self._full_invoice())
        self.assertTrue(backup.self_test()["ok"])
        arch = backup.make_backup(backup.default_backup_dir())
        before = len([i for i in S.list_invoices(self.conn) if i["status"] == "festgeschrieben"])
        S.finalize_invoice(self.conn, self._full_invoice())   # Stand ändert sich (+1)
        self.assertEqual(
            len([i for i in S.list_invoices(self.conn) if i["status"] == "festgeschrieben"]),
            before + 1)
        self.conn.close()
        backup.restore(arch, make_safety=False)               # auf Backup-Stand zurück
        c = db.connect()
        after = len([i for i in S.list_invoices(c) if i["status"] == "festgeschrieben"])
        self.assertEqual(after, before)                       # die zusätzliche Rechnung ist weg
        c.close()
        # Datensicherheit: ein ZIP mit DB, aber ohne Belegarchiv, muss abgewiesen
        # werden (sonst würde der Restore die Belege ersatzlos löschen).
        import zipfile
        from pathlib import Path
        bad = Path(backup.default_backup_dir()) / "nur-db.zip"
        with zipfile.ZipFile(arch) as z, zipfile.ZipFile(bad, "w") as out:
            out.writestr("rechnungstool.sqlite3", z.read("rechnungstool.sqlite3"))
        with self.assertRaises(ValueError):
            backup.restore(bad, make_safety=False)

    def test_einvoice_rules(self):
        from app import einvoice_rules
        iid = self._full_invoice()
        S.finalize_invoice(self.conn, iid)
        ctx = S.build_context(self.conn, S.get_invoice(self.conn, iid))
        self.assertTrue(einvoice_rules.check(ctx)["ok"])   # vollständig -> keine Fehler
        # kaputter Kontext -> Fehler werden erkannt
        ctx["invoice"]["number"] = ""
        ctx["company"] = dict(ctx["company"]); ctx["company"]["name"] = ""
        res = einvoice_rules.check(ctx)
        self.assertFalse(res["ok"])
        self.assertTrue(any("BR-02" in e for e in res["errors"]))
        self.assertTrue(any("BR-06" in e for e in res["errors"]))

    def test_audit_chain(self):
        from app import audit
        iid = self._full_invoice()
        S.finalize_invoice(self.conn, iid)   # erzeugt Protokoll-Einträge
        self.assertTrue(audit.verify_chain(self.conn)["ok"])
        # nachträgliche Manipulation am Protokoll wird erkannt
        rid = self.conn.execute("SELECT id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.conn.execute("UPDATE audit_log SET detail='geaendert' WHERE id=?", (rid,))
        self.conn.commit()
        self.assertFalse(audit.verify_chain(self.conn)["ok"])

    def test_mahn_faellig(self):
        import datetime as _dt
        base = {"status": "festgeschrieben", "doc_type": "standard", "open": 100.0}
        today = _dt.date.today().isoformat()
        old = (_dt.date.today() - _dt.timedelta(days=20)).isoformat()
        self.assertFalse(S.mahn_faellig({**base, "invoice_date": today}))   # frisch
        self.assertTrue(S.mahn_faellig({**base, "invoice_date": old}))      # 20 Tage offen
        self.assertFalse(S.mahn_faellig({**base, "open": 0.0, "invoice_date": old}))  # bezahlt


class TestEInvoiceXSD(unittest.TestCase):
    """drafthorse validiert beim Serialisieren gegen die EN-16931-XSD."""
    def _ctx(self, mode):
        company = dict(name="Montageservice Beka", street="Im Vogelgesang 6",
                       zip="67346", city="Speyer", country="DE", email="info@x.de",
                       tax_number="27/123/45678", vat_id="DE327654321",
                       iban="DE12545500100123456789", kleinunternehmer=0)
        items = [{"item_type": "leistung", "name": "Pos", "description": "d",
                  "quantity": 6, "unit": "lfm", "unit_price": 95.0,
                  "discount_percent": 0, "tax_rate": 19.0}]
        calc = ic.compute(items, mode)
        inv = dict(number="RE-2026-0001", doc_type="standard", invoice_date="2026-06-19",
                   service_date="Juni 2026", due_date="2026-07-03", tax_mode=mode)
        buyer = dict(name_full="Max M", name_lines=["Max M"], street="Hauptstr 12",
                     zip="67434", city="Neustadt", country="DE",
                     customer_number="K-0001", _raw={"kind": "B2C"})
        return dict(company=company, buyer=buyer, invoice=inv, calc=calc,
                    payment_text="Zahlbar bis 03.07.2026")

    def test_en16931_valid_all_modes(self):
        for mode in ("regel", "kleinunternehmer", "reverse_charge"):
            xml = einvoice.cii_xml(self._ctx(mode))  # wirft bei Schema-Fehler
            self.assertIn(b"CrossIndustryInvoice", xml)
            self.assertIn(b"570.00", xml)  # LineTotalAmount der Position
            self.assertIn(b"678.30" if mode == "regel" else b"570.00", xml)  # Grand total

    def test_zugferd_embeds_xml(self):
        from app import pdf_invoice
        ctx = self._ctx("regel")
        ctx["notes"] = []
        ctx["logo_path"] = None
        ctx["is_small"] = False
        ctx["buyer"]["salutation_line"] = "Sehr geehrter Herr M,"
        pdf = pdf_invoice.render(ctx)
        xml = einvoice.cii_xml(ctx)
        zug = einvoice.zugferd_pdf(pdf, xml)
        self.assertIn(b"factur-x.xml", zug)
        self.assertTrue(zug.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
