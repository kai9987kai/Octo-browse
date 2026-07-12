; Inno Setup script for OctoBrowse. build_inno.ps1 supplies MyAppVersion.

#ifndef MyAppVersion
  #define MyAppVersion "3.3"
#endif
#define MyAppName "OctoBrowse"
#define MyAppPublisher "OctoBrowse"
#define MyAppExeName "OctoBrowse.exe"
#define MyAppURL "https://github.com/kai9987kai/Octo-browse"

[Setup]
; Stable AppId ensures an upgrade replaces the previous installation.
AppId={{8F2C5A1B-3D74-4E9A-B6C2-1A7E9D4F50C3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=OctoBrowse-{#MyAppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\octobrowse.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0.0
VersionInfoProductVersion={#MyAppVersion}.0.0
VersionInfoProductName={#MyAppName}
VersionInfoDescription=OctoBrowse Windows installer
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (c) 2026 OctoBrowse contributors
CloseApplications=force
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove old frozen-runtime payload so renamed dependencies cannot survive an upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\OctoBrowse\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
