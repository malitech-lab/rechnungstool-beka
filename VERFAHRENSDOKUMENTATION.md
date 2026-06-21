# Verfahrensdokumentation (GoBD) – Vorlage

**Betrieb:** Montageservice Beka, Nehat Beka, Im Vogelgesang 6, 67346 Speyer
**Eingesetzte Software:** Rechnungstool Montageservice Beka (lokal, Version 1.0)
**Stand:** _________  ·  **Verantwortlich:** _________

> Diese Vorlage ist vom Betrieb auszufüllen und mit dem Steuerberater
> abzustimmen. Sie beschreibt, wie Rechnungen erstellt, festgeschrieben und
> aufbewahrt werden (gefordert nach GoBD, vgl. Fachkonzept Abschnitt 5.4).

## 1. Überblick
Das Tool erstellt Ausgangsrechnungen, schreibt sie unveränderbar fest und
archiviert PDF- und E-Rechnungs-Dateien revisionssicher. Es läuft lokal auf
einem Einzelplatz-Rechner; ein externer Zugriff findet nicht statt.

## 2. Belegfluss
1. Angebot/Auftrag → Erfassung der Positionen (Katalog oder frei).
2. Prüfung der Pflichtangaben (§§ 14/14a UStG) durch das Tool.
3. **Festschreibung**: Vergabe der fortlaufenden Rechnungsnummer, Einfrieren von
   Verkäufer-/Käuferdaten und Summen, Erzeugung von PDF + XRechnung + ZUGFeRD.
4. Versand an den Kunden (per E-Mail/Ausdruck).
5. Erfassung von Zahlungseingängen, ggf. Mahnung.
6. Übergabe an den Steuerberater per DATEV-Export.

## 3. Unveränderbarkeit (GoBD)
- Festgeschriebene Rechnungen sind **nicht mehr editierbar**.
- Korrekturen erfolgen ausschließlich über **Storno-/Korrekturrechnung** mit
  Bezug auf das Original.
- Rechnungsnummern sind **lückenlos und fortlaufend** je Jahr.

## 4. Protokollierung
Jede Erstellung, Festschreibung, Stornierung und Zahlung wird im **Audit-Log**
mit Benutzer, Zeitpunkt und Aktion protokolliert (Menü „GoBD-Protokoll“).
Für jede festgeschriebene PDF-Rechnung wird eine **SHA-256-Prüfsumme** gespeichert.

## 5. Aufbewahrung & Datensicherung
- Speicherort: `C:\ProgramData\RechnungstoolBeKa` (Datenbank + Ordner `belege\`,
  `assets\`, `logs\`). Per NTFS-Rechten geschützt: SYSTEM/Administratoren
  Vollzugriff; das Alltags-Konto darf schreiben, das Belegarchiv aber **nicht
  löschen** (Schutz vor versehentlichem Löschen).
- E-Rechnungen werden im **strukturierten Originalformat** (XML) aufbewahrt.
- Aufbewahrungsfrist Rechnungen/Buchungsbelege: **8 Jahre** (seit 2025, viertes
  Bürokratieentlastungsgesetz).
- **Sicherung:** automatischer täglicher Task „RechnungstoolBeKa-Backup“
  (WAL-konsistentes, datiertes ZIP via `Rechnungstool-Beka.exe --backup`).
  Ziel-Medium (zweites Laufwerk/NAS/Cloud): __________, Verantwortlich: __________
- Datierte Sicherungen werden über die gesamte Aufbewahrungsfrist behalten
  (nicht überschrieben/rotiert).
- Wiederherstellung wurde getestet am: __________

## 6. Zugriff/Sicherheit
- Einzelplatz; Alltags-Windows-Konto: __________ ; Wartungs-/Admin-Konto: __________
- Empfehlung für vollen Schutz: getrenntes **Standard-Konto** (Alltag) +
  **Admin-Konto** (Wartung/Backup); ohne diese Trennung schützen die NTFS-Rechte
  nur vor Versehen, nicht gegen einen Anwender mit Administratorrechten.
- **Verschlüsselung-at-rest:** BitLocker auf `C:` ☐ aktiv ☐ nicht verfügbar (Home).
  Recovery-Key hinterlegt bei: __________
- Der Daten-Ordner ist Teil der regelmäßigen Datensicherung.
- Hinweis: Das Audit-Log dokumentiert Änderungen, ist aber (Stand MVP) nicht
  hash-verkettet → Schutz „gegen versehentliches Löschen + dokumentiert“, nicht
  „manipulationssicher gegen Vorsatz“.

## 7. Änderungen an diesem Dokument
| Datum | Änderung | Person |
|---|---|---|
|  |  |  |
