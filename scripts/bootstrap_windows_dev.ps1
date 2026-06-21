$ErrorActionPreference = "Stop"

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-WithWinget {
    param(
        [string]$Id,
        [string]$Name
    )
    if (!(Test-Command winget)) {
        Write-Host "winget no esta disponible. Instala manualmente: $Name" -ForegroundColor Yellow
        return
    }
    Write-Host "Instalando/verificando $Name..." -ForegroundColor Cyan
    winget install --id $Id --exact --accept-source-agreements --accept-package-agreements
}

Write-Host "Optical Link Windows developer bootstrap" -ForegroundColor Green
Write-Host "Este script prepara herramientas para recompilar Android y ejecutar el receptor."
Write-Host ""

if (!(Test-Command git)) {
    Install-WithWinget -Id "Git.Git" -Name "Git for Windows"
}

if (!(Test-Command python)) {
    Install-WithWinget -Id "Python.Python.3.12" -Name "Python 3.12"
}

if (!(Test-Command javac)) {
    Install-WithWinget -Id "EclipseAdoptium.Temurin.17.JDK" -Name "Temurin JDK 17"
}

$AndroidHome = $env:ANDROID_HOME
if (!$AndroidHome) { $AndroidHome = $env:ANDROID_SDK_ROOT }
if (!$AndroidHome -or !(Test-Path $AndroidHome)) {
    Install-WithWinget -Id "Google.AndroidStudio" -Name "Android Studio"
    Write-Host ""
    Write-Host "Abre Android Studio una vez e instala desde SDK Manager:" -ForegroundColor Yellow
    Write-Host "- Android SDK Platform 35"
    Write-Host "- Android SDK Build-Tools 35.0.0 o 34.0.0"
    Write-Host "- Android SDK Platform-Tools"
    Write-Host "Despues define ANDROID_HOME o ANDROID_SDK_ROOT si el script no detecta el SDK."
}

Write-Host ""
Write-Host "Comprobacion rapida:" -ForegroundColor Green
foreach ($Command in @("git", "python", "javac")) {
    if (Test-Command $Command) {
        Write-Host "OK $Command"
    } else {
        Write-Host "FALTA $Command" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Agentes IA:" -ForegroundColor Green
Write-Host "- Usa tu agente local preferido, por ejemplo Codex o Claude Code."
Write-Host "- Abre este repo y pidele: lee AGENTS.md, prepara Python/JDK/Android SDK, ejecuta el receptor, compila la APK y verifica."
Write-Host "- Consulta siempre las instrucciones oficiales del agente que vayas a instalar; no guardes tokens en el repo."
