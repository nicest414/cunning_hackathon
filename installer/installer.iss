[Setup]
AppName=Input Monitor
AppVersion=1.0.0
DefaultDirName={autopf}\InputMonitor
DefaultGroupName=Input Monitor
OutputDir=..\dist
OutputBaseFilename=InputMonitor_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\InputMonitor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Input Monitor"; Filename: "{app}\InputMonitor.exe"
Name: "{commondesktop}\Input Monitor"; Filename: "{app}\InputMonitor.exe"

[Run]
Filename: "{app}\InputMonitor.exe"; Description: "起動する"; Flags: nowait postinstall skipifsilent
