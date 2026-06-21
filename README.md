# Rechnungstool Montageservice Beka

Ein **lokal** auf einem Windows-Rechner laufendes Rechnungsprogramm für den
Handwerksbetrieb **Montageservice Beka** (Schornsteinbau, Ofen-/Kaminmontage,
Trockenbau, Fliesen – schornstein-beka.de). Es erzeugt rechtssichere Rechnungen
mit allen Pflichtangaben, schreibt sie GoBD-konform fest und liefert
**E-Rechnungen** (XRechnung & ZUGFeRD/Factur-X nach EN 16931).

Umgesetzt ist die **MVP-Ausbaustufe** aus dem Fachkonzept (Stammdaten, Angebot →
Rechnung, Pflichtangaben, PDF, E-Rechnung-Versand, GoBD-Archiv, DATEV-Export).

> Keine Cloud, kein Konto, keine Internetpflicht: Alle Daten bleiben auf dem
> Rechner des Betriebs. Der eingebaute Server lauscht nur lokal auf `127.0.0.1`.

---

## Schnellstart (Windows)

**Variante A – Installer (empfohlen für den Betrieb)**
1. Auf einem Windows-Rechner `build_windows.bat` ausführen → `dist\Rechnungstool-Beka.exe`.
2. `ISCC.exe deploy\setup.iss` → erzeugt `RechnungstoolBeKa-Setup.exe`.
3. Setup beim Kunden einmal **als Administrator** ausführen: legt die App nach
   *Program Files*, schützt den Datenordner und richtet die tägliche Sicherung ein.
   Künftig genügt die Desktop-Verknüpfung – die Oberfläche öffnet sich als
   **App-Fenster** (kein Browser-Tab, kein Konsolenfenster).

   Vollständige Anleitung inkl. Signatur, Datenschutz-Grenzen und Backup:
   [`deploy/README-Deployment.md`](deploy/README-Deployment.md).

**Variante B – als einzelne EXE ohne Installer**
- `build_windows.bat` ausführen, dann Doppelklick auf `dist\Rechnungstool-Beka.exe`.
  Die Oberfläche öffnet sich als App-Fenster. Ohne den Installer sind Datenordner-
  Härtung und automatisches Backup **nicht** eingerichtet (manuell: `deploy\harden.cmd`).

**Variante C – direkt aus dem Quellcode**
- Doppelklick auf **`Rechnungstool-starten.bat`**.
  Beim ersten Start wird automatisch eine Python-Umgebung eingerichtet
  (einmalig ein paar Minuten), danach startet das Tool sofort.

Voraussetzung für beide Varianten: **Python 3.10+** installiert
(https://www.python.org/downloads/ – beim Setup „Add Python to PATH“ anhaken).

### Auf dem Mac/Linux (Entwicklung)
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run.py            # öffnet http://127.0.0.1:8765
```

---

## Erste Einrichtung

Beim ersten Start sind die öffentlichen Firmendaten bereits hinterlegt. Bitte in
**Einstellungen** ergänzen (Pflicht für gültige Rechnungen):

- **Steuernummer** oder **USt-IdNr.** (§ 14 Abs. 4 UStG)
- **Bankverbindung** (IBAN/BIC) für die Zahlung
- ggf. **Kleinunternehmer §19** aktivieren, falls zutreffend
- optional: Logo, Farben, Standard-Texte, Zahlungsziel

---

## Funktionsumfang

| Bereich | Inhalt |
|---|---|
| **Stammdaten** | Firma, Logo, Nummernkreise, Steuer-/Bankdaten |
| **Kunden** | B2C/B2B/B2G, USt-IdNr., Leitweg-ID, §48-Freistellung |
| **Leistungskatalog** | wiederverwendbare Leistungen/Material (vorbefüllt) |
| **Rechnungen** | Standard, **Kleinbetrag** (§33 UStDV, automatisch), **Storno/Korrektur**, **§13b** Reverse-Charge, **§19** Kleinunternehmer |
| **PDF-Design** | Firmenlogo, Corporate-Farben, **GiroCode/EPC-QR** zum Bezahlen per Banking-App (IBAN, Betrag, Rechnungsnummer vorausgefüllt) |
| **Pflichtangaben** | automatische Prüfung (§§ 14/14a UStG) – blockiert unvollständige Rechnungen |
| **GoBD** | Festschreibung = unveränderbar, lückenlose Nummern, Audit-Log, revisionssicheres Belegarchiv inkl. SHA-256 |
| **E-Rechnung** | **XRechnung** (CII-XML, EN 16931) und **ZUGFeRD/Factur-X** (PDF mit eingebettetem XML) |
| **Zahlungen** | Zahlungseingänge, offene Posten, Mahnstand-Übersicht |
| **Export** | DATEV-Buchungsstapel (EXTF) und Umsatzliste (CSV) |
| **Übersicht** | Umsatz, offene Posten, überfällige Rechnungen |

### Typischer Ablauf
Kunde anlegen → **Neue Rechnung** → Positionen aus dem Katalog wählen →
Beträge/USt werden live berechnet → **Speichern & Festschreiben** →
PDF, XRechnung und ZUGFeRD stehen zum Download bereit.

---

## Wo liegen meine Daten? (Backup!)

Alle Daten liegen in **einem** Ordner:

- Windows: `C:\ProgramData\RechnungstoolBeKa`
- Mac/Linux: `~/Rechnungstool-BeKa-Daten`

Darin: `rechnungstool.sqlite3` (komplette Buchhaltung), `belege\` (alle
festgeschriebenen PDFs/XMLs), `assets\` und `logs\`. Der Pfad lässt sich über die
Umgebungsvariable `RECHNUNGSTOOL_DATEN` ändern.

**Beim Installer-Deployment** wird dieser Ordner per NTFS-Rechten **geschützt**
(SYSTEM/Admins Vollzugriff; das Alltags-Konto darf schreiben, aber das Belegarchiv
nicht löschen) und **täglich automatisch gesichert** (WAL-konsistentes, datiertes
ZIP – Ziel idealerweise ein zweites Medium). Manuelle Sicherung jederzeit:
`Rechnungstool-Beka.exe --backup "Z:\Ziel"` bzw. `deploy\backup-jetzt.cmd`.

Wichtige **Grenzen** (lokaler Admin hebelt ACLs aus; „versteckt“ ≠ Sicherheit;
Verschlüsselung-at-rest via BitLocker separat aktivieren) sind ehrlich
beschrieben in [`deploy/README-Deployment.md`](deploy/README-Deployment.md).

---

## Rechtlicher Stand & Grenzen (wichtig)

- Die Pflichtangaben-Prüfung und die Sonderfälle (§13b, §19, §14b-Hinweis für
  Privatkunden, §48) sind nach Rechtsstand **Juni 2026** umgesetzt
  (vgl. Fachkonzept, Abschnitt 5).
- Die erzeugte E-Rechnung wird beim Erstellen **gegen das offizielle
  EN-16931-XSD-Schema** (Factur-X 1.0.07) validiert. Eine zusätzliche
  **Schematron-/KoSIT-Prüfung** (Geschäftsregeln) ist für den Produktivbetrieb
  empfehlenswert – die XML kann dazu im KoSIT-Validator geprüft werden.
- Die **DATEV-Konten** (SKR03-Standard) in `app/datev_export.py` sind Vorgaben
  und **mit dem Steuerberater abzustimmen**.
- Dieses Tool ersetzt **keine** steuerliche oder rechtliche Beratung.

### Nicht im MVP enthalten (spätere Ausbaustufen)
Mobile Baustellen-Erfassung (offline), Abschlags-/Schlussrechnung mit
Anrechnung, automatischer Bank-Zahlungsabgleich, mehrstufiges Mahnwesen,
wiederkehrende Rechnungen, PEPPOL-Anbindung. Die Datenstruktur ist dafür
vorbereitet.

---

## Technik

- **Python 3 + Flask** (lokaler Webserver), **SQLite** (eine Datei)
- **fpdf2** (PDF), **lxml** + **drafthorse** (XRechnung/ZUGFeRD nach EN 16931)
- Keine Build-Tools nötig, keine Node-/Datenbank-Installation
- Verzeichnisstruktur:
  ```
  app/            Anwendung (server, db, services, pdf, einvoice, ...)
  app/templates/  Oberfläche (Jinja2)
  app/static/     CSS/JS + mitgelieferte Schriften (DejaVu Sans)
  tests/          automatisierte Tests der Rechnungs-/Steuerlogik
  run.py          Startpunkt (Server + Browser)
  ```

### Tests
```bash
python -m unittest discover -s tests
```
Prüft Berechnung, USt-Aufschlüsselung, Nummernkreis, Pflichtangaben,
Festschreibung/Unveränderbarkeit, Storno, Zahlungen und die EN-16931-Gültigkeit
der E-Rechnung.

---

## Lizenz / Hinweis
Internes Werkzeug für Montageservice Beka, erstellt von malitech solutions.
Die mitgelieferte Schrift „DejaVu Sans“ steht unter einer freien Lizenz.
