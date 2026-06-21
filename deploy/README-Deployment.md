# Deployment auf Windows (Stufe a – „Einfach-Standard")

Diese Anleitung erzeugt aus dem Quellcode eine **native wirkende Windows-App**:
versteckter Server (kein Konsolenfenster), Bedienung in einem **Edge-App-Fenster**
(kein Browser-Tab), Daten in einem **geschützten Ordner** und eine **automatische
tägliche Sicherung**.

> ⚠️ **Der Build muss auf Windows laufen.** PyInstaller erzeugt nur für das
> Betriebssystem, auf dem es läuft – der Mac kann die Auslieferungs-EXE **nicht**
> bauen. Eine Windows-10/11-VM oder ein Windows-PC ist Pflicht (auch für Updates).

---

## 1. EXE bauen (auf dem Windows-Rechner)

```bat
:: im Projektordner, einmalig die Umgebung + PyInstaller
build_windows.bat
```

`build_windows.bat` legt bei Bedarf die venv an, installiert `requirements.txt`
+ PyInstaller und baut nach **`dist\Rechnungstool-Beka.exe`**.

Manuell entspricht das:
```bat
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller
.venv\Scripts\python -m PyInstaller build_windows.spec --noconfirm
```

Ergebnis ist **eine** EXE: `console=False` (kein schwarzes Fenster), `upx=False`
(keine Defender-Fehlalarme). Start- und Fehlermeldungen schreibt die App nach
`C:\ProgramData\RechnungstoolBeKa\logs\app.log`.

## 2. Installer bauen (Inno Setup)

[Inno Setup](https://jrsoftware.org/isinfo.php) installieren, dann:
```bat
ISCC.exe deploy\setup.iss
```
→ erzeugt `deploy\Output\RechnungstoolBeKa-Setup.exe`.

Der Installer fragt zwei Dinge ab:
1. **Alltags-Windows-Konto** – das Konto, das täglich arbeitet (für die Schreibrechte).
2. **Sicherungs-Zielordner** – am besten ein **zweites Laufwerk** (USB/NAS/Cloud).

und richtet beim Installieren (als Admin) automatisch ein:
- EXE nach `C:\Program Files\RechnungstoolBeKa`, Desktop-/Startmenü-Verknüpfung
- gehärteter Datenordner (`deploy\harden.cmd`)
- tägliche Sicherung um 20:00 Uhr (`deploy\register-backup.cmd`)

## 3. Code signieren (dringend empfohlen)

Ohne Signatur zeigt Windows **SmartScreen**-Warnungen, die gerade nicht-technische
Nutzer maximal verunsichern. EXE **und** Setup.exe mit `signtool` signieren:
```bat
signtool sign /fd SHA256 /tr http://zeitstempel-url /td SHA256 dist\Rechnungstool-Beka.exe
signtool sign /fd SHA256 /tr http://zeitstempel-url /td SHA256 deploy\Output\RechnungstoolBeKa-Setup.exe
```

---

## Datenort & Schutz

**Pfad:** `C:\ProgramData\RechnungstoolBeKa` (DB, `belege\`, `assets\`, `logs\`).
Bewusst **klar benannt** und maschinenweit – kein Tarnname (getarnte „Cache“-Ordner
werden von Aufräum-Tools bevorzugt gelöscht).

`harden.cmd` setzt per `icacls`:
- **SYSTEM + Administratoren:** Vollzugriff, Besitz bei Administratoren.
- **Alltags-Konto:** Ändern (lesen/schreiben) – aber **kein Löschen im Belegarchiv**.

Die Härtung passiert **einmalig im Installer** (läuft ohnehin als Admin). Im
Alltag startet die App **ohne UAC-Abfrage**, weil die Schreibrechte vorab gesetzt sind.

### Ehrliche Grenzen (bitte dem Betrieb so sagen)

1. **„Versteckt“ ist keine Sicherheit.** ProgramData ist nur „ausgeblendet“; echter
   Schutz kommt von den NTFS-Rechten + Verschlüsselung, nicht vom Pfad.
2. **Lokaler Admin hebelt ACLs aus.** Ist das Alltags-Konto selbst lokaler
   Administrator (im Handwerk häufig), kann es die Rechte mit `takeown` aushebeln.
   Die ACL schützt dann nur vor **Versehen**, nicht vor Absicht. Saubere Lösung:
   **getrenntes Standard-Konto (Alltag) + Admin-Konto (Wartung)** – siehe Stufe b.
3. **Verschlüsselung-at-rest separat aktivieren:** **BitLocker** auf `C:`. Achtung –
   **Windows Home hat kein BitLocker.** Edition prüfen (`manage-bde -status C:`); ohne
   Verschlüsselung sind die Daten bei Diebstahl/Platten-Ausbau im Klartext lesbar.
   Recovery-Key extern hinterlegen. (Kein EFS – zerstört Laien-Backups.)
4. **GoBD-Manipulationsschutz begrenzt:** Das Audit-Log ist (noch) ohne
   Hash-Verkettung. Zusagbar ist „geschützt gegen versehentliches Löschen +
   dokumentiert“, **nicht** „manipulationssicher gegen Vorsatz“. Ausbaustufe: Audit-Log
   per fortlaufender SHA-256-Kette verketten (Stufe b).

---

## Datensicherung (GoBD)

- Automatisch täglich via Aufgabenplanung („RechnungstoolBeKa-Backup“). Die App
  sichert die DB **WAL-konsistent** (`VACUUM INTO`) + `belege\` + `assets\` in ein
  **datiertes ZIP** im gewählten Zielordner.
- **Datierte Archive aufbewahren (ca. 10 Jahre), nicht überschreiben.** Ziel auf ein
  **zweites Medium** legen (3-2-1-Regel).
- Sofort-Sicherung von Hand: `deploy\backup-jetzt.cmd` (oder
  `Rechnungstool-Beka.exe --backup "Z:\Ziel"`).
- **Restore einmal real testen** (App beenden, ZIP zurück nach ProgramData, ggf.
  `harden.cmd` erneut ausführen). Ein ungetestetes Backup ist kein Backup.

---

## Stufe b – „Gehärtet“ (optional, später)

- Getrenntes **Standard-Benutzerkonto** (Alltag) + **Admin-Konto** (Wartung) → macht
  die ACLs erst gegen Vorsatz wirksam.
- **BitLocker erzwingen/prüfen**; auf Home-Edition alternativ **SQLCipher** als
  App-DB-Verschlüsselung.
- **Audit-Log mit SHA-256-Hash-Kette** für belastbare Revisionssicherheit.

---

## Update-Pfad

**Neue Version = einfach die neue `Setup.exe` drüberlaufen lassen.** Der Installer
erkennt die vorhandene Installation automatisch und im Update-Modus:

1. erstellt **zuerst automatisch eine Sicherung** (`--backup` in den Backups-Ordner),
2. **schließt die laufende App** (damit die EXE ersetzt werden kann),
3. **tauscht nur die EXE aus** – fragt **nicht** erneut nach Konto/Sicherungsziel und
   härtet/registriert **nicht** neu (bleibt alles bestehen).

Der **Datenordner in ProgramData bleibt unangetastet**; das DB-Schema migriert sich
beim ersten Start der neuen Version selbst (`app/db.py`, idempotent). Die neue
Version sollte – wie die erste – **signiert** sein (SmartScreen).

> Hinweis: Die Update-Erkennung geht vom Standard-Installationspfad
> `C:\Program Files\RechnungstoolBeKa` aus. Wird ein abweichender Pfad gewählt, läuft
> das Setup als Erst-Installation (harmlos, aber Konto/Sicherung würden erneut abgefragt).
