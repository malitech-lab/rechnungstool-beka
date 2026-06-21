"""Konsistente, GoBD-taugliche Datensicherung als datiertes ZIP-Archiv.

Die SQLite-Datenbank läuft im WAL-Modus; eine nackte Dateikopie wäre potenziell
inkonsistent. Deshalb wird die DB per ``VACUUM INTO`` als sauberer Online-Snapshot
gesichert. Belegarchiv und Assets werden mitgepackt. Aufruf über die App:

    Rechnungstool-Beka.exe --backup "Z:\\RechnungstoolBeKa-Backups"

Wichtig (GoBD): Die erzeugten, datierten Archive NICHT überschreiben/rotieren –
die Aufbewahrungsfrist beträgt i.d.R. 10 Jahre. Ziel sollte ein zweites Medium
sein (USB/NAS/Cloud), nie dieselbe Platte (3-2-1-Regel).
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app import config

DB_NAME = "rechnungstool.sqlite3"


def make_backup(dest: str | Path, when: _dt.datetime | None = None) -> Path:
    """Erzeugt ein datiertes Backup-ZIP im Zielordner und gibt dessen Pfad zurück."""
    config.ensure_dirs()
    dest_dir = Path(dest).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = (when or _dt.datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    archive = dest_dir / f"RechnungstoolBeKa-Backup_{stamp}.zip"
    i = 2   # eindeutig halten, falls mehrere Sicherungen in derselben Sekunde
    while archive.exists():
        archive = dest_dir / f"RechnungstoolBeKa-Backup_{stamp}_{i}.zip"
        i += 1

    with tempfile.TemporaryDirectory() as tmp:
        db_snap = Path(tmp) / "rechnungstool.sqlite3"
        # Konsistenter Snapshot (WAL-sicher), auch während die App geöffnet ist.
        con = sqlite3.connect(str(config.DB_PATH))
        try:
            con.execute("VACUUM INTO ?", (str(db_snap),))
        finally:
            con.close()

        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_snap, DB_NAME)
            for sub in ("belege", "assets"):
                base = config.DATA_DIR / sub
                if not base.exists():
                    continue
                for p in base.rglob("*"):
                    if p.is_file():
                        z.write(p, str(Path(sub) / p.relative_to(base)))
    return archive


def default_backup_dir() -> Path:
    return config.DATA_DIR / "backups"


def list_backups(backup_dir: str | Path | None = None) -> list[dict]:
    """Vorhandene Backup-ZIPs im Ordner, neueste zuerst."""
    d = Path(backup_dir) if backup_dir else default_backup_dir()
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("RechnungstoolBeKa-Backup_*.zip"), reverse=True):
        st = p.stat()
        out.append({"name": p.name, "path": str(p), "size": st.st_size})
    return out


def _zip_is_valid(zip_path: str | Path) -> tuple[bool, str]:
    """Prüft, ob das ZIP einen lesbaren, vollständigen DB-Snapshot enthält und ob
    die in der DB referenzierten Belege auch im Archiv liegen (sonst würde ein
    Restore das Belegarchiv ersatzlos löschen)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            if DB_NAME not in names:
                return False, "Backup enthält keine Datenbank."
            belege_im_zip = sum(1 for n in names if n.startswith("belege/")
                                and not n.endswith("/"))
            with tempfile.TemporaryDirectory() as tmp:
                z.extract(DB_NAME, tmp)
                con = sqlite3.connect(str(Path(tmp) / DB_NAME))
                try:
                    tabs = {r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                    if "invoices" not in tabs or "company" not in tabs:
                        return False, "Datenbank im Backup ist unvollständig."
                    n = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
                    referenziert = con.execute(
                        "SELECT COUNT(*) FROM invoices WHERE pdf_file <> ''").fetchone()[0]
                finally:
                    con.close()
            if referenziert and belege_im_zip == 0:
                return False, ("Backup enthält Rechnungen, aber kein Belegarchiv – "
                               "Wiederherstellung abgebrochen (würde Belege löschen).")
            return True, f"{n} Rechnungen"
    except (zipfile.BadZipFile, sqlite3.DatabaseError, OSError) as e:
        return False, f"Backup nicht lesbar: {e}"


def self_test(backup_dir: str | Path | None = None) -> dict:
    """Erstellt eine Sicherung und prüft sie sofort auf Lesbarkeit/Vollständigkeit.
    Verändert die laufenden Daten NICHT. Gibt {ok, error, invoices, belege, archive}."""
    try:
        archive = make_backup(backup_dir or default_backup_dir())
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"Sicherung schlug fehl: {e}"}
    ok, msg = _zip_is_valid(archive)
    if not ok:
        return {"ok": False, "error": msg, "archive": archive.name}
    with zipfile.ZipFile(archive) as z:
        belege = sum(1 for n in z.namelist() if n.startswith("belege/"))
    n_inv = msg.split()[0]
    return {"ok": True, "error": "", "invoices": n_inv, "belege": belege,
            "archive": archive.name}


def restore(zip_path: str | Path, make_safety: bool = True) -> dict:
    """Stellt Datenbank + Belege + Assets aus einem Backup-ZIP wieder her.

    WICHTIG: Vorher müssen alle offenen DB-Verbindungen geschlossen sein (Windows-
    Dateisperre). Legt zuvor automatisch eine Sicherheitskopie des aktuellen Stands an.
    """
    zip_path = Path(zip_path)
    ok, msg = _zip_is_valid(zip_path)
    if not ok:
        raise ValueError(msg)
    config.ensure_dirs()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Quelle ZUERST entpacken – so kann die Sicherheitskopie sie nicht
        # überschreiben (z. B. wenn das Quell-ZIP im selben Backup-Ordner liegt).
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        safety = make_backup(default_backup_dir()) if make_safety else None

        # ---- 1) STAGE: alles Neue NEBEN die Live-Daten aufbauen (.new) ------
        # Schlägt hier etwas fehl (z. B. Platte voll), bleiben die Live-Daten
        # vollständig unangetastet.
        db_new = Path(str(config.DB_PATH) + ".new")
        if db_new.exists():
            db_new.unlink()
        shutil.copy2(tmp / DB_NAME, db_new)
        staged = []   # (Ziel, .new)
        for sub in ("belege", "assets"):
            tgt = config.DATA_DIR / sub
            new = config.DATA_DIR / (sub + ".new")
            if new.exists():
                shutil.rmtree(new)
            src = tmp / sub
            if src.exists():
                shutil.copytree(src, new)
            else:
                new.mkdir(parents=True, exist_ok=True)
            staged.append((tgt, new))

        # ---- 2) SWAP: jetzt erst die Live-Daten ersetzen (schnelle os.replace) --
        for suffix in ("-wal", "-shm"):
            p = Path(str(config.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
        os.replace(db_new, config.DB_PATH)
        for tgt, new in staged:
            old = config.DATA_DIR / (tgt.name + ".old")
            if old.exists():
                shutil.rmtree(old)
            if tgt.exists():
                os.replace(tgt, old)
            os.replace(new, tgt)
            shutil.rmtree(old, ignore_errors=True)

    # ---- 3) Schema der wiederhergestellten DB auf den aktuellen Code heben ---
    from app import db as _db
    con = sqlite3.connect(str(config.DB_PATH))
    try:
        _db._migrate(con)
        con.commit()
    finally:
        con.close()
    return {"safety": safety.name if safety else None}
