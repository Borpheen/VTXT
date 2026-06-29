#define MyAppName "VTXT"
#define MyAppVersion "3.0.1"
#define MyAppPublisher "VTX-LordBust"
#define MyAppExeName "VTXT.exe"

[Setup]
AppId={{B8D7A3B2-6C5B-4F2A-9A4A-8D1F30000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VTXT
DefaultGroupName=Vertex
DisableProgramGroupPage=yes
OutputDir=E:\vtx\Vertex timer\vertex_timer_v3.0\Installer
OutputBaseFilename=VTXT_Setup_v3.0.1
SetupIconFile=E:\vtx\Vertex timer\vertex_timer_v3.0\Packaged\vtxt.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "E:\vtx\Vertex timer\vertex_timer_v3.0\Packaged\dist\VTXT.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VTXT"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\VTXT"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch VTXT"; Flags: nowait postinstall skipifsilent
