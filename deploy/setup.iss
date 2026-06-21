; ====================================================================
;  Inno Setup Script - Rechnungstool Montageservice Beka
;
;  Erst-Installation: legt die EXE nach Program Files, haertet den Datenordner
;  in ProgramData und richtet die taegliche Sicherung ein (fragt einmalig nach
;  Alltags-Konto + Sicherungsziel).
;
;  UPDATE (gleiche Setup.exe einfach drueberlaufen lassen): erkennt die vorhandene
;  Installation, macht ZUERST automatisch eine Sicherung, schliesst die laufende
;  App und tauscht nur die EXE aus. Die Daten in ProgramData bleiben unberuehrt und
;  migrieren beim Start selbst. KEINE erneute Konto-/Haertungs-Abfrage.
;
;  Voraussetzung: dist\Rechnungstool-Beka.exe wurde zuvor gebaut
;     pyinstaller build_windows.spec --noconfirm
;  Dann:  ISCC.exe deploy\setup.iss   (danach EXE + Setup.exe signieren!)
; ====================================================================

#define AppName "Rechnungstool Montageservice Beka"
#define AppShort "RechnungstoolBeKa"
#define AppVer "1.0.0"
#define ExeName "Rechnungstool-Beka.exe"

[Setup]
AppId={{B7E4C0A2-9D31-4F8E-A6B5-2C7D8E9F0A1B}
AppName={#AppName}
AppVersion={#AppVer}
VersionInfoVersion={#AppVer}.0
AppPublisher=malitech solutions
DefaultDirName={autopf}\{#AppShort}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputBaseFilename={#AppShort}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Wir schliessen die laufende App selbst (PrepareToInstall) -> keinen Neustart erzwingen
CloseApplications=no

[Files]
Source: "..\dist\{#ExeName}";   DestDir: "{app}";        Flags: ignoreversion
Source: "harden.cmd";           DestDir: "{app}\deploy"; Flags: ignoreversion
Source: "register-backup.cmd";  DestDir: "{app}\deploy"; Flags: ignoreversion
Source: "backup-jetzt.cmd";     DestDir: "{app}\deploy"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#ExeName}"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#ExeName}"

[Run]
; NUR bei Erst-Installation: Datenordner haerten + taegliche Sicherung registrieren.
Filename: "{app}\deploy\harden.cmd"; Parameters: """{code:GetAccount}"""; \
  Flags: runhidden waituntilterminated; StatusMsg: "Datenordner wird geschützt..."; \
  Check: IsFreshInstall
Filename: "{app}\deploy\register-backup.cmd"; \
  Parameters: """{app}\{#ExeName}"" ""{code:GetBackupDir}"""; \
  Flags: runhidden waituntilterminated; StatusMsg: "Tägliche Sicherung wird eingerichtet..."; \
  Check: IsFreshInstall
; Immer: optional direkt starten.
Filename: "{app}\{#ExeName}"; Description: "Rechnungstool jetzt starten"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks"; Parameters: "/Delete /TN ""RechnungstoolBeKa-Backup"" /F"; Flags: runhidden

; Datenordner C:\ProgramData\RechnungstoolBeKa wird beim Deinstallieren BEWUSST
; NICHT geloescht - GoBD-Aufbewahrungspflicht.

[Code]
var
  CfgPage: TInputQueryWizardPage;
  gUpgrade: Boolean;

function IsFreshInstall: Boolean;
begin
  Result := not gUpgrade;
end;

function InitializeSetup(): Boolean;
begin
  // Vorhandene Installation? -> Update-Modus (kein erneutes Einrichten).
  gUpgrade := FileExists(ExpandConstant('{autopf}\{#AppShort}\{#ExeName}'));
  Result := True;
end;

procedure InitializeWizard;
begin
  CfgPage := CreateInputQueryPage(wpSelectDir,
    'Einrichtung', 'Konto und Sicherungsziel',
    'Bitte das Windows-Konto angeben, das im Alltag mit dem Rechnungstool ' +
    'arbeitet, sowie den Zielordner fuer die taegliche Datensicherung ' +
    '(idealerweise ein ZWEITES Laufwerk: USB / NAS / Cloud-Ordner).');
  CfgPage.Add('Alltags-Windows-Konto:', False);
  CfgPage.Add('Sicherungs-Zielordner:', False);
  CfgPage.Values[0] := GetUserNameString();
  CfgPage.Values[1] := ExpandConstant('{commonappdata}\{#AppShort}\backups');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // Beim Update die Einrichtungs-Seite ueberspringen.
  Result := (PageID = CfgPage.ID) and gUpgrade;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  rc: Integer;
begin
  Result := '';
  if gUpgrade then
  begin
    // 1) Sicherung des aktuellen Stands, BEVOR die neue Version etwas anfasst.
    Exec(ExpandConstant('{app}\{#ExeName}'),
         '--backup "' + ExpandConstant('{commonappdata}\{#AppShort}\backups') + '"',
         '', SW_HIDE, ewWaitUntilTerminated, rc);
    // 2) Laufende App schliessen, damit die EXE ersetzt werden kann.
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#ExeName} /F',
         '', SW_HIDE, ewWaitUntilTerminated, rc);
  end;
end;

function GetAccount(Param: String): String;
begin
  Result := CfgPage.Values[0];
end;

function GetBackupDir(Param: String): String;
begin
  Result := CfgPage.Values[1];
end;
