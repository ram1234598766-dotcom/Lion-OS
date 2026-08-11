; Lion-OS Desktop installer (Inno Setup)
; Produces LionOS-Desktop-Setup.exe from the Rust launcher binary `lionos.exe`.
; Compile:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" LionOS-Desktop.iss
; Requires a release `lionos.exe` on the `[Files]` Source path.

#define MyAppName "Lion-OS Desktop"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Mrityunjay"
#define MyAppExeName "lionos.exe"
#define MyAppURL "https://github.com/ram1234598766-dotcom/Lion-OS"

[Setup]
AppId={{9A4C1E2F-7B3D-4E5A-9C6F-2D8E4F6A0B1C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; User-scope install: no admin/UAC required, per-user PATH + shortcuts.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\LionOS
DisableDirPage=yes
; Single-file, signed-style modern window.
OutputDir=.
OutputBaseFilename=LionOS-Desktop-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "addtopath"; Description: "Add Lion-OS to your &PATH"; GroupDescription: "Additional icons:"

[Files]
Source: "stage\lionos.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Per-user PATH entry so `lionos` works in any terminal after install.
Root: HKCU; Subkey: "Environment"; ValueName: "PATH"; \
  ValueType: expandsz; \
  ValueData: "{olddata};{app}"; \
  Check: NeedsAddPath('{app}') and WizardIsTaskSelected('addtopath')

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "setup"; \
  Description: "Open the LionOS installation manager (auto-configures + package picker)"; \
  Flags: nowait postinstall skipifsilent

[Code]
// Only add to PATH if not already present (and the segment is not empty).
function NeedsAddPath(Param: string): Boolean;
var
  Path: string;
  Segments: TArrayOfString;
  i: Integer;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'PATH', Path) then
  begin
    Result := True;
    Exit;
  end;
  Result := True;
  // Split on ';' (single-char separator).
  SetArrayLength(Segments, 0);
  i := 0;
  while Path <> '' do
  begin
    if (Pos(';', Path) > 0) then
    begin
      SetArrayLength(Segments, i + 1);
      Segments[i] := Copy(Path, 1, Pos(';', Path) - 1);
      Path := Copy(Path, Pos(';', Path) + 1, Length(Path));
      Inc(i);
    end else
    begin
      SetArrayLength(Segments, i + 1);
      Segments[i] := Path;
      Path := '';
      Inc(i);
    end;
  end;
  for i := 0 to GetArrayLength(Segments) - 1 do
    if CompareText(Segments[i], Param) = 0 then
    begin
      Result := False; // already on PATH
      Exit;
    end;
end;