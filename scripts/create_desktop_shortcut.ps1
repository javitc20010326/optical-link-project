$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Launcher = Join-Path $Root "launch_optical_link.bat"
if (!(Test-Path $Launcher)) {
    throw "No encuentro launch_optical_link.bat en $Root"
}

$Desktop = [Environment]::GetFolderPath("Desktop")
if (!$Desktop -or !(Test-Path $Desktop)) {
    $Desktop = Join-Path $env:USERPROFILE "Desktop"
}
if (!(Test-Path $Desktop)) {
    New-Item -ItemType Directory -Force $Desktop | Out-Null
}

$ShortcutPath = Join-Path $Desktop "Optical Link Receiver.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Launcher
$Shortcut.WorkingDirectory = $Root
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$Shortcut.Description = "Start Optical Link receiver and open the local web UI"
$Shortcut.Save()

Write-Host "Acceso directo creado:" -ForegroundColor Green
Write-Host $ShortcutPath
