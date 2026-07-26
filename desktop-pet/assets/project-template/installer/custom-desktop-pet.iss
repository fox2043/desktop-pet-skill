#define MyAppName "我的桌面宠物"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "自定义桌面宠物"
#define MyAppExeName "我的桌面宠物.exe"

[Setup]
AppId={{E5BAEB3D-CFA2-433D-9CC2-70FC0B5D651A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\我的桌面宠物
DefaultGroupName=我的桌面宠物
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsedUserAreasWarning=no
OutputDir=..\release
OutputBaseFilename=自定义桌面宠物安装程序-v{#MyAppVersion}
SetupIconFile=..\assets\pet.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=2.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=我的桌面宠物安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: checkedonce
Name: "startup"; Description: "开机后自动启动我的桌面宠物"; GroupDescription: "附加选项："

[Files]
Source: "..\dist\我的桌面宠物.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "使用说明.md"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\我的桌面宠物"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\我的桌面宠物"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\我的桌面宠物"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "安装完成后创建我的桌面宠物"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopCustomPet;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'),
    '/F /IM "{#MyAppExeName}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopCustomPet;
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopCustomPet;
end;
