; ORION Windows installer (Inno Setup 6). Build with scripts\build.ps1, which runs PyInstaller first.
; Installs per user (no admin prompt), adds Start-menu and optional login entries, and uninstalls cleanly.
; The 354 MB Kokoro voice is not bundled: ORION downloads it in the background on first start.

#define AppName "ORION"
#define AppVersion "2.1.0"
#define AppExe "ORION.exe"

[Setup]
AppId={{6C3E2E57-6F55-4F0B-9C77-0B7E52B7A1D4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=ORION-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}

[Tasks]
Name: "autostart"; Description: "Start {#AppName} when I sign in"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\ORION\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value name the service itself uses (service/autostart.py), so either can remove it.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "StopOrion"

[UninstallDelete]
; Settings, history, and the license stay in %LOCALAPPDATA%\ORION unless the person deletes them.
Type: filesandordirs; Name: "{app}"
