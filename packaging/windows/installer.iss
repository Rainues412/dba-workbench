#ifndef SourceDir
  #error SourceDir must be supplied by the build script
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by the build script
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B446CC25-D12C-4A45-9826-A2AB6038A19E}
AppName=DBA 工作台
AppVersion={#AppVersion}
AppPublisher=DBA Workbench
DefaultDirName={localappdata}\Programs\DBA 工作台
DefaultGroupName=DBA 工作台
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=DBA工作台-安装程序-{#AppVersion}-x64
SetupIconFile=..\..\assets\dba-workbench-icon.ico
UninstallDisplayIcon={app}\DBA工作台.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dynamic
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DBA 工作台"; Filename: "{app}\DBA工作台.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\DBA 工作台"; Filename: "{app}\DBA工作台.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DBA工作台.exe"; Description: "启动 DBA 工作台"; Flags: nowait postinstall skipifsilent
