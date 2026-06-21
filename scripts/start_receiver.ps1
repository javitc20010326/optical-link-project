$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")
$Receiver = Join-Path $Root "receiver"
$Venv = Join-Path $Receiver ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Requirements = Join-Path $Receiver "requirements.txt"
$DepsStamp = Join-Path $Venv ".deps-installed"

if (!(Test-Path $Venv)) {
    python -m venv $Venv
}

$NeedsInstall = !(Test-Path $DepsStamp)
if (!$NeedsInstall -and (Test-Path $Requirements)) {
    $NeedsInstall = (Get-Item $Requirements).LastWriteTimeUtc -gt (Get-Item $DepsStamp).LastWriteTimeUtc
}
if ($NeedsInstall) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r $Requirements
    Set-Content -Path $DepsStamp -Value (Get-Date).ToString("o")
}

& $Python (Join-Path $Receiver "app.py")
