; RemoteMouse.iss — Inno Setup script for RemoteMouse-Setup.exe
;
; Build (from the `pc` folder, after building dist\RemoteMouse.exe):
;     "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\RemoteMouse.iss
; Output: dist\RemoteMouse-Setup.exe
;
; What it does:
;  * Installs for the CURRENT USER only — no administrator prompt — into
;    %LOCALAPPDATA%\Programs\Remote Mouse
;  * Start-menu shortcut (+ optional desktop shortcut)
;  * Optional "start when I sign in" (the same per-user Run entry the tray
;    menu's "Start with Windows" uses)
;  * Clean uninstall from Settings → Apps. Your pairing settings in
;    %APPDATA%\RemoteMouse are kept, so reinstalling doesn't break your phone.

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{6D0B7C3E-5B7A-4C2F-9E0D-2A4C1B8F7E51}
AppName=Remote Mouse
AppVersion={#AppVersion}
AppVerName=Remote Mouse {#AppVersion}
AppPublisher=ColterPan
AppPublisherURL=https://github.com/ColterPan/remote-mouse
AppSupportURL=https://github.com/ColterPan/remote-mouse/issues
DefaultDirName={localappdata}\Programs\Remote Mouse
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=RemoteMouse-Setup
SetupIconFile=..\assets\remote_mouse.ico
UninstallDisplayIcon={app}\RemoteMouse.exe
UninstallDisplayName=Remote Mouse
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start Remote Mouse when I sign in to Windows (recommended)"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\RemoteMouse.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Remote Mouse"; Filename: "{app}\RemoteMouse.exe"
Name: "{autodesktop}\Remote Mouse"; Filename: "{app}\RemoteMouse.exe"; Tasks: desktopicon

[Registry]
; Autostart, if chosen. Matches the command autostart.py writes.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "RemoteMouse"; ValueData: """{app}\RemoteMouse.exe"" --background"; Tasks: autostart
; Always remove the autostart entry on uninstall (even if it was turned on
; later from the tray menu).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "RemoteMouse"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\RemoteMouse.exe"; Description: "Start Remote Mouse now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Quit the running app first so its file can be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM RemoteMouse.exe"; Flags: runhidden; RunOnceId: "StopRemoteMouse"

[Code]
// After uninstalling, offer to also delete the pairing data (pairing code,
// certificate + private key, logs) in %APPDATA%\RemoteMouse. Kept by default
// so a reinstall keeps working with your phone. Silent uninstalls keep it.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\RemoteMouse');
    if DirExists(DataDir) and not UninstallSilent() then
      if MsgBox('Also delete your Remote Mouse pairing data?' + #13#10#13#10 +
                'Choose Yes if you are not planning to reinstall. Your phones will ' +
                'need to scan a new QR code if you install Remote Mouse again.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
