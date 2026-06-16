; Inno Setup script for DFP TakeoffPro
; Download Inno Setup free from: https://jrsoftware.org/isinfo.php
; Then open this file in Inno Setup and click Build > Compile

#define MyAppName "DFP TakeoffPro"
#define MyAppVersion "1.0.5"
#define MyAppPublisher "Defense Fire Protection"
#define MyAppURL "https://defensefirepro.com"
#define MyAppExeName "DFP TakeoffPro.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
; Uncomment the next line to add a license agreement file:
; LicenseFile=LICENSE.txt
OutputDir=installer_output
OutputBaseFilename=DFP_TakeoffPro_Setup_{#MyAppVersion}
; Replace with your icon file once you have one:
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
WizardImageFile=
PrivilegesRequired=admin

; Visual appearance
WizardImageStretch=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Include everything PyInstaller put in dist/DFP TakeoffPro/
Source: "dist\DFP TakeoffPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";       Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Do NOT delete user data in AppData on uninstall (preserve their projects)
; If you want to offer data cleanup, add a custom page to the uninstaller
