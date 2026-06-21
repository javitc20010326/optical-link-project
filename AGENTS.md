# Agent Guide

This repository is intended to be usable by local coding agents such as Codex and Claude Code.

## Goal

Optical Link is an experimental Android-to-PC optical transfer system. The Android app transmits data through screen light, flashlight, or infrared. The Windows receiver uses a webcam, OpenCV, and a local web UI.

## Main Entry Points

- Receiver: `receiver/app.py`
- Web UI: `receiver/static/`
- Android app: `android/app/src/main/java/com/codex/opticallink/MainActivity.java`
- Protocol helpers: `receiver/protocol.py`
- APK artifact for manual install: `downloads/android/OpticalLink-debug.apk`
- Human troubleshooting: `docs/TROUBLESHOOTING.md`
- Optional Windows tool bootstrap: `bootstrap_windows_dev.bat` / `scripts/bootstrap_windows_dev.ps1`

## External Tool Requirements

For receiver-only use:

- Windows 10/11
- Python 3.10+
- webcam

For Android rebuilds:

- JDK with `javac`, `jar`, and `keytool`
- Android SDK platform 35
- Android build-tools 35.0.0 or 34.0.0
- Android platform-tools if installing over USB

Do not assume these tools are present on a fresh clone. Verify and install them when the user asks for a full rebuild.

## Local Run

Double-click launcher for humans:

```text
launch_optical_link.bat
```

Create desktop shortcut:

```text
create_desktop_shortcut.bat
```

Start receiver:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_receiver.ps1
```

Open:

```text
http://127.0.0.1:8000
```

Build APK:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\build_apk.ps1
```

Install APK over USB:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\install_apk.ps1
```

Prepare a fresh Windows development machine when `winget` is available:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows_dev.ps1
```

If acting as Codex, Claude Code, or another local AI coding agent, a suitable user prompt is:

```text
Read AGENTS.md and docs/TROUBLESHOOTING.md. Prepare this Windows machine for Optical Link development: install or verify Python 3.10+, Git, JDK, Android SDK/platform-tools/build-tools, then run the receiver and rebuild the APK.
```

## Current Stable Receiver Path

The stable screen-grid path is `Centro rapido`:

- the receiver samples a fixed centered rectangle;
- the user manually aligns the phone grid inside the green box;
- automatic full-frame search is intentionally disabled because it caused low FPS and unstable crops.

Do not re-enable expensive full-frame grid search unless it is isolated behind a clearly optional mode and benchmarked.

## Verification

Before committing receiver changes:

```powershell
.\receiver\.venv\Scripts\python.exe -m py_compile .\receiver\app.py
```

Then start the receiver and confirm `/api/status` reports `tracking_mode=center` and normal webcam FPS.

Before committing Android changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\android\build_apk.ps1
```

Copy the built APK to `downloads/android/OpticalLink-debug.apk` if it should be published for manual download.

## Publication Checklist

- `README.md` explains human setup and agent setup.
- `downloads/android/OpticalLink-debug.apk` exists for manual Android install.
- `launch_optical_link.bat` starts the receiver with double click.
- `create_desktop_shortcut.bat` creates a user-specific desktop shortcut after clone.
- `bootstrap_windows_dev.bat` documents and automates common Windows dev tool setup.
- `receiver/.venv/`, `android/build/`, `android/dist/`, and `receiver/server.pid` are not tracked.
- `git status --short --ignored` contains no unexpected untracked public files.

## Do Not Commit

- `receiver/.venv/`
- `receiver/server.pid`
- `android/build/`
- `android/dist/`
- `outputs/`
- local debug captures
- private tokens or credentials
