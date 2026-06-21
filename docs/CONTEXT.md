# Project Context

Optical Link is an experimental phone-to-PC optical communication bridge.

The current implementation was built and tested on Windows with a Xiaomi Redmi phone and a laptop webcam. The design goal is emergency fallback communication when ordinary short-range links are unavailable: no Wi-Fi, Bluetooth, USB cable, pendrive, or similar channel.

## Current Architecture

- Android transmitter: native Java APK compiled with Android SDK command line tools.
- PC receiver: Python + OpenCV + local HTTP server.
- Web UI: static HTML/CSS/JavaScript served by the receiver.
- Windows launchers: `launch_optical_link.bat` starts the receiver, `create_desktop_shortcut.bat` creates a local desktop shortcut.
- Windows setup helper: `bootstrap_windows_dev.bat` checks/installs common dev tools with `winget` where possible.
- Primary path: phone screen emits a color grid; PC webcam receives and decodes it.
- Secondary slow paths: flashlight pulses and infrared pulses.

## Current Screen Protocol

- Magic: `OC`
- Version: `3`
- Frame fields: flags, tx id, sequence, total, chunk length, original length, reserved byte, payload chunk, CRC16.
- Compression: zlib is used when it reduces payload size.
- Grid is configurable. Default is 25 columns x 50 rows.
- The stable APK uses 8 high-contrast colors/data symbols for 3 bits/cell.

## Practical Notes

The most important receiver assumption is tracking:

- `Centro rapido`: assumes the user places the phone/grid in the middle of the webcam view. It avoids expensive full-frame search and keeps FPS high.
- Full-frame automatic search is currently disabled in the stable path because it caused low FPS and bad crops on ordinary webcams.

Dense grids are sensitive to:

- webcam focus and exposure;
- moire patterns;
- black gaps between cells;
- phone brightness;
- perspective and crop alignment.

The latest APK removed black gaps between grid cells and makes the grid occupy more screen area.

Do not commit machine-specific `.lnk` files. Desktop shortcuts are generated locally after clone because Windows shortcut files contain absolute paths.

## Roadmap

- Add a true OFDM visual mode with temporal frequency bins per screen zone.
- Add audio/microphone transmission.
- Add stronger forward error correction.
- Add optional adaptive ROI locking with user-visible confidence, only if it keeps high FPS.
- Add packaged releases for Windows and Android.
