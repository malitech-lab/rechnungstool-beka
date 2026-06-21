"""Startet das Rechnungstool: versteckter lokaler Server + App-Fenster.

Im Auslieferungsbetrieb (Windows, als EXE mit console=False) läuft der Flask-
Server unsichtbar im Hintergrund; die Bedienung öffnet sich als rahmenloses
Edge-/Chromium-App-Fenster (kein Browser-Tab, keine Adressleiste). Ein kleines
Tray-Icon dient zum sauberen Beenden. Gelauscht wird ausschließlich lokal auf
127.0.0.1 – kein Zugriff von außen.

Sonderaufruf für die Datensicherung (vom geplanten Task genutzt):
    Rechnungstool-Beka.exe --backup "Z:\\Zielordner"
erzeugt ein konsistentes, datiertes Backup-ZIP und beendet sich wieder.
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app import config

log = logging.getLogger("rechnungstool")


def _setup_logging() -> None:
    """Logging in eine rotierende Datei (zwingend bei console=False, sonst wirft
    print() eine Exception, weil stdout None ist) und – falls vorhanden – auf
    die Konsole im Entwicklungsbetrieb."""
    config.ensure_dirs()
    logdir = config.DATA_DIR / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(logdir / "app.log", maxBytes=1_000_000,
                            backupCount=5, encoding="utf-8")
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _find_browser() -> str | None:
    """Edge (bevorzugt) oder Chrome auf Windows finden – für den App-Modus."""
    if not sys.platform.startswith("win"):
        return None
    candidates: list[str] = []
    try:
        import winreg  # nur auf Windows vorhanden
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for exe in ("msedge.exe", "chrome.exe"):
                try:
                    key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\" + exe
                    with winreg.OpenKey(hive, key) as k:
                        p = winreg.QueryValue(k, None)
                        if p:
                            candidates.append(p)
                except OSError:
                    pass
    except Exception:
        pass
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates += [
        os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _open_app_window(url: str) -> None:
    """Bedienoberfläche öffnen: als App-Fenster (Edge/Chrome --app) ohne Tab/
    Adressleiste, sonst Fallback auf den Standardbrowser."""
    exe = _find_browser()
    if exe:
        profile = os.path.join(
            os.environ.get("LOCALAPPDATA", str(Path.home())),
            "RechnungstoolBeKa", "appprofile")
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860",
                              f"--user-data-dir={profile}"])
            return
        except Exception as e:  # pragma: no cover - nur Windows-Laufzeit
            log.warning("App-Fenster konnte nicht geöffnet werden: %s", e)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def _serve(app) -> None:
    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, debug=False,
            use_reloader=False, threaded=True)


def _run_tray(url: str) -> bool:
    """Tray-Icon zum Öffnen/Beenden. Nur Windows (paketiert). Blockiert bis
    „Beenden". Gibt False zurück, wenn kein Tray möglich ist."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        return False
    img = Image.new("RGB", (64, 64), (15, 42, 74))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 30, 30, 48], fill=(230, 126, 34))
    d.rectangle([34, 22, 48, 48], fill=(230, 126, 34))

    def _open(icon, item):
        _open_app_window(url)

    def _quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Rechnungstool öffnen", _open, default=True),
        pystray.MenuItem("Beenden", _quit),
    )
    pystray.Icon("RechnungstoolBeKa", img, "Rechnungstool Beka", menu).run()
    return True


def _run_backup() -> int:
    """--backup <ziel>: konsistentes, datiertes Backup erstellen und beenden."""
    argv = sys.argv
    idx = argv.index("--backup")
    dest = argv[idx + 1] if len(argv) > idx + 1 else str(config.DATA_DIR / "backups")
    from app import backup
    out = backup.make_backup(dest)
    log.info("Backup erstellt: %s", out)
    return 0


def main() -> None:
    _setup_logging()

    if "--backup" in sys.argv:
        raise SystemExit(_run_backup())

    url = f"http://{config.SERVER_HOST}:{config.SERVER_PORT}/"
    log.info("Rechnungstool startet – Daten-Ordner: %s", config.DATA_DIR)

    # Läuft schon eine Instanz? Dann nur das Fenster öffnen, keinen 2. Server.
    if _port_in_use(config.SERVER_HOST, config.SERVER_PORT):
        log.info("Server läuft bereits – öffne nur das Fenster (%s).", url)
        _open_app_window(url)
        return

    from app.server import create_app
    app = create_app()

    server = threading.Thread(target=_serve, args=(app,), daemon=True)
    server.start()
    threading.Timer(1.0, _open_app_window, args=[url]).start()

    # Im paketierten Windows-Betrieb hält das Tray-Icon den Prozess am Leben.
    # Sonst (Entwicklung/Konsole) blockierend am Server-Thread hängen bleiben.
    if not _run_tray(url):
        print("=" * 60)
        print("  Rechnungstool Montageservice Beka")
        print(f"  Geöffnet: {url}")
        print(f"  Daten-Ordner: {config.DATA_DIR}")
        print("  Zum Beenden dieses Fenster schließen (Strg+C).")
        print("=" * 60)
        try:
            server.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
