"""
E2E test harness — the REAL phone page in a REAL (headless) mobile Chrome,
talking to the REAL server over HTTPS/WebSocket. Only the final step is faked:
FakeController records input instead of moving your mouse.

Touches are injected through the Chrome DevTools Protocol, which produces
genuine multi-touch pointer events — the same events a phone generates.

Run:   pytest e2e        (from the pc folder; needs `playwright install chromium`)
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from remote_mouse.input_controller import FakeController
from remote_mouse.security import FailedAuthLimiter
from remote_mouse.server import AuthState, BackgroundServer, ServerContext
from remote_mouse.tls import create_ssl_context, ensure_certificate

TOKEN = "E2eTestTokenAbcdefghij"
DEMO_PC_NAME = "Demo-PC"
PHONE = {"width": 412, "height": 892}  # Pixel-7-like logical size


@dataclass
class Env:
    ctx: ServerContext
    server: BackgroundServer
    port: int
    cert_dir: Path

    @property
    def base(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    @property
    def calls(self) -> list[tuple]:
        return self.ctx.controller.calls  # type: ignore[attr-defined]

    def restart(self) -> None:
        """Stop and start the server on the same port (simulates a PC restart)."""
        self.server.stop()
        info = ensure_certificate(self.cert_dir, ["localhost"], ["127.0.0.1"])
        self.server = BackgroundServer(self.ctx, "127.0.0.1", self.port, create_ssl_context(info))
        self.server.start()


@pytest.fixture(scope="session")
def env(tmp_path_factory) -> Iterator[Env]:
    cert_dir = tmp_path_factory.mktemp("cert")
    info = ensure_certificate(cert_dir, ["localhost"], ["127.0.0.1"])
    ctx = ServerContext(
        auth=AuthState(TOKEN),
        controller=FakeController(),
        limiter=FailedAuthLimiter(max_failures=50),
        name=DEMO_PC_NAME,
    )
    server = BackgroundServer(ctx, "127.0.0.1", 0, create_ssl_context(info))
    server.start()
    environment = Env(ctx, server, server.bound_port or 0, cert_dir)
    yield environment
    environment.server.stop()


class TimedList(list):
    """A list that also remembers WHEN each item arrived (for smoothness checks)."""

    def __init__(self) -> None:
        super().__init__()
        self.times: list[float] = []

    def append(self, item) -> None:  # type: ignore[override]
        self.times.append(time.perf_counter())
        super().append(item)


@pytest.fixture(autouse=True)
def clean(env: Env) -> None:
    controller = FakeController()
    controller.calls = TimedList()
    env.ctx.controller = controller
    env.ctx.auth.rotate(TOKEN)


def mock_native_bridge(env: Env) -> str:
    """
    JavaScript that stands in for the Android app's native side
    (MainActivity + NativeBridge), implementing the same message protocol.
    "Saved PCs" persist in localStorage, so reloading the page = relaunching
    the app. Pairing ("scan") uses demo data — never a real IP or token.
    """
    return f"""
(() => {{
  const TOKEN = {TOKEN!r};
  const WS_URL = 'wss://127.0.0.1:{env.port}/ws';
  const load = () => JSON.parse(localStorage.getItem('__mockPcs') || '[]');
  const save = (pcs) => localStorage.setItem('__mockPcs', JSON.stringify(pcs));
  let ws = null;
  const bridge = {{ onmessage: null }};
  const emit = (o) => setTimeout(() => bridge.onmessage && bridge.onmessage({{ data: JSON.stringify(o) }}), 0);
  const sendPcs = () => emit({{ ev: 'pcs', pcs: load().map(({{ token, ...p }}) => p),
                                lastId: localStorage.getItem('__mockLast') }});
  bridge.postMessage = (text) => {{
    const m = JSON.parse(text);
    if (m.op === 'init') sendPcs();
    if (m.op === 'scan') {{
      const pc = {{ id: 'demo-fp', name: '192.168.1.20', host: '192.168.1.20', port: 8765, token: TOKEN }};
      save([...load().filter((p) => p.id !== pc.id), pc]);
      localStorage.setItem('__mockLast', pc.id);
      sendPcs();
      emit({{ ev: 'paired', id: pc.id }});
    }}
    if (m.op === 'connect') {{
      const cid = m.cid;
      localStorage.setItem('__mockLast', m.id);
      emit({{ ev: 'status', cid, state: 'connecting', name: 'PC' }});
      let opened = false;
      ws = new WebSocket(WS_URL);
      ws.onopen = () => ws.send(JSON.stringify({{ t: 'auth', token: TOKEN, v: 1 }}));
      ws.onmessage = (e) => {{
        const d = JSON.parse(e.data);
        if (d.t === 'hello' && !opened) {{
          opened = true;
          save(load().map((p) => (p.id === m.id ? {{ ...p, name: d.name }} : p)));
          sendPcs();
          emit({{ ev: 'open', cid, data: e.data }});
        }} else emit({{ ev: 'message', cid, data: e.data }});
      }};
      ws.onclose = (e) => emit({{ ev: 'close', cid, code: e.code }});
    }}
    if (m.op === 'send' && ws && ws.readyState === 1) ws.send(m.msg);
    if (m.op === 'disconnect' && ws) {{ ws.onclose = null; ws.close(); ws = null; }}
    if (m.op === 'forget') {{ save(load().filter((p) => p.id !== m.id)); sendPcs(); }}
  }};
  window.RemoteMouseNative = bridge;
}})();
"""


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        chromium = p.chromium.launch()
        yield chromium
        chromium.close()


def new_phone_page(
    browser: Browser,
    init_script: str | None = None,
    viewport: dict | None = None,
    scale: float = 2.625,
) -> Page:
    context = browser.new_context(
        viewport=viewport or PHONE,
        device_scale_factor=scale,
        is_mobile=True,
        has_touch=True,
        ignore_https_errors=True,  # the PC's self-signed certificate
        color_scheme="dark",
    )
    if init_script:
        context.add_init_script(init_script)
    return context.new_page()


@pytest.fixture
def phone(browser: Browser, env: Env) -> Iterator[Page]:
    page = new_phone_page(browser)
    page.goto(f"{env.base}/#t={TOKEN}&fp=x")
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    yield page
    page.context.close()


class Touch:
    """Multi-touch driver using the DevTools protocol."""

    def __init__(self, page: Page) -> None:
        self.cdp = page.context.new_cdp_session(page)
        self.page = page

    def _send(self, kind: str, points: list[tuple[float, float]]) -> None:
        self.cdp.send(
            "Input.dispatchTouchEvent",
            {
                "type": kind,
                "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(points)],
            },
        )

    def start(self, *points: tuple[float, float]) -> None:
        self._send("touchStart", list(points))

    def move(self, *points: tuple[float, float]) -> None:
        self._send("touchMove", list(points))

    def end(self) -> None:
        self._send("touchEnd", [])

    def tap(self, x: float, y: float) -> None:
        self.start((x, y))
        self.end()

    def swipe(self, points_from, points_to, steps: int = 20, frame_ms: int = 8) -> list[float]:
        """Move one or more fingers from → to in `steps` frames.
        Returns the time each move was injected (to measure latency)."""
        self.start(*points_from)
        injected = []
        for i in range(1, steps + 1):
            f = i / steps
            injected.append(time.perf_counter())
            self.move(
                *[
                    (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                    for a, b in zip(points_from, points_to, strict=True)
                ]
            )
            self.page.wait_for_timeout(frame_ms)
        return injected


def center_of(page: Page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).bounding_box()
    assert box is not None
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def wait_until(
    predicate: Callable[[], bool],
    timeout: float = 3.0,
    what: str | Callable[[], str] = "condition",
) -> None:
    """Poll until `predicate()` is true. `what` may be a function, so the
    failure message can show the state at the moment of failure."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what() if callable(what) else what}")
        time.sleep(0.02)
