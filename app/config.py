"""Zentrale Konfiguration: Pfade für Daten und Belegarchiv.

Die Geschäftsdaten liegen außerhalb des Programmverzeichnisses in einem
maschinenweiten Ordner (Windows: %PROGRAMDATA%\\RechnungstoolBeKa), der vom
Installer per NTFS-Rechten gehärtet wird (SYSTEM/Admins Vollzugriff, Alltags-
konto „Ändern", Löschsperre auf dem Belegarchiv). Wichtig für die GoBD-konforme
Aufbewahrung (revisionssichere Ablage) und die automatische Datensicherung.

Hinweis: DATA_DIR wird beim Modul-Import einmalig festgelegt. Soll der Pfad
abweichen, MUSS die Umgebungsvariable RECHNUNGSTOOL_DATEN gesetzt sein, BEVOR
dieses Modul importiert wird.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    """Standard-Datenverzeichnis je Betriebssystem.

    - Override per Umgebungsvariable RECHNUNGSTOOL_DATEN
    - Windows:  %PROGRAMDATA%\\RechnungstoolBeKa  (maschinenweit, gehärtet)
    - sonst:    ~/Rechnungstool-BeKa-Daten
    """
    override = os.environ.get("RECHNUNGSTOOL_DATEN")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        # ProgramData = maschinenweit, vom Installer per ACL geschützt. Bewusst
        # NICHT %APPDATA% (benutzergebunden, offen) und kein Tarnname.
        base = os.environ.get("PROGRAMDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "RechnungstoolBeKa"
    return Path.home() / "Rechnungstool-BeKa-Daten"


DATA_DIR: Path = _default_data_dir()
DB_PATH: Path = DATA_DIR / "rechnungstool.sqlite3"
# Revisionssicheres Belegarchiv (PDF / XML / ZUGFeRD je festgeschriebener Rechnung)
ARCHIVE_DIR: Path = DATA_DIR / "belege"
# Hochgeladenes Firmenlogo etc.
ASSETS_DIR: Path = DATA_DIR / "assets"

# Aktueller Einzelplatz-Benutzer (lokales Tool, ein Arbeitsplatz). Für das
# Audit-Log und die GoBD-Protokollierung relevant.
CURRENT_USER: str = os.environ.get("RECHNUNGSTOOL_USER", "Büro")

SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = int(os.environ.get("RECHNUNGSTOOL_PORT", "8765"))


def ensure_dirs() -> None:
    for p in (DATA_DIR, ARCHIVE_DIR, ASSETS_DIR):
        p.mkdir(parents=True, exist_ok=True)
