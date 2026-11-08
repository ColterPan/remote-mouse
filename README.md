# 🖱️ Remote Mouse

**Use your phone as your PC's mouse and keyboard over Wi-Fi.**
Free, open source, **no ads, no accounts, no cloud**. Your phone talks
directly to your PC over your own network, encrypted.

[![CI](https://github.com/ColterPan/remote-mouse/actions/workflows/ci.yml/badge.svg)](https://github.com/ColterPan/remote-mouse/actions/workflows/ci.yml)

| Touchpad | Keyboard | Extras |
|---|---|---|
| Move, tap to click, 2-finger right-click, 2-finger scroll, double-tap-and-drag, scroll strip | Type with your phone keyboard (any language and emoji), Esc/Tab/arrows/F1–F12, sticky Ctrl/Alt/Shift/Win | Copy/Paste/Undo/Alt+Tab/Win+D shortcuts, volume and media keys, drag lock, keeps your screen on |

---

## Quick start (3 steps)

**1. On your PC:** download **[RemoteMouse.exe](https://github.com/ColterPan/remote-mouse/releases/latest/download/RemoteMouse.exe)** and run it.
- Windows SmartScreen may say *"Windows protected your PC"*, because the app isn't code-signed (signing certificates cost money). Click **More info → Run anyway**. You can [verify the download](#verify-your-download) first.
- When Windows Firewall asks, tick **Private networks** only and click **Allow**.
- A window with a QR code appears. Remote Mouse now lives in the system tray (near the clock; click **^** if you don't see it).

**2. On your phone:** connect to the **same Wi-Fi** as the PC, then open the camera and scan the QR code.
- Chrome shows *"Your connection is not private"*. This is expected the first time: the PC uses its own certificate rather than one bought from a company. Tap **Advanced → Proceed to 192.168.x.x**. Your connection *is* encrypted.

**3. Add it to your home screen:** in Chrome, tap **⋮ → Add to Home screen**. From now on, one tap opens your remote.

> 💡 Tray icon → **Start with Windows** keeps Remote Mouse always ready after every reboot.

---

## How to use it

| Gesture / button | Does |
|---|---|
| Slide one finger | Move the pointer (fast swipes travel further) |
| Tap | Left click (tap twice = double-click) |
| Two-finger tap | Right click |
| Three-finger tap | Middle click |
| Two-finger slide | Scroll (up/down and sideways) |
| Tap, then touch again and slide | Drag (e.g. move a window or select text) |
| Right-hand strip | One-finger scrolling |
| **Left / • / Right** buttons | Hold a button and move with another finger to drag |
| 🔒 button | Drag lock: keeps the left button held until you tap it again |
| **Keyboard** | Opens your phone keyboard; everything you type goes to the PC |
| **Keys** | Esc, Tab, Del, Home/End, PgUp/PgDn, arrows, F1–F12 |
| **Ctrl / Alt / Shift / Win** | Tap to "arm", then tap or type a key → e.g. Ctrl + C |
| **Shortcuts** | Copy, Paste, Cut, Undo, Redo, Save, Find, Alt+Tab, Win+D, Task Manager… |
| **Media** | Volume up/down/mute, play/pause, next/previous |
| ⚙ Settings | Pointer speed, scroll speed, natural scrolling, vibration, keep screen on |

### Tray menu (on the PC)

- **Show pairing QR code:** pair another phone, or pick a different network address.
- **Start with Windows:** start silently in the tray when you log in.
- **Reset pairing…:** makes a new secret code and disconnects every phone. Use it if you lose a phone.
- **Quit**

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Phone says *"PC not reachable"* | Is the phone on the **same Wi-Fi**? (Guest networks often block devices from seeing each other.) Is Remote Mouse running (tray icon)? Did you allow it in the firewall? Check **Windows Security → Firewall → Allow an app**: *Remote Mouse* should be ticked for **Private**. Make sure your Wi-Fi is set to *Private* in Windows network settings. |
| QR code doesn't work / wrong address | In the QR window, choose another **Network address**. VPNs, Hyper-V and WSL add extra adapters. |
| PC's IP address changed (new router, DHCP) | Show the QR code again and re-scan. Your pairing code stays the same. |
| *"Not paired"* on the phone | The pairing was reset on the PC. Scan the new QR code. |
| *"Too many wrong attempts"* | Wait 60 seconds. |
| Pointer doesn't move over Task Manager / admin apps | Windows blocks normal apps from controlling admin windows. That's a Windows security feature. |
| Antivirus flags RemoteMouse.exe | A false positive that's common for Python-built exes. [Verify the checksum](#verify-your-download), or [run from source](#run-from-source). |
| Port 8765 already in use | Edit `%APPDATA%\RemoteMouse\config.json` and change `"port"`. |
| Logs | `%APPDATA%\RemoteMouse\remote_mouse.log` |

### Verify your download

On the [Releases page](https://github.com/ColterPan/remote-mouse/releases), open `SHA256SUMS.txt`, then in PowerShell run:

```powershell
Get-FileHash .\RemoteMouse.exe -Algorithm SHA256
```

The hash must match.

---

## Security in one minute

- Only devices on **your local network** can connect. Internet addresses are refused.
- A phone needs the **secret pairing code** from your QR code (128-bit random), and 5 wrong guesses block that device for a minute.
- Everything is **encrypted** (HTTPS / TLS 1.2+), so nobody else on the Wi-Fi can read your typing.
- No ads, no tracking, no accounts, no outbound connections. Read every line yourself.

Details: [SECURITY.md](SECURITY.md).

---

## Run from source

Requires [Python 3.11+](https://www.python.org/downloads/) on Windows.

```powershell
git clone https://github.com/ColterPan/remote-mouse.git
cd remote-mouse\pc
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m remote_mouse            # starts the app (add --background to hide the QR window)
```

| Task | Command (inside `pc/`) |
|---|---|
| Run all Python tests with coverage | `pytest --cov` |
| Run phone-remote tests | `node --test "web-tests/*.test.mjs"` |
| Lint and format | `ruff check .` and `ruff format .` |
| Security scans | `bandit -c pyproject.toml -r remote_mouse` and `pip-audit -r requirements.txt` |
| Build the exe | `pyinstaller remote_mouse.spec --clean --noconfirm` → `dist\RemoteMouse.exe` |
| Regenerate icons | `python tools\make_icons.py` |

**Tip:** while editing the phone page, just reload it on your phone. The PC serves the files straight from `pc/remote_mouse/web/`.

### Publishing a new version

```powershell
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions runs all checks, builds `RemoteMouse.exe`, and attaches it with checksums to a new Release. The download link in this README always points at the latest one.

---

## How it works

```
Phone (Chrome)                      Wi-Fi, encrypted              PC (RemoteMouse.exe)
touchpad / keyboard  ──── JSON over WebSocket (wss://) ────►  server.py  → security.py
  gestures.js                {"t":"move","dx":12,"dy":-3}             → protocol.py
  keyboard.js                {"t":"click","b":"right"}                → input_controller.py
  connection.js              {"t":"key","k":"c","mods":["ctrl"]}       → Windows SendInput
```

1. The PC app runs a small HTTPS server on port 8765 that serves the remote web page and a WebSocket endpoint.
2. Scanning the QR code opens that page with the secret token in the link (after `#`, which is never sent over the network). The page saves the token and removes it from the address bar.
3. The page connects to the WebSocket and sends the token first. The PC checks it.
4. Your gestures are turned into tiny JSON messages (batched to at most 60 per second). The PC validates each one and performs it with real mouse/keyboard input.

Every source file starts with a comment explaining what it does and how it fits in. Good places to start:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): map of every file and thread
- [docs/PROTOCOL.md](docs/PROTOCOL.md): every message the phone can send
- [docs/PLANNING.md](docs/PLANNING.md): options considered and why each choice was made

### Repository layout

```
remote-mouse/
├── README.md, SECURITY.md, LICENSE
├── docs/                       ARCHITECTURE, PROTOCOL, PLANNING
├── pc/                         ← the Windows app
│   ├── remote_mouse/           Python package (server, security, input, tray…)
│   │   └── web/                the phone remote (HTML, CSS, JS, icons)
│   ├── tests/                  pytest suite
│   ├── web-tests/              node tests for the phone remote's logic
│   ├── tools/make_icons.py     draws the app icon
│   ├── remote_mouse.spec       PyInstaller build recipe
│   └── requirements*.txt       pinned dependencies
└── .github/                    CI, release and Dependabot config
```

---

## Adding a feature (example: a "lock PC" message)

1. **Protocol:** in `pc/remote_mouse/protocol.py`, add a `@dataclass(frozen=True) class Lock` and a `_parse_lock` function, and register `"lock"` in `_PARSERS`.
2. **Action:** in `input_controller.py`, add `lock()` to `InputController`, `PynputController` and `FakeController`, plus a `case Lock():` in `execute()`.
3. **Phone:** add a button in `web/index.html` and send `{ t: 'lock' }` from `web/js/app.js`.
4. **Tests and docs:** add tests in `pc/tests/` (run `pytest`), and document the message in `docs/PROTOCOL.md`.

CI checks everything automatically when you push.

---

## Roadmap

- [x] **Phase 1:** Wi-Fi remote (PC app + phone web remote), tests, CI, releases
- [ ] **Phase 2:** Android app with **Bluetooth** mode (the phone becomes a real Bluetooth mouse and keyboard, no PC software needed, works at the login screen) and Wi-Fi mode without the certificate warning

## License

[MIT](LICENSE): free to use, change and share.
