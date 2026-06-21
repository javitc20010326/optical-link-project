# Troubleshooting

## Receiver Does Not Start

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_receiver.ps1
```

If Python is not found, install Python 3.10+ and make sure `python` is available in PATH.

If OpenCV installation fails, upgrade pip manually:

```powershell
.\receiver\.venv\Scripts\python.exe -m pip install --upgrade pip
.\receiver\.venv\Scripts\python.exe -m pip install -r .\receiver\requirements.txt
```

## Browser Opens But Camera Is Black

- Close Teams, Zoom, browser tabs, or any app using the webcam.
- Press `Reset` in the receiver UI.
- Try camera index `1`, then `2`, and press `Aplicar`.
- Restart the receiver.

## FPS Is Very Low

- Use `Centro rapido`.
- Keep the phone grid centered in the green rectangle.
- Close other camera applications.
- Prefer the default `25 x 50` grid before testing denser grids.
- Use `200 ms` or `300 ms` per frame until decoding is stable.

## Screen Grid Is Detected But No Text Arrives

- Make sure Android and receiver use the same columns and rows.
- Align the colored grid itself, not the whole phone, inside the green rectangle.
- Increase phone brightness.
- Avoid strong reflections on the phone screen.
- Start with short text such as `hola`.

## Android APK Install Fails

Manual install:

```text
downloads/android/OpticalLink-debug.apk
```

Android may require enabling install from unknown sources.

USB install:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\install_apk.ps1
```

If ADB shows no devices:

- enable Developer Options;
- enable USB debugging;
- reconnect the cable;
- accept the RSA prompt on the phone;
- run `adb devices`.

## Build APK Fails

The build script expects:

- Android SDK with platform `android-35`;
- Android build-tools `35.0.0` or `34.0.0`;
- JDK with `javac`, `jar`, and `keytool`.

On Windows, first try:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_dev.ps1
```

That script can install/check Git, Python, JDK, and Android Studio through `winget` when available. After Android Studio is installed, open SDK Manager once and install:

- Android SDK Platform 35;
- Android SDK Build-Tools 35.0.0 or 34.0.0;
- Android SDK Platform-Tools.

Set these variables if auto-detection fails:

```powershell
$env:ANDROID_HOME="C:\Path\To\Android\Sdk"
$env:JAVA_HOME="C:\Path\To\JDK"
```

If you are using a local AI coding agent, ask it to verify these tools and then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\build_apk.ps1
```
