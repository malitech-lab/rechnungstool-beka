@echo off
REM ====================================================================
REM  Sofort-Sicherung von Hand (zusaetzlich zur taeglichen Automatik).
REM  Optional Zielordner angeben:   backup-jetzt.cmd "Z:\Backup-Ziel"
REM ====================================================================
set "EXE=%~dp0..\Rechnungstool-Beka.exe"
set "ZIEL=%~1"
if "%ZIEL%"=="" set "ZIEL=%PROGRAMDATA%\RechnungstoolBeKa\backups"

if not exist "%EXE%" (
  echo FEHLER: Rechnungstool-Beka.exe nicht gefunden neben dem deploy-Ordner.
  pause & exit /b 1
)
"%EXE%" --backup "%ZIEL%"
echo.
echo Sicherung abgelegt in: %ZIEL%
pause
