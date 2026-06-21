@echo off
setlocal
REM ====================================================================
REM  Haertet den Datenordner  C:\ProgramData\RechnungstoolBeKa
REM  Aufruf als ADMINISTRATOR:   harden.cmd "Alltags-Kontoname"
REM  Ohne Parameter wird der aktuell angemeldete Benutzer genutzt.
REM
REM  Ergebnis: SYSTEM + Administratoren = Vollzugriff; das Alltags-Konto
REM  darf lesen/schreiben, aber im Belegarchiv NICHTS loeschen
REM  (GoBD-Schutz vor versehentlichem Loeschen).
REM ====================================================================
set "DATA=%PROGRAMDATA%\RechnungstoolBeKa"
set "ACCOUNT=%~1"
if "%ACCOUNT%"=="" set "ACCOUNT=%USERNAME%"

if not exist "%DATA%\belege" mkdir "%DATA%\belege"
if not exist "%DATA%\assets" mkdir "%DATA%\assets"

REM Vererbung kappen, dann gezielt Rechte setzen.
icacls "%DATA%" /inheritance:r
REM SYSTEM (S-1-5-18) + Administratoren (S-1-5-32-544) Vollzugriff - sprachneutral.
icacls "%DATA%" /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"
icacls "%DATA%" /setowner "*S-1-5-32-544" /T
REM Alltags-Konto = Aendern (Modify) auf dem gesamten Datenordner ...
icacls "%DATA%" /grant:r "%ACCOUNT%:(OI)(CI)M"
REM ... ABER Loeschsperre NUR auf dem Belegarchiv (NICHT auf den DB-Ordner,
REM sonst kollidiert es mit dem SQLite-WAL-Checkpoint).
icacls "%DATA%\belege" /grant:r "%ACCOUNT%:(OI)(CI)(RX,W,AD)"
icacls "%DATA%\belege" /deny  "%ACCOUNT%:(OI)(CI)(DE,DC)"

echo.
echo Fertig. Geschuetzter Datenordner: %DATA%
echo Alltags-Konto (Schreiben, kein Loeschen im Archiv): %ACCOUNT%
endlocal
