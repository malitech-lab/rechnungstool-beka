# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec: erzeugt eine einzelne Windows-EXE (Rechnungstool-Beka.exe).

Bauen (auf einem Windows-Rechner, im Projektordner, venv aktiv):
    pip install pyinstaller
    pyinstaller build_windows.spec --noconfirm

Ergebnis:  dist\\Rechnungstool-Beka.exe  (per Doppelklick startbar)
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

datas = []
# E-Rechnungs-XSD-Schemata von drafthorse (für die Validierung zur Laufzeit)
datas += collect_data_files("drafthorse")
# Flask-Templates, CSS/JS und die mitgelieferten Schriften
datas += [("app/templates", "app/templates"), ("app/static", "app/static")]
# PDFium-Bibliothek von pypdfium2 (native DLL) mitnehmen
datas += collect_data_files("pypdfium2_raw")
# certifi-CA-Bundle (cacert.pem) für den TLS-E-Mail-Versand mitnehmen
datas += collect_data_files("certifi")

binaries = []
binaries += collect_dynamic_libs("pypdfium2_raw")

hiddenimports = collect_submodules("drafthorse")
hiddenimports += ["lxml._elementpath", "lxml.etree", "segno", "PIL", "PIL.Image",
                  "PIL.ImageDraw", "pypdfium2", "pypdfium2_raw",
                  # App-Fenster/Tray + Backup-Modul (lazy importiert in run.py)
                  "pystray", "pystray._win32", "app.backup", "certifi",
                  "truststore"]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Rechnungstool-Beka",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX provoziert Defender/SmartScreen-Fehlalarme
    runtime_tmpdir=None,
    console=False,         # versteckter Server: kein Konsolenfenster (Logging -> Datei)
    disable_windowed_traceback=False,
    icon=("app/static/icon.ico" if os.path.exists("app/static/icon.ico") else None),
)
