# Architecture

```
 PHONE                                                     PC: Remote Mouse (tray app)
 ┌────────────────────────────────────────────┐           ┌─────────────────────────────────────────┐
 │ Android app                                │           │ server.py  (aiohttp, background thread) │
 │  MainActivity: WebView + bundled web UI    │  TLS 1.2+ │   GET /, /static/*  → web UI (browser)  │
 │  NativeBridge ⇄ page (origin-restricted)   │  pinned   │   /ws → security.py → protocol.py        │
 │  RemoteSession → PinnedSocket (OkHttp)     │ ────────► │            → input_controller.py         │
 │  PcDiscovery (mDNS)  LowLatencyWifi        │ ◄──mDNS── │ discovery.py (announces fingerprint)     │
 │  PcStore (saved PCs, app-private)          │           │ tray.py + qr_window.py (main thread)    │
 ├────────────────────────────────────────────┤           │ config.py, tls.py, netinfo.py,          │
 │ …or any phone browser (same web UI)        │ ────────► │ autostart.py, __main__.py               │
 └────────────────────────────────────────────┘           └─────────────────────────────────────────┘
```

**One UI, two hosts.** `pc/remote_mouse/web/` is served by the PC to browsers, and copied into the Android APK at build time (`copyWebAssets` in `android/app/build.gradle.kts`). In the app, `native.js` swaps the browser WebSocket for the native bridge.

## PC modules (`pc/remote_mouse/`)

| File | Responsibility | Tested by |
|---|---|---|
| `__main__.py` | Start-up: single instance, logging, config, cert, server, discovery, tray | manual + installer UAT |
| `config.py` | `config.json` (token, port): load, repair, atomic save | `test_config.py` |
| `security.py` | Private-IP allow-list, Host check, constant-time token check, lockout | `test_security.py` |
| `protocol.py` | Parse and validate every message into typed, immutable commands | `test_protocol.py` |
| `input_controller.py` | Commands → pynput; sub-pixel movement and lossless wheel accumulation | `test_input_controller.py` |
| `server.py` | HTTPS/WebSocket server, auth handshake, connection caps, background thread | `test_server.py`, `e2e/` |
| `discovery.py` | mDNS announcement (`_remotemouse._tcp`: version, fingerprint, name; never the token) | `test_discovery.py` |
| `tls.py` | Self-signed certificate creation, reuse and renewal | `test_tls.py` |
| `netinfo.py` | LAN IP discovery; pairing URL | `test_netinfo.py` |
| `autostart.py` | "Start with Windows" (HKCU Run key) | `test_autostart.py` |
| `tray.py`, `qr_window.py` | Tray icon and menu; pairing window | manual checklist |

## Web UI (`pc/remote_mouse/web/js/`)

| File | Responsibility | Tested by |
|---|---|---|
| `app.js` | Wires everything; browser vs app mode; PCs screen; banner; settings | `e2e/` |
| `connection.js` | Auth, ping/pong, dead-link detection, reconnect backoff | `e2e/`, `helpers.test.mjs` |
| `native.js` | App mode: `NativeSocket` imitates WebSocket over the native bridge | `momentum_native.test.mjs`, `e2e/` (mock bridge) |
| `gestures.js` | **Pure** gesture state machine: taps, drag, scroll, fling, smoothed acceleration | `gestures.test.mjs` |
| `momentum.js` | **Pure** momentum-scroll physics | `momentum_native.test.mjs` |
| `touchpad.js` | Pointer events → gestures → throttled messages; momentum loop | `e2e/` |
| `keyboard.js`, `textdiff.js` | Soft-keyboard typing via text diffs, special keys, sticky modifiers | `helpers.test.mjs`, `e2e/` |
| `settings.js` | Validated preferences (+ browser-mode token) in localStorage | `helpers.test.mjs` |

## Android app (`android/app/src/main/java/io/github/colterpan/remotemouse/`)

| File | Responsibility | Tested by |
|---|---|---|
| `MainActivity.kt` | WebView host, asset loader, bridge registration, Wi-Fi lock, QR scanner, debug-only test hooks | `FirstLaunchTest` (on device) |
| `NativeBridge.kt` | JSON messages between page and native; never sends tokens to the page | on-device UAT |
| `RemoteSession.kt` | Connect to the saved address → rediscover by fingerprint → reconnect | on-device UAT |
| `PinnedSocket.kt` | OkHttp WebSocket, TCP_NODELAY, sends the token after TLS is verified | `PinningTest` |
| `FingerprintTrustManager.kt` | Accepts only the paired PC's certificate (SHA-256) | `PinningTest`, `FingerprintTrustManagerTest` |
| `PairingLink.kt` | Strict QR link parser | `PairingLinkTest` |
| `PcStore.kt` | Saved PCs in app-private storage (no backups) | `PcCodecTest` |
| `PcDiscovery.kt` | NSD browse/resolve, match by fingerprint | on-device UAT |
| `LowLatencyWifi.kt` | Low-latency Wi-Fi lock while on screen | on-device UAT |

## Threads

- **PC:** tkinter on the main thread (with a 100 ms task queue), a pystray thread, an asyncio server thread, and a zeroconf refresh thread. Shared state is `AuthState` (locked) and the queue.
- **Android:** the UI thread (WebView, bridge replies), OkHttp threads (socket events), and NSD callbacks. `RemoteSession` tags each attempt with a connection id (`cid`) and ignores stale events. Replies to the page are always posted to the main thread.

## Design principles

- **One validation choke point** (`protocol.parse_message`) and one UI codebase.
- **Immutable data:** frozen dataclasses, frozen JS settings, Kotlin data classes.
- **Dependency injection for testability:** controller, clock, registry and Zeroconf are swappable, so tests never move your mouse or touch your registry.
- **No build step for the UI, no CDNs.** What's in the repo is exactly what runs.
