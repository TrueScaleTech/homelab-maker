; Inno Setup script for HomeLabMaker.
;
; Built by packaging\build-windows.ps1, which passes the version, the folder PyInstaller
; produced and where to put the result:
;   ISCC /DAppVersion=0.1.0 /DSourceDir=...\HomeLabMaker /DOutDir=... /DIconFile=... windows-installer.iss
;
; The installer asks for no administrator rights: by default it installs for the current
; user only, which is what the application's own promise ("no elevated privileges") needs.

#ifndef AppVersion
  #error AppVersion is not set
#endif
#ifndef SourceDir
  #error SourceDir is not set
#endif
#ifndef OutDir
  #define OutDir "."
#endif
#ifndef IconFile
  #error IconFile is not set
#endif

[Setup]
; A fixed id, so that a newer installer upgrades an older install instead of adding a second.
AppId={{6C2D7A4E-3B1F-4F6E-9C57-2E8A5D0B7F31}
AppName=HomeLabMaker
AppVersion={#AppVersion}
AppVerName=HomeLabMaker {#AppVersion}
AppPublisher=TrueScaleTech
AppPublisherURL=https://github.com/TrueScaleTech/homelab-maker
AppSupportURL=https://github.com/TrueScaleTech/homelab-maker/issues
DefaultDirName={autopf}\HomeLabMaker
DefaultGroupName=HomeLabMaker
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir={#OutDir}
OutputBaseFilename=HomeLabMaker-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\HomeLabMaker.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\HomeLabMaker"; Filename: "{app}\HomeLabMaker.exe"
Name: "{autodesktop}\HomeLabMaker"; Filename: "{app}\HomeLabMaker.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HomeLabMaker.exe"; Description: "Start HomeLabMaker"; Flags: nowait postinstall skipifsilent
