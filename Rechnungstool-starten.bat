@echo off
REM ====================================================================
REM  Rechnungstool Montageservice Beka - Start aus dem Quellcode
REM  (Doppelklick). Richtet beim ersten Start automatisch alles ein.
REM ====================================================================
cd /d "%~dp0"
title Rechnungstool Montageservice Beka

REM Python pruefen
where py >nul 2>nul
if %errorlevel%==0 ( set PY=py ) else ( set PY=python )

REM Virtuelle Umgebung beim ersten Start anlegen
if not exist ".venv\Scripts\python.exe" (
    echo Erstinstallation - bitte einen Moment Geduld...
    %PY% -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo Starte Rechnungstool...
".venv\Scripts\python.exe" run.py

echo.
echo Das Rechnungstool wurde beendet.
pause
