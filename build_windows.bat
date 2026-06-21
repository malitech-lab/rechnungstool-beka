@echo off
REM ====================================================================
REM  Erzeugt die eigenstaendige Windows-EXE (dist\Rechnungstool-Beka.exe)
REM ====================================================================
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 ( set PY=py ) else ( set PY=python )

if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller build_windows.spec --noconfirm

echo.
echo Fertig. Die EXE liegt in:  dist\Rechnungstool-Beka.exe
pause
