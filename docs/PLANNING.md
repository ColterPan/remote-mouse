# Planning and decision record

This file records **what options were considered at each stage, which was
chosen, and why**. If you want to change direction later, start here.
✅ = chosen.

## Requirements

- Control a Windows PC from an Android phone: move, left/right/middle click, scroll, drag, typing, special keys and shortcuts.
- Connects over **Wi-Fi** (phase 1) and **Bluetooth** (phase 2).
- Free, open source, **no ads, no accounts, no cloud**.
- Easy to install from a link: the GitHub Releases page.
- Safe by default: nobody else on the network can take control.
- Readable, well-commented code that's easy to extend.

## Decisions

### 1. PC language

| Option | Pros | Cons |
|---|---|---|
| ✅ **Python** | Easiest to read and extend; huge ecosystem; already installed | Unsigned PyInstaller exes sometimes get antivirus false positives; ~24 MB exe |
| Go | Tiny single exe, few false positives | More verbose; input/tray libraries less mature |
| C# / .NET | Most Windows-native | Windows-only skills; needs the .NET SDK |

**Mitigation for the Python downside:** build only in GitHub Actions from public source, publish SHA-256 checksums, and don't use UPX compression.

### 2. Server library

| Option | Notes |
|---|---|
| ✅ **aiohttp** | One mature library serves both static files and WebSockets on one port |
| FastAPI + uvicorn | Great for REST APIs, but more moving parts than we need |
| `websockets` + `http.server` | Two servers / two ports to manage |

### 3. Input injection

| Option | Notes |
|---|---|
| ✅ **pynput** | Well-maintained; uses Windows `SendInput`; Unicode typing; media keys |
| ctypes `SendInput` by hand | Full control, but lots of low-level code to maintain |
| pyautogui | Built-in "fail-safe" corner and pauses get in the way of a remote |

### 4. Phone app

| Option | Notes |
|---|---|
| ✅ **Phase 1: web remote served by the PC** | Nothing to install (scan the QR, Add to Home screen); always matches the PC version; works on any phone |
| ✅ **Phase 2: native Android app (Kotlin)** | Needed for Bluetooth; pins the certificate so there's no browser warning |
| Flutter / React Native | Cross-platform, but the Bluetooth HID API is Android-native anyway |

### 5. Securing the connection

| Option | Notes |
|---|---|
| Plain HTTP | Simplest, but keystrokes (passwords!) readable by anyone on the Wi-Fi |
| ✅ **Self-signed HTTPS** | Encrypted. Cost: a one-time "not private" warning in Chrome |
| App-level encryption | Reinventing TLS: risky |

### 6. Pairing

| Option | Notes |
|---|---|
| None | Anyone on the Wi-Fi could control the PC |
| 6-digit PIN | Typeable, but only 1,000,000 combinations |
| ✅ **128-bit random token in a QR code** | Unguessable; scanning is easier than typing; resettable from the tray |

The token travels in the URL *fragment* (`#t=…`), which browsers never send over the network.

### 7. Packaging and distribution

| Option | Notes |
|---|---|
| ✅ **PyInstaller one-file exe on GitHub Releases** | One file to download and run; built by CI on version tags |
| Installer (Inno Setup / MSI) | Nicer uninstall, but more to maintain; can be added later |
| Microsoft Store | Needs a developer account; slow review |

### 8. Bluetooth (phase 2)

| Option | Notes |
|---|---|
| ✅ **Phone acts as a Bluetooth HID mouse and keyboard** (Android 9+ `BluetoothHidDevice`) | Windows sees a standard Bluetooth keyboard and mouse; no PC software needed; works at the login screen |
| Custom Bluetooth (RFCOMM) link to the PC app | Needs the PC app running and more pairing UX |

**Risk:** a few phone makers disable the HID profile. The README explains how to check.

## Phases

1. **Phase 1 (done):** PC app, web remote, tests, CI, releases.
2. **Phase 2:** Android app (Kotlin + Jetpack Compose) with Wi-Fi (pinned TLS) and Bluetooth HID modes; signed APK attached to releases.

Security follow-up (from the v1 security review): single-use, short-lived QR pairing codes exchanged for per-device keys, plus a "paired devices" list with individual revoke.

Ideas after that: a landing page on GitHub Pages, an installer, macOS/Linux support (`InputController` is already an interface), a trackpad "pinch to zoom" gesture, clipboard sync.
