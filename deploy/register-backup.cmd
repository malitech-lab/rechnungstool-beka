@echo off
REM ====================================================================
REM  Registriert die taegliche, automatische Datensicherung (Task Scheduler).
REM  Aufruf als ADMINISTRATOR:
REM     register-backup.cmd "C:\Pfad\Rechnungstool-Beka.exe" "Z:\Backup-Ziel"
REM  Die App sichert WAL-konsistent in ein datiertes ZIP (siehe app\backup.py).
REM ====================================================================
schtasks /Create /TN "RechnungstoolBeKa-Backup" ^
  /TR "\"%~1\" --backup \"%~2\"" ^
  /SC DAILY /ST 20:00 /RL LIMITED /F

echo.
echo Taegliche Sicherung um 20:00 Uhr eingerichtet -^> %~2
