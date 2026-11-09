# User acceptance testing

## v1.1.1: phone keyboard fix + "Get the phone app" QR

**Bug reported:** opening the phone keyboard in the app messed up the touchpad size.

**Reproduced on v1.1.0, Android 15 emulator, real on-screen keyboard:**
- The app was not resized and the keyboard covered the controls. Android 15 ignores `adjustResize` for apps targeting SDK 35.
- The key row stretched the layout to 632 px on a 412 px screen, pushing the Right button and toolbar off-screen.
- After closing the keyboard the touchpad stayed the wrong size.
- On smaller phones the keyboard made the visible area wider than tall, so CSS switched to the *landscape* layout and squashed the touchpad to 18 px wide.

**Fixes:**
- The native side handles the keyboard and system-bar insets itself (`MainActivity.fitAboveBarsAndKeyboard`).
- The page sizes itself to the visible area and never scrolls (`viewport.js`).
- A compact layout is used while the keyboard is open.
- Landscape is now judged on the full screen size.
- Long rows scroll instead of widening the page.

| # | Check (real taps, real Gboard, real PC app) | Android 15 | Android 14 |
|---|---|---|---|
| K1 | Keyboard open: touchpad big (336×310 css px), Left/Right, key row and toolbar all above the keyboard | ✅ | ✅ |
| K2 | App window ends exactly at the keyboard's top edge | ✅ (1517 = 1517 px) | ✅ (1499 = 1499 px) |
| K3 | Swipe with the keyboard open reaches the PC cursor losslessly | ✅ 404→405, 403→402 px | ⚠️ not measured: the PC's mouse was in use during the run |
| K4 | Back button hides the keyboard → full-size touchpad again, keyboard panel closed | ✅ | ✅ |
| K5 | 10 keyboard open/close toggles in a row, layout correct every time | ✅ | ✅ |
| K6 | Landscape, and landscape with the keyboard: touchpad visible and usable | ✅ | ✅ |
| K7 | Still connected at the end | ✅ | ✅ |

**Automated:**
- 6 new browser E2E tests in `e2e/test_keyboard_layout.py`: big phone, tall keyboard, small 360×640 phone, landscape, 5 rapid toggles, typing in compact mode.
- 8 new unit tests in `web-tests/viewport.test.mjs`.
- 3 tests in `tests/test_qr_window.py`.

**Get the phone app QR:**
- The tray menu item and the pairing-window button show a QR code for `releases/latest/download/RemoteMouse.apk`.
- An independent QR reader (zxing-cpp) decodes the window and the README image to exactly that URL.
- The URL returns HTTP 200 with `application/vnd.android.package-archive`.

---

# v1.1.0

Every check below was run against **real software**, not mocks: the real PC app (installed with the real installer), the real Android app on a real Android 14 system (emulator, Pixel 7 profile), and the real phone UI in mobile Chrome. Only the automated browser tests swap the final mouse/keyboard injection for a recorder.

## 1. Android app on Android 14 (emulator) ↔ real PC app

Driven over adb against the PC app installed from `RemoteMouse-Setup.exe`.

| # | User story | Result | Evidence |
|---|---|---|---|
| A1 | Fresh install opens **"Add your PC"** | ✅ | page state read from the app's WebView |
| A2 | Pairing (QR link) connects over the **pinned** connection | ✅ | PC log "Phone connected", app shows the PC name |
| A3 | Swiping the touchpad moves the **real Windows cursor**, losslessly | ✅ | 3 swipes: phone sent 345 / 353 / 352 px, PC cursor moved 345 / 353 / 352 px |
| A4 | **Force-stop and relaunch → connects automatically, no QR** | ✅ | PC log shows a new connection, pairing screen not shown |
| A5 | Saved address broken → app shows "Searching…" then "Can't reach … Retry" (no hang) | ✅ | states seen: connecting → searching → offline |
| A6 | Re-pairing restores the connection | ✅ | PC log |
| A7 | **Release APK ignores debug test hooks** (a hostile app can't pair it silently) | ✅ | debug pairing intent sent to the release build: no connection |
| A8 | On-device instrumented tests (`FirstLaunchTest`, 2 tests) | ✅ | `gradlew connectedDebugAndroidTest` |
| A9 | PC address changed → app **re-finds it via mDNS** | ⏳ real phone | The emulator's virtual network doesn't carry multicast from the real LAN, so this needs a physical phone. The PC side is verified in B4. |

**Bug found and fixed by this UAT:** the first swipe after the page loaded lost ~80% of its distance (62 px instead of ~345 px). Android WebView dropped some move events in the first gesture, and the touchpad ignored the lift-off position. The touchpad now applies the lift-off position as a final move (`touchpad.js`). Re-test: lossless (A3).

## 2. PC app (installer, real Windows)

| # | User story | Result | Evidence |
|---|---|---|---|
| B1 | Silent install, no admin prompt, into `%LOCALAPPDATA%\Programs\Remote Mouse` | ✅ | exit code 0 |
| B2 | Start-menu and desktop shortcuts, "start with Windows" entry, Settings → Apps entry | ✅ | file and registry checks |
| B3 | Installed app serves the phone UI over HTTPS, accepts the token, refuses wrong tokens (locked out on the 6th try), moves the real cursor | ✅ | smoke test: cursor moved exactly 40 px; 5 × unauthorized, then HTTP 429 |
| B4 | Installed app **announces itself** on the network; a real mDNS browse finds it with the right fingerprint; **no token and no PC name** in the announcement | ✅ | TXT keys `fp`, `v` only; fingerprint matches `cert.pem` |
| B5 | Request via the PC's Wi-Fi address works; a DNS-rebinding `Host` is refused | ✅ | 200 / 403 |
| B6 | Pairing window shows the new logo and the app-first instructions | ✅ | screenshot |

## 3. Phone UI in mobile Chrome (automated, 19 tests, run in CI)

`pc/e2e/test_phone_remote.py`, Pixel-7-sized Chrome with real multi-touch:

- **Connecting:** connects and shows the PC name; a wrong token leads to the pairing screen; it reconnects by itself after a PC restart; the offline banner offers **Retry**.
- **Touchpad:** tap → left click; two-finger tap → right click; swipe → smooth, continuous moves with median touch→PC lag under 15 ms; two-finger scroll plus momentum; momentum can be turned off; tap-and-drag holds the left button with no stray click; holding the Left button.
- **Keyboard:** typing plus Enter; shortcut and media buttons; sticky Ctrl + typed letter.
- **Settings:** speed preset remembered; tips shown only once.
- **App mode:**
  - First launch → scan → connected, then **relaunch auto-connects**.
  - The token never appears in the page.
  - The "Your PCs" list works.
  - Forgetting the current PC leads to the PC list.

## 4. Automated suites

| Suite | Result |
|---|---|
| Python unit tests (`pc/tests`) | all pass, **96.5 % coverage** |
| Phone UI logic (`pc/web-tests`, node) | 36 / 36 |
| E2E user tests (`pc/e2e`) | 19 / 19 |
| Android unit tests (incl. real-TLS pinning: accepts the paired PC, rejects an impostor) | 16 / 16 |
| Android instrumented (on device) | 2 / 2 |
| ruff, bandit, pip-audit, Android lint | clean |
| Independent code review + security review | all findings fixed (1 HIGH, 4 MEDIUM, 13 LOW) |

## 5. Smoothness

See [PERFORMANCE.md](PERFORMANCE.md). Touch→PC latency median dropped from 21.7 ms to 11.2 ms, and p95 from 34.3 ms to 19.1 ms. Movement is lossless end to end (A3).

## Still to do on a real phone

- A9: rediscovery after a real IP change (mDNS on real Wi-Fi).
- A feel check of smoothness with the low-latency Wi-Fi lock on real hardware.
- The camera QR scan (the emulator has no real camera; pairing used the same code path via the debug hook).
