# User acceptance testing: v1.1.0

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
