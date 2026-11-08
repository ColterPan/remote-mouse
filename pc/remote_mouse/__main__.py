"""
__main__.py — Program start-up: wires every module together.

Run with:   python -m remote_mouse            (from the `pc` folder)
       or:  RemoteMouse.exe                   (packaged build)
Options:    --background   start hidden in the tray (used by "Start with Windows")
            --port N       use another port for this run

Start-up sequence:
    1. Make sure only ONE copy runs (a named Windows mutex). A second launch
       just tells you where to find the first one.
    2. Set up logging to %APPDATA%\\RemoteMouse\\remote_mouse.log.
    3. Load settings (token, port) and the HTTPS certificate — created on
       first run.
    4. Start the server on a background thread.
    5. Show the tray icon (and the QR window, unless --background). The main
       thread now runs the GUI until you choose Quit.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import logging
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PIL import Image

from . import __version__, autostart
from .config import Config, default_config_dir, is_valid_port, load_config, save_config
from .config import with_new_token as config_with_new_token
from .input_controller import PynputController
from .netinfo import build_pairing_url, get_lan_ip, list_private_ipv4
from .security import FailedAuthLimiter
from .server import WEB_DIR, AuthState, BackgroundServer, ServerContext
from .tls import create_ssl_context, ensure_certificate
from .tray import TrayApp

logger = logging.getLogger("remote_mouse")

MUTEX_NAME = "Local\\RemoteMouseSingleInstance"
ERROR_ALREADY_EXISTS = 183
LISTEN_HOST = "0.0.0.0"  # all interfaces; non-private callers are refused in server.py
ICON_PATH = WEB_DIR / "icons" / "icon-192.png"

_mutex_handle = None  # kept alive for the whole process lifetime


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="RemoteMouse", description="Remote Mouse PC app")
    parser.add_argument("--background", action="store_true", help="start hidden in the tray")
    parser.add_argument("--port", type=int, help="override the port for this run")
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def setup_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            directory / "remote_mouse.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:  # windowed .exe builds have no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def show_message(text: str, title: str = "Remote Mouse") -> None:
    """A plain Windows message box (works before any GUI is set up)."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION
    else:
        print(f"{title}: {text}", file=sys.stderr)


def acquire_single_instance() -> bool:
    """Return False if another Remote Mouse is already running."""
    global _mutex_handle
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def enable_high_dpi() -> None:
    """Sharp (non-blurry) windows on high-resolution screens."""
    if sys.platform == "win32":
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(1)


def network_addresses() -> list[str]:
    """Best address first, then any others; never empty."""
    return list(dict.fromkeys([get_lan_ip(), *list_private_ipv4()]))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_dir = default_config_dir()
    setup_logging(config_dir)

    if not acquire_single_instance():
        show_message(
            "Remote Mouse is already running.\n\n"
            "Look for its icon near the clock (click ^ if hidden) and choose "
            "“Show pairing QR code”."
        )
        return 0

    enable_high_dpi()
    config_path = config_dir / "config.json"
    config = load_config(config_path)
    port = args.port if args.port is not None and is_valid_port(args.port) else config.port

    lan_ip = get_lan_ip()
    certificate = ensure_certificate(
        config_dir, [socket.gethostname(), "localhost"], [lan_ip, "127.0.0.1"]
    )
    auth = AuthState(config.token)
    ctx = ServerContext(auth=auth, controller=PynputController(), limiter=FailedAuthLimiter())
    server = BackgroundServer(ctx, LISTEN_HOST, port, create_ssl_context(certificate))

    try:
        server.start()
    except OSError as exc:
        logger.error("Could not start server on port %s: %s", port, exc)
        show_message(
            f"Remote Mouse could not open port {port}.\n\n"
            "Another program may be using it. Close that program, or set a "
            f'different "port" in:\n{config_path}'
        )
        return 1

    try:
        autostart.refresh_if_enabled()
    except OSError:
        logger.warning("Could not refresh autostart entry", exc_info=True)

    state = {"config": config}

    def reset_pairing() -> None:
        new_config: Config = config_with_new_token(state["config"])
        save_config(new_config, config_path)
        state["config"] = new_config
        server.reset_pairing(new_config.token)
        logger.info("Pairing reset; all phones disconnected")

    def build_url(address: str) -> str:
        return build_pairing_url(address, port, auth.token, certificate.fingerprint_sha256)

    tray = TrayApp(
        icon_image=Image.open(ICON_PATH),
        get_addresses=network_addresses,
        build_url=build_url,
        on_reset_pairing=reset_pairing,
        on_quit=server.stop,
    )
    ctx.on_client_change = tray.set_client_count

    # Tell the user whenever a device connects from an address not seen yet
    # this session — if it wasn't them, they can Reset pairing immediately.
    seen_addresses: set[str] = set()

    def on_client_connected(address: str) -> None:
        if address in seen_addresses:
            return
        seen_addresses.add(address)
        tray.notify(f"A phone connected from {address}. Not you? Use Reset pairing.")

    ctx.on_client_connected = on_client_connected
    tray.set_client_count(len(ctx.sockets))  # a phone may have reconnected already
    logger.info("Remote Mouse %s ready on port %s", __version__, port)
    tray.run(show_qr=not args.background)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
