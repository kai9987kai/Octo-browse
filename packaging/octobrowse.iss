; Inno Setup script for OctoBrowse.
; Build with packaging\build_inno.ps1 (which passes /DMyAppVersion).
; Packages the PyInstaller onedir output (dist\OctoBrowse) into a proper
; installer with Start Menu / optional desktop shortcuts, an uninstaller, and
; an Add/Remove Programs entry. Installs per-user (no admin prompt).

#ifndef MyAppVersion
  #define MyAppVersion "3.2"
#endif
#define MyAppName "OctoBrowse"
#define MyAppPublisher "OctoBrowse"
#define MyAppExeName "OctoBrowse.exe"
#define MyAppURL "https://github.com/kai9987kai/Octo-browse"

[Setup]
; Stable AppId so upgrades replace prior installs instead of stacking.
AppId={{8F2C5A1B-3D74-4E9A-B6C2-1A7E9D4F50C3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=OctoBrowse-{#MyAppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\OctoBrowse\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
