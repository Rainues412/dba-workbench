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

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDirectory: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;

  DataDirectory := ExpandConstant('{localappdata}\DBA Workbench');
  if DirExists(DataDirectory) and
     (SuppressibleMsgBox(
       '是否同时删除 DBA 工作台的全部应用数据？' + #13#10 + #13#10 +
       '选择“是”将永久删除数据库、密码保险箱恢复密钥、日志和目录授权配置。' + #13#10 +
       '选择“否”将保留数据，以便重新安装后继续使用。',
       mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES) then
  begin
    if not DelTree(DataDirectory, True, True, True) then
      MsgBox('应用数据未能完全删除，请手动检查：' + DataDirectory, mbError, MB_OK);
  end;
end;
