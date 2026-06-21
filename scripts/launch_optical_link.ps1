$ErrorActionPreference = "SilentlyContinue"

$Root = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")
$Receiver = Join-Path $Root "receiver"
$PidFile = Join-Path $Receiver "server.pid"
$Python = Join-Path $Receiver ".venv\Scripts\python.exe"
$App = Join-Path $Receiver "app.py"
$Url = "http://127.0.0.1:8000"
$Requirements = Join-Path $Receiver "requirements.txt"
$DepsStamp = Join-Path $Receiver ".venv\.deps-installed"

function Test-Server {
    try {
        $response = Invoke-WebRequest -UseBasicParsing "$Url/api/status" -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-Path $Python)) {
    python -m venv (Join-Path $Receiver ".venv")
}

if (Test-Path $Python) {
    $NeedsInstall = !(Test-Path $DepsStamp)
    if (!$NeedsInstall -and (Test-Path $Requirements)) {
        $NeedsInstall = (Get-Item $Requirements).LastWriteTimeUtc -gt (Get-Item $DepsStamp).LastWriteTimeUtc
    }
    if ($NeedsInstall) {
        & $Python -m pip install --upgrade pip
        & $Python -m pip install -r $Requirements
        Set-Content -Path $DepsStamp -Value (Get-Date).ToString("o")
    }
}

if (-not (Test-Server)) {
    if (Test-Path $PidFile) {
        $oldPid = Get-Content $PidFile
        if ($oldPid) {
            Stop-Process -Id ([int]$oldPid) -Force
        }
    }
    $proc = Start-Process -FilePath $Python -ArgumentList @($App) -WorkingDirectory $Receiver -WindowStyle Hidden -PassThru
    Set-Content -Path $PidFile -Value $proc.Id
    Start-Sleep -Seconds 2
}

Start-Process $Url
