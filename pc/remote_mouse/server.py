"""
server.py — The HTTPS + WebSocket server the phone talks to.

Two jobs, one port (default 8765):
    GET /            → the phone remote web page (files in remote_mouse/web/)
    GET /static/...  → its CSS, JavaScript, icons
    GET /ws          → a WebSocket: a long-lived two-way connection that
                       carries the mouse/keyboard messages

Life of a connection (see websocket_handler):
    1. The middleware drops anything not from a private/local address.
    2. Locked-out addresses (too many wrong tokens) get HTTP 429.
    3. The connection is upgraded to a WebSocket.
    4. The FIRST message must be {"t":"auth", "token":…, "v":1} within 10 s.
       Wrong token → failure recorded, connection closed with code 4401.
    5. After that, each message is validated (protocol.py) and executed
       (input_controller.py). Bad messages get an error reply but don't kill
       the session — one glitchy message shouldn't disconnect you.
    6. On disconnect, any mouse button still held down (e.g. mid-drag) is
       released so nothing gets stuck on the PC.

`BackgroundServer` runs all of this on its own thread with its own asyncio
event loop, so the tray icon / windows on the main thread stay responsive.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import mimetypes
import socket
import ssl
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import WSCloseCode, WSMsgType, web

from .input_controller import InputController, execute
from .protocol import (
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    Auth,
    ButtonDown,
    ButtonUp,
    Command,
    Ping,
    ProtocolError,
    parse_message,
)
from .security import FailedAuthLimiter, is_private_address, is_trusted_host, tokens_match

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"

AUTH_TIMEOUT_SECONDS = 5.0  # a real phone sends its token instantly
HEARTBEAT_SECONDS = 15.0  # aiohttp pings idle sockets and drops dead ones
MAX_CLIENTS = 4  # authenticated phones at once
MAX_PENDING_TOTAL = 8  # not-yet-authenticated connections, all addresses
MAX_PENDING_PER_IP = 2  # not-yet-authenticated connections, per address
STARTUP_TIMEOUT_SECONDS = 10.0
DISCONNECT_TIMEOUT_SECONDS = 3.0

# Host names (besides private IPs) that may appear in the Host header.
_HOSTNAME = socket.gethostname().lower()
LOCAL_NAMES = frozenset({"localhost", _HOSTNAME, f"{_HOSTNAME}.local"})

_CLOSED_TYPES = frozenset({WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR})

# Custom WebSocket close codes (4000-4999 are reserved for applications).
CLOSE_UNAUTHORIZED = 4401
CLOSE_VERSION_MISMATCH = 4426
CLOSE_PAIRING_RESET = 4001

# Windows sometimes maps ".js" to text/plain via the registry, which makes
# browsers refuse to run JavaScript modules. Pin the correct types here.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Content-Security-Policy: the page may only load code/styles from this PC and
# only open connections back to this PC. Blocks injected or third-party scripts.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class AuthState:
    """Holds the current pairing token. Thread-safe because the tray thread
    can rotate it ("Reset pairing") while the server thread reads it."""

    def __init__(self, token: str) -> None:
        self._lock = threading.Lock()
        self._token = token

    @property
    def token(self) -> str:
        with self._lock:
            return self._token

    def rotate(self, new_token: str) -> None:
        with self._lock:
            self._token = new_token


@dataclass
class ServerContext:
    """Everything the request handlers need, bundled together."""

    auth: AuthState
    controller: InputController
    limiter: FailedAuthLimiter = field(default_factory=FailedAuthLimiter)
    sockets: set[web.WebSocketResponse] = field(default_factory=set)
    # Connections that are open but haven't authenticated yet, per IP address.
    pending: dict[str, int] = field(default_factory=dict)
    on_client_change: Callable[[int], None] | None = None  # e.g. update the tray tooltip
    on_client_connected: Callable[[str], None] | None = None  # e.g. "phone connected" toast
    name: str = field(default_factory=socket.gethostname)  # shown on the phone

    def notify_client_change(self) -> None:
        if self.on_client_change is not None:
            self.on_client_change(len(self.sockets))

    def reserve_pending(self, ip: str) -> bool:
        """Claim a slot for an unauthenticated connection; False if over the caps."""
        if sum(self.pending.values()) >= MAX_PENDING_TOTAL:
            return False
        if self.pending.get(ip, 0) >= MAX_PENDING_PER_IP:
            return False
        self.pending = {**self.pending, ip: self.pending.get(ip, 0) + 1}
        return True

    def release_pending(self, ip: str) -> None:
        count = self.pending.get(ip, 0) - 1
        others = {k: v for k, v in self.pending.items() if k != ip}
        self.pending = {**others, ip: count} if count > 0 else others


CONTEXT_KEY = web.AppKey("context", ServerContext)


# --- Middleware & headers ----------------------------------------------------


@web.middleware
async def private_network_only(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
) -> web.StreamResponse:
    """Refuse requests not from a local/private address, or with a foreign Host."""
    if not is_private_address(request.remote):
        logger.warning("Refused connection from non-private address %s", request.remote)
        raise web.HTTPForbidden(text="Remote Mouse only accepts devices on your local network.")
    if not is_trusted_host(request.host, LOCAL_NAMES):
        logger.warning("Refused request from %s with untrusted Host header", request.remote)
        raise web.HTTPForbidden(text="Open Remote Mouse using the PC's IP address.")
    return await handler(request)


async def _add_security_headers(request: web.Request, response: web.StreamResponse) -> None:
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)


def _origin_allowed(request: web.Request) -> bool:
    """
    Block cross-site WebSocket hijacking: if a browser sends an Origin header,
    it must be this very server. Native apps (Android, phase 2) send none.
    """
    origin = request.headers.get("Origin")
    return origin is None or origin == f"{request.scheme}://{request.host}"


# --- Handlers ----------------------------------------------------------------


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html")


async def websocket_handler(request: web.Request) -> web.StreamResponse:
    ctx = request.app[CONTEXT_KEY]
    ip = request.remote or "unknown"

    if not _origin_allowed(request):
        logger.warning("Refused WebSocket from %s with foreign Origin", ip)
        raise web.HTTPForbidden(text="Bad origin")
    if ctx.limiter.is_locked(ip):
        raise web.HTTPTooManyRequests(text="Too many wrong pairing attempts. Wait a minute.")
    if len(ctx.sockets) >= MAX_CLIENTS:
        raise web.HTTPServiceUnavailable(text="Too many phones connected.")
    # Cap connections that haven't logged in yet, so nobody can tie up the
    # server by opening lots of sockets and never sending a token.
    if not ctx.reserve_pending(ip):
        raise web.HTTPServiceUnavailable(text="Too many pending connections.")

    ws = web.WebSocketResponse(heartbeat=HEARTBEAT_SECONDS, max_msg_size=MAX_MESSAGE_BYTES)
    try:
        await ws.prepare(request)
        authenticated = await _authenticate(ws, ctx, ip)
    finally:
        ctx.release_pending(ip)
    if not authenticated:
        return ws

    # Register BEFORE saying hello, so a "Reset pairing" that happens at this
    # exact moment still sees (and disconnects) this socket.
    ctx.sockets.add(ws)
    try:
        if await _send(ws, {"t": "hello", "v": PROTOCOL_VERSION, "name": ctx.name}):
            logger.info("Phone connected from %s", ip)
            ctx.notify_client_change()
            if ctx.on_client_connected is not None:
                ctx.on_client_connected(ip)
            await _command_loop(ws, ctx.controller)
    finally:
        ctx.sockets.discard(ws)
        ctx.notify_client_change()
        logger.info("Phone disconnected from %s", ip)
    return ws


async def _send(ws: web.WebSocketResponse, data: dict) -> bool:
    """Send JSON; return False (instead of raising) if the connection is gone."""
    try:
        await ws.send_json(data)
    except (ConnectionError, RuntimeError):
        return False
    return True


async def _reject(ws: web.WebSocketResponse, reply: dict, code: int, reason: bytes) -> None:
    """Tell the phone why, then close. Never raises if the socket already died."""
    with contextlib.suppress(ConnectionError, RuntimeError):
        await ws.send_json(reply)
    await ws.close(code=code, message=reason)


async def _authenticate(ws: web.WebSocketResponse, ctx: ServerContext, ip: str) -> bool:
    """Wait for the auth message. Returns True if the phone may continue."""
    try:
        message = await ws.receive(timeout=AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        ctx.limiter.record_failure(ip)  # holding a slot without logging in counts
        await ws.close(code=CLOSE_UNAUTHORIZED, message=b"auth timeout")
        return False

    if message.type in _CLOSED_TYPES:
        return False  # the phone simply went away; not a wrong guess

    command: Command | None = None
    if message.type == WSMsgType.TEXT:
        try:
            command = parse_message(message.data)
        except ProtocolError:
            command = None

    if isinstance(command, Auth) and command.version != PROTOCOL_VERSION:
        await _reject(
            ws,
            {"t": "error", "reason": "version", "v": PROTOCOL_VERSION},
            CLOSE_VERSION_MISMATCH,
            b"protocol version mismatch",
        )
        return False

    # Re-check the lockout here (not only at upgrade time) so many connections
    # opened in parallel can't each sneak in a guess.
    locked = ctx.limiter.is_locked(ip)
    if locked or not isinstance(command, Auth) or not tokens_match(command.token, ctx.auth.token):
        if not locked:
            ctx.limiter.record_failure(ip)
        logger.warning("Wrong pairing token from %s", ip)
        await _reject(ws, {"t": "error", "reason": "unauthorized"}, CLOSE_UNAUTHORIZED, b"no")
        return False

    ctx.limiter.record_success(ip)
    return True


def _track_buttons(held: frozenset[str], command: Command) -> frozenset[str]:
    """Return the new set of held mouse buttons after `command`."""
    if isinstance(command, ButtonDown):
        return held | {command.button}
    if isinstance(command, ButtonUp):
        return held - {command.button}
    return held


async def _command_loop(ws: web.WebSocketResponse, controller: InputController) -> None:
    """
    Process messages until the socket closes.

    The `finally` guarantees that mouse buttons still held down (mid-drag,
    drag lock) are released however the session ends — a clean close, Wi-Fi
    dropping, or an error while replying.
    """
    held: frozenset[str] = frozenset()
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            try:
                command = parse_message(message.data)
            except ProtocolError as exc:
                if not await _send(ws, {"t": "error", "reason": str(exc)}):
                    break
                continue

            if isinstance(command, Ping):
                if not await _send(ws, {"t": "pong"}):
                    break
                continue
            if isinstance(command, Auth):
                continue  # already authenticated; ignore repeats

            held = _track_buttons(held, command)
            try:
                execute(controller, command)
            except Exception:  # pynput/OS errors must not kill the session
                # Log only the command TYPE: a Text command may contain a password.
                logger.exception("Failed to perform %s", type(command).__name__)
    finally:
        _release_buttons(controller, held)


def _release_buttons(controller: InputController, buttons: frozenset[str]) -> None:
    for button in buttons:
        try:
            controller.release_button(button)
        except Exception:
            logger.exception("Failed to release %s button", button)


async def disconnect_all(ctx: ServerContext, code: int = CLOSE_PAIRING_RESET) -> None:
    """Close every connected phone (used by 'Reset pairing' and on shutdown).

    Sockets are closed in parallel with a time limit, so one unresponsive
    phone can't hold everything up.
    """
    closing = [ws.close(code=code, message=b"disconnected by PC") for ws in list(ctx.sockets)]
    if not closing:
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(*closing, return_exceptions=True), DISCONNECT_TIMEOUT_SECONDS
        )


def create_app(ctx: ServerContext) -> web.Application:
    """Build the aiohttp application with all routes and protections."""
    app = web.Application(middlewares=[private_network_only], client_max_size=64 * 1024)
    app[CONTEXT_KEY] = ctx
    app.on_response_prepare.append(_add_security_headers)
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/static", WEB_DIR, show_index=False, follow_symlinks=False)

    async def _on_shutdown(_app: web.Application) -> None:
        await disconnect_all(ctx, code=WSCloseCode.GOING_AWAY)

    app.on_shutdown.append(_on_shutdown)
    return app


# --- Running in the background ----------------------------------------------


def _log_future_error(future: concurrent.futures.Future) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.error("Background task failed", exc_info=future.exception())


class BackgroundServer:
    """Runs the server on a dedicated thread with its own event loop."""

    def __init__(
        self,
        ctx: ServerContext,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None,
    ) -> None:
        self._ctx = ctx
        self._host = host
        self._port = port
        self._ssl_context = ssl_context
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._error: BaseException | None = None
        self.bound_port: int | None = None

    def start(self) -> None:
        """Start the server; raises OSError if the port can't be opened."""
        self._thread = threading.Thread(target=self._run, name="remote-mouse-server", daemon=True)
        self._thread.start()
        if not self._started.wait(STARTUP_TIMEOUT_SECONDS):
            raise TimeoutError("Server did not start in time")
        if self._error is not None:
            raise self._error

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        runner: web.AppRunner | None = None
        try:
            runner = web.AppRunner(create_app(self._ctx), access_log=None)
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, self._host, self._port, ssl_context=self._ssl_context)
            loop.run_until_complete(site.start())
            self.bound_port = runner.addresses[0][1]
        except BaseException as exc:  # report startup failures to start()
            self._error = exc
            self._started.set()
            if runner is not None:
                loop.run_until_complete(runner.cleanup())
            loop.close()
            return

        logger.info("Server listening on %s:%s", self._host, self.bound_port)
        self._started.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(runner.cleanup())
            loop.close()

    def reset_pairing(self, new_token: str) -> None:
        """Switch to a new token and kick out every connected phone."""
        self._ctx.auth.rotate(new_token)
        if self._loop is not None and self._loop.is_running():
            # Fire and forget: the caller (the GUI thread) must never freeze
            # waiting for slow phones. Errors are logged when it finishes.
            future = asyncio.run_coroutine_threadsafe(disconnect_all(self._ctx), self._loop)
            future.add_done_callback(_log_future_error)

    def stop(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
