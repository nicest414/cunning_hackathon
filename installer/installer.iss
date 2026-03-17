[Setup]
AppName=CunningApp
AppVersion=1.0.0
DefaultDirName={autopf}\CunningApp
DefaultGroupName=CunningApp
OutputDir=..\dist
OutputBaseFilename=CunningApp_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\CunningApp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CunningApp"; Filename: "{app}\CunningApp.exe"
Name: "{commondesktop}\CunningApp"; Filename: "{app}\CunningApp.exe"

[Run]
Filename: "{app}\CunningApp.exe"; Description: "起動する"; Flags: nowait postinstall skipifsilent
