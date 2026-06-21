# Android APK Download

This folder contains the current debug APK for manual Android installation:

```text
OpticalLink-debug.apk
```

For normal development, rebuild it from source:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\build_apk.ps1
```

For USB installation with Android debugging enabled:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\install_apk.ps1
```

This APK is a debug build for field testing. It is not signed as a Play Store release.
