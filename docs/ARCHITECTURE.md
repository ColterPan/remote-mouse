# Architecture

```
 PHONE (Chrome on Android, "Add to Home screen")        PC (RemoteMouse.exe, system tray)
 ┌──────────────────────────────────────┐              ┌─────────────────────────────────────────┐
 │ index.html + styles.css              │   HTTPS      │ server.py  (aiohttp, background thread) │
 │ js/app.js ── wires everything        │ ◄──────────► │   GET /, /static/*  → web files         │
 │ js/touchpad.js ─► js/gestures.js     │   WSS /ws    │   /ws → security.py → protocol.py        │
 │ js/keyboard.js ─► js/textdiff.js     │   JSON msgs  │            → input_controller.py         │
 │ js/connection.js (auto-reconnect)    │              │                 → pynput → Windows input │
 │ js/settings.js (localStorage)        │              │                                         │
 └──────────────────────────────────────┘              │ tray.py + qr_window.py (main thread)    │
                                                       │ config.py, tls.py, netinfo.py,          │
                                                       │ autostart.py, __main__.py               │
                                                       └─────────────────────────────────────────┘
```

## PC modules (`pc/remote_mouse/`)

| File | Responsibility | Tested by |
|---|---|---|
| `__main__.py` | Start-up: single-instance check, logging, config, cert, server, tray | manual checklist |
| `config.py` | `config.json` (token, port): load, repair, atomic save | `test_config.py` |
| `security.py` | Private-IP allow-list, constant-time token check, lockout | `test_security.py` |
| `protocol.py` | Parse and validate every network message into typed, immutable commands | `test_protocol.py` |
| `input_controller.py` | Commands → pynput; sub-pixel accumulation; fake controller for tests | `test_input_controller.py` |
| `server.py` | HTTPS/WebSocket server, auth handshake, security headers, background thread | `test_server.py` |
| `tls.py` | Self-signed certificate creation, reuse and renewal; SSL context | `test_tls.py` |
| `netinfo.py` | LAN IP discovery; pairing URL | `test_netinfo.py` |
| `autostart.py` | "Start with Windows" (HKCU Run key) | `test_autostart.py` |
| `tray.py` | Tray icon and menu; thread-safe task queue to the GUI thread | manual checklist |
| `qr_window.py` | Pairing window with the QR code | manual checklist |

## Threads on the PC

- **Main thread:** runs tkinter (the QR window and dialogs). It checks a queue every 100 ms for work posted by the tray.
- **pystray thread:** runs the Windows tray message loop. Menu clicks put tasks on the queue.
- **Server thread:** runs its own asyncio event loop with aiohttp. Input is injected directly from here (SendInput is thread-agnostic).

Shared state between threads is limited to `AuthState`, which is protected by a lock, and the queue.

## Phone modules (`pc/remote_mouse/web/js/`)

| File | Responsibility | Tested by |
|---|---|---|
| `app.js` | Bootstraps everything: pairing token, panels, settings dialog, wake lock, lifecycle | manual checklist |
| `connection.js` | WebSocket, auth, ping/pong, reconnect backoff, status | `helpers.test.mjs` (backoff) |
| `gestures.js` | **Pure** gesture state machine: taps, scroll, drag, acceleration | `gestures.test.mjs` |
| `touchpad.js` | Pointer events → gestures → batched messages (one per frame) | manual checklist |
| `textdiff.js` | **Pure** diff of the hidden input → backspaces and inserted text | `helpers.test.mjs` |
| `keyboard.js` | Soft keyboard, special keys, sticky modifiers, shortcuts, media | manual checklist |
| `settings.js` | Preferences and token in localStorage, validated | `helpers.test.mjs` |

## Design principles

- **One validation choke point.** Raw network data is only ever touched by `protocol.parse_message`.
- **Immutable data.** Commands and `Config` are frozen dataclasses, and JS settings are frozen objects.
- **Dependency injection for testability.** The controller, clock and registry can all be swapped in tests, so tests never move your real mouse or edit your real registry.
- **No build step, no CDN.** The phone page is plain ES modules, so what's in the repo is exactly what runs.
