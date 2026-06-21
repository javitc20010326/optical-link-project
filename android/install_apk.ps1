$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Sdk = $env:ANDROID_SDK_ROOT
if (!$Sdk) { $Sdk = $env:ANDROID_HOME }
if (!$Sdk) {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Android\Sdk"),
        (Join-Path $env:USERPROFILE "AppData\Local\Android\Sdk"),
        "C:\Android\Sdk"
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            $Sdk = $Candidate
            break
        }
    }
}
if (!$Sdk) {
    $CodexRoot = Join-Path $env:USERPROFILE "Documents\Codex"
    if (Test-Path $CodexRoot) {
        $CodexSdk = Get-ChildItem -Path $CodexRoot -Recurse -Directory -Filter "android-sdk" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like "*\tools\android-sdk" } |
            Select-Object -First 1
        if ($CodexSdk) { $Sdk = $CodexSdk.FullName }
    }
}
if (!$Sdk -or !(Test-Path $Sdk)) {
    throw "No encuentro Android SDK. Define ANDROID_HOME o ANDROID_SDK_ROOT."
}

$Adb = Join-Path $Sdk "platform-tools\adb.exe"
if (!(Test-Path $Adb)) {
    throw "No encuentro adb.exe en $Adb. Instala Android platform-tools."
}
$Apk = Join-Path $Project "dist\OpticalLink-debug.apk"
if (!(Test-Path $Apk)) {
    & (Join-Path $Project "build_apk.ps1")
}

& $Adb devices
& $Adb install -r $Apk
