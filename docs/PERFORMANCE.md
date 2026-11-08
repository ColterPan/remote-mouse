# Performance: how smooth is it?

v1.1 focused on making the pointer and scrolling feel smoother. This page records what was measured and what changed.

## Causes of lag found in v1.0

| # | Cause | Where | Fix in v1.1 |
|---|---|---|---|
| 1 | Moves were held until the next screen frame, on top of `pointermove` already being frame-aligned (adds 1–2 frames) | `touchpad.js` | Send immediately, merged to at most one message per 8 ms. Use `pointerrawupdate` and `getCoalescedEvents()` |
| 2 | Pointer speed came from single noisy samples, so the acceleration gain jumped around | `gestures.js` | Time-aware moving average (τ = 24 ms) and a smooth acceleration curve |
| 3 | Phone Wi-Fi power saving bunches packets into bursts | phone OS | App holds `WIFI_MODE_FULL_LOW_LATENCY` while on screen (`LowLatencyWifi.kt`) |
| 4 | Nagle's algorithm can delay tiny packets | phone TCP | App sockets use `TCP_NODELAY` (`PinnedSocket.kt`). aiohttp already sets it on the PC |
| 5 | Small scroll amounts were truncated and lost; scrolling stopped dead on finger lift | `input_controller.py`, `touchpad.js` | Lossless wheel-unit accumulator, plus momentum scrolling |

The PC side was already fast: pynput's `SetCursorPos` takes well under 1 ms.

## Benchmark: touch → PC latency

`pc/tools/touch_latency_bench.py` drives a headless phone-sized Chrome against the real server and injects a scripted 60-sample swipe (8 ms apart) as genuine touch events. A recording controller timestamps every move the PC performs. Each figure is the median of 5 runs.

| Phone UI | Moves delivered | Lag p50 | Lag p95 |
|---|---|---|---|
| v1.0.0 | 60 / 60 | 21.7 ms | 34.3 ms |
| **v1.1** | 60 / 60 | **11.2 ms** | **19.1 ms** |

Both the median and the 95th-percentile delay **roughly halved**. The ~50 ms "max gap" in the raw output is the same for both versions; it comes from the test driver (Python → Chrome DevTools round-trips), not the app.

Reproduce:

```powershell
cd pc
python tools\touch_latency_bench.py                       # current UI
git archive v1.0.0 pc/remote_mouse/web | tar -x -C old     # old UI
python tools\touch_latency_bench.py --web old\pc\remote_mouse\web
```

## Automated smoothness checks (run in CI)

- `e2e/test_phone_remote.py::test_swipe_moves_pointer_smoothly`: every touch sample produces a move, the median touch→PC lag stays under 15 ms, and a horizontal swipe stays perfectly horizontal.
- `e2e/test_phone_remote.py::test_two_finger_scroll_then_momentum`: scrolling continues after the fingers lift, and never moves the pointer.
- `web-tests/gestures.test.mjs`: the acceleration curve never decreases and has no jumps, and one noisy sample can't spike the speed.
- `web-tests/momentum_native.test.mjs`: momentum covers the same distance at 60 Hz and 120 Hz, and stops by itself.

## Real phone

See [UAT.md](UAT.md) for the hands-on results on a real Android phone over Wi-Fi.
