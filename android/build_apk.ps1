$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Comando fallido ($LASTEXITCODE): $FilePath $Arguments"
    }
}

$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$App = Join-Path $Project "app"
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

$JavaBin = $env:JAVA_HOME
if ($JavaBin) { $JavaBin = Join-Path $JavaBin "bin" }
if (!$JavaBin -or !(Test-Path (Join-Path $JavaBin "javac.exe"))) {
    $Javac = Get-Command javac.exe -ErrorAction SilentlyContinue
    if ($Javac) {
        $JavaBin = Split-Path -Parent $Javac.Source
    }
}
if (!$JavaBin -or !(Test-Path (Join-Path $JavaBin "javac.exe"))) {
    $JavaCandidates = @(
        "$env:ProgramFiles\Android\Android Studio\jbr\bin",
        "${env:ProgramFiles(x86)}\Android\Android Studio\jbr\bin",
        "$env:ProgramFiles\Android\Android Studio\jre\bin",
        "$env:ProgramFiles\Eclipse Adoptium",
        "$env:ProgramFiles\Microsoft\jdk",
        "$env:ProgramFiles\Amazon Corretto",
        "$env:USERPROFILE\.jdks"
    )
    foreach ($JavaCandidate in $JavaCandidates) {
        if ($JavaCandidate -and (Test-Path (Join-Path $JavaCandidate "javac.exe"))) {
            $JavaBin = $JavaCandidate
            break
        }
        if ($JavaCandidate -and (Test-Path $JavaCandidate)) {
            $FoundJavac = Get-ChildItem -Path $JavaCandidate -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($FoundJavac) {
                $JavaBin = Split-Path -Parent $FoundJavac.FullName
                break
            }
        }
    }
}
if (!$JavaBin -or !(Test-Path (Join-Path $JavaBin "javac.exe"))) {
    foreach ($JavaSearchRoot in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($JavaSearchRoot -and (Test-Path $JavaSearchRoot)) {
            $FoundJavac = Get-ChildItem -Path $JavaSearchRoot -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($FoundJavac) {
                $JavaBin = Split-Path -Parent $FoundJavac.FullName
                break
            }
        }
    }
}
if (!$JavaBin -or !(Test-Path (Join-Path $JavaBin "javac.exe"))) {
    throw "No encuentro javac.exe. Instala JDK o define JAVA_HOME."
}
$env:JAVA_HOME = Split-Path -Parent $JavaBin
$env:PATH = "$JavaBin;$env:PATH"

$BuildTools = Join-Path $Sdk "build-tools\35.0.0"
if (!(Test-Path $BuildTools)) { $BuildTools = Join-Path $Sdk "build-tools\34.0.0" }
$AndroidJar = Join-Path $Sdk "platforms\android-35\android.jar"
if (!(Test-Path $AndroidJar)) { throw "No encuentro android.jar en $Sdk\platforms\android-35" }

$Build = Join-Path $Project "build"
$Generated = Join-Path $Build "generated"
$Classes = Join-Path $Build "classes"
$Dex = Join-Path $Build "dex"
$Dist = Join-Path $Project "dist"
New-Item -ItemType Directory -Force $Generated, $Classes, $Dex, $Dist | Out-Null
Remove-Item -Recurse -Force $Generated, $Classes, $Dex -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Generated, $Classes, $Dex | Out-Null

$Manifest = Join-Path $App "src\main\AndroidManifest.xml"
$Unsigned = Join-Path $Build "unsigned.apk"
$Aligned = Join-Path $Build "aligned.apk"
$Signed = Join-Path $Dist "OpticalLink-debug.apk"
$Keystore = Join-Path $Project "debug.keystore"
$ClassesJar = Join-Path $Build "classes.jar"

$AaptArgs = @(
    "link",
    "--manifest", $Manifest,
    "-I", $AndroidJar,
    "--java", $Generated,
    "--min-sdk-version", "23",
    "--target-sdk-version", "35",
    "--debug-mode",
    "-o", $Unsigned
)
Invoke-Checked -FilePath (Join-Path $BuildTools "aapt2.exe") -Arguments $AaptArgs

$SourcesFile = Join-Path $Build "sources.txt"
Get-ChildItem -Path (Join-Path $App "src\main\java") -Recurse -Filter *.java | ForEach-Object { $_.FullName } | Set-Content $SourcesFile
Get-ChildItem -Path $Generated -Recurse -Filter *.java | ForEach-Object { $_.FullName } | Add-Content $SourcesFile

$JavacArgs = @("-encoding", "UTF-8", "-source", "1.8", "-target", "1.8", "-bootclasspath", $AndroidJar, "-d", $Classes, "@$SourcesFile")
Invoke-Checked -FilePath (Join-Path $JavaBin "javac.exe") -Arguments $JavacArgs

$ClassJarArgs = @("cf", $ClassesJar, "-C", $Classes, ".")
Invoke-Checked -FilePath (Join-Path $JavaBin "jar.exe") -Arguments $ClassJarArgs

$D8Args = @("--release", "--lib", $AndroidJar, "--output", $Dex, $ClassesJar)
Invoke-Checked -FilePath (Join-Path $BuildTools "d8.bat") -Arguments $D8Args
$JarArgs = @("uf", $Unsigned, "-C", $Dex, "classes.dex")
Invoke-Checked -FilePath (Join-Path $JavaBin "jar.exe") -Arguments $JarArgs

$ZipalignArgs = @("-f", "4", $Unsigned, $Aligned)
Invoke-Checked -FilePath (Join-Path $BuildTools "zipalign.exe") -Arguments $ZipalignArgs

if (!(Test-Path $Keystore)) {
    $KeytoolArgs = @(
        "-genkeypair", "-v",
        "-keystore", $Keystore,
        "-storepass", "android",
        "-alias", "androiddebugkey",
        "-keypass", "android",
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-dname", "CN=Android Debug,O=Codex,C=ES"
    )
    Invoke-Checked -FilePath (Join-Path $JavaBin "keytool.exe") -Arguments $KeytoolArgs
}

$SignArgs = @("sign", "--ks", $Keystore, "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", $Signed, $Aligned)
Invoke-Checked -FilePath (Join-Path $BuildTools "apksigner.bat") -Arguments $SignArgs

$VerifyArgs = @("verify", $Signed)
Invoke-Checked -FilePath (Join-Path $BuildTools "apksigner.bat") -Arguments $VerifyArgs
Write-Host "APK creada: $Signed"
