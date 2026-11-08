"""
touch_latency_bench.py — Measures how smoothly finger movement reaches the PC.

It runs a headless phone-sized Chrome against a real Remote Mouse server
(with a recording fake controller), injects a scripted one-finger swipe as
real touch events, and reports:

    moves     how many move messages reached the PC (more = finer motion)
    lag p50   median time from a touch sample to the PC performing it
    lag p95   95th percentile of that lag (spikes = perceived stutter)
    max gap   longest pause between moves during the swipe

Usage (from the pc folder):
    python tools/touch_latency_bench.py                 # current web UI
    python tools/touch_latency_bench.py --web <folder>  # e.g. an older version
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "e2e"))

from conftest import TOKEN, TimedList, Touch, center_of, new_phone_page  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from remote_mouse import server as server_module  # noqa: E402
from remote_mouse.input_controller import FakeController  # noqa: E402
from remote_mouse.server import AuthState, BackgroundServer, ServerContext  # noqa: E402
from remote_mouse.tls import create_ssl_context, ensure_certificate  # noqa: E402

STEPS = 60
FRAME_MS = 8
RUNS = 5


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def bench(web_dir: Path | None) -> dict[str, float]:
    if web_dir is not None:
        server_module.WEB_DIR = web_dir
    controller = FakeController()
    ctx = ServerContext(AuthState(TOKEN), controller, name="Bench-PC")
    with tempfile.TemporaryDirectory() as tmp:
        info = ensure_certificate(Path(tmp), ["localhost"], ["127.0.0.1"])
        srv = BackgroundServer(ctx, "127.0.0.1", 0, create_ssl_context(info))
        srv.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = new_phone_page(browser)
                page.goto(f"https://127.0.0.1:{srv.bound_port}/#t={TOKEN}&fp=x")
                page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
                results = {"moves": [], "lag50": [], "lag95": [], "gap": []}
                for _ in range(RUNS):
                    controller.calls = TimedList()
                    x, y = center_of(page, "#touchpad")
                    touch = Touch(page)
                    injected = touch.swipe(
                        [(x - 120, y)], [(x + 120, y)], steps=STEPS, frame_ms=FRAME_MS
                    )
                    touch.end()
                    time.sleep(0.3)
                    times = [
                        t
                        for c, t in zip(controller.calls, controller.calls.times, strict=True)
                        if c[0] == "move"
                    ]
                    lags = [
                        t - max(i for i in injected if i <= t)
                        for t in times
                        if any(i <= t for i in injected)
                    ]
                    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
                    results["moves"].append(len(times))
                    results["lag50"].append(statistics.median(lags) * 1000)
                    results["lag95"].append(percentile(lags, 95) * 1000)
                    results["gap"].append(max(gaps) * 1000 if gaps else 0)
                browser.close()
        finally:
            srv.stop()
    return {k: statistics.median(v) for k, v in results.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", type=Path, help="web UI folder to test (default: current)")
    args = parser.parse_args()
    r = bench(args.web)
    print(  # noqa: T201 (CLI tool output)
        f"moves={r['moves']:.0f}/{STEPS}  lag p50={r['lag50']:.1f} ms  "
        f"lag p95={r['lag95']:.1f} ms  max gap={r['gap']:.1f} ms"
    )


if __name__ == "__main__":
    main()
