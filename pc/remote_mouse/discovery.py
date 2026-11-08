"""
discovery.py — Lets the phone app find this PC automatically (no QR re-scan).

The problem: your router can give the PC a new IP address at any time (after a
reboot, a new lease, a different Wi-Fi). The phone app remembers the old
address, which then stops working.

The fix: the PC announces itself on the local network using mDNS/DNS-SD — the
same "zero-configuration" standard printers, Chromecasts and AirPlay speakers
use. The Android app asks "who offers _remotemouse._tcp?", and every running
Remote Mouse PC answers with its current address and port.

How the app knows it found the RIGHT PC: the announcement includes the PC's
certificate fingerprint (public information — it's not a secret). The app only
accepts a PC whose fingerprint matches the one it paired with, and it then
verifies that same certificate when connecting (see tls.py). An impostor can
copy the announcement but cannot present the matching certificate.

What is NOT announced: the pairing token (ever), and not your computer's name
either (it's often a person's name, and the announcement can be seen by anyone
on the same network). The instance is called "Remote Mouse <first 8 hex of the
fingerprint>". The phone learns the friendly PC name only after connecting.
Discovery can be switched off with "discovery": false in config.json.

The Zeroconf factory is injectable so tests don't touch the real network.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from typing import Any

from .protocol import PROTOCOL_VERSION

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_remotemouse._tcp.local."
REFRESH_SECONDS = 30.0  # re-check our addresses this often (DHCP changes)
MAX_LABEL_BYTES = 63  # DNS label limit


def short_id(fingerprint: str) -> str:
    return fingerprint[:8].lower()


def service_instance_name(fingerprint: str) -> str:
    """Neutral, DNS-safe instance name, e.g. 'Remote Mouse 3fa2b4c1'."""
    return f"Remote Mouse {short_id(fingerprint)}"[:MAX_LABEL_BYTES]


def build_properties(fingerprint: str) -> dict[str, str]:
    """The public TXT record: protocol version + certificate fingerprint only."""
    return {"v": str(PROTOCOL_VERSION), "fp": fingerprint}


def usable_addresses(addresses: list[str]) -> tuple[str, ...]:
    """Drop loopback (127.x): a phone can never reach it. Happens when the PC
    starts before Wi-Fi is connected (e.g. autostart at login)."""
    return tuple(a for a in addresses if a and not a.startswith("127."))


class ServiceAdvertiser:
    """
    Announces this PC via mDNS and keeps the announcement current.

    Important detail: a Zeroconf instance binds its network sockets to the
    interface addresses that exist when it is CREATED and never re-scans. So
    when the PC's address changes (new DHCP lease, waking from sleep, Wi-Fi
    connecting after login), merely updating the record isn't enough — we tear
    the instance down and build a fresh one bound to the new address.
    """

    def __init__(
        self,
        *,
        port: int,
        fingerprint: str,
        get_addresses: Callable[[], list[str]],
        zeroconf_factory: Callable[[tuple[str, ...]], Any] | None = None,
        refresh_seconds: float = REFRESH_SECONDS,
    ) -> None:
        self._port = port
        self._fingerprint = fingerprint
        self._get_addresses = get_addresses
        self._zeroconf_factory = zeroconf_factory or _default_zeroconf
        self._refresh_seconds = refresh_seconds
        self._zeroconf: Any = None
        self._info: Any = None
        self._addresses: tuple[str, ...] = ()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _build_info(self, addresses: tuple[str, ...]) -> Any:
        from zeroconf import ServiceInfo

        name = service_instance_name(self._fingerprint)
        return ServiceInfo(
            SERVICE_TYPE,
            f"{name}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(a) for a in addresses],
            port=self._port,
            properties=build_properties(self._fingerprint),
            server=f"remote-mouse-{short_id(self._fingerprint)}.local.",
        )

    @property
    def announcing(self) -> bool:
        return self._zeroconf is not None

    def start(self) -> None:
        """Begin announcing (now, or as soon as there's a usable address).
        Failures are logged, never fatal — QR pairing and saved addresses
        still work without discovery."""
        self.refresh()
        self._thread = threading.Thread(target=self._refresh_loop, name="mdns", daemon=True)
        self._thread.start()

    def refresh(self) -> bool:
        """(Re)announce if our usable addresses changed. Returns True if changed."""
        with self._lock:
            if self._stop.is_set():
                return False
            current = usable_addresses(self._get_addresses())
            if current == self._addresses and (self.announcing or not current):
                return False
            self._teardown()
            self._addresses = current
            if not current:
                logger.info("No network address yet; discovery will start when connected")
                return True
            try:
                self._zeroconf = self._zeroconf_factory(current)
                self._info = self._build_info(current)
                self._zeroconf.register_service(self._info, allow_name_change=True)
            except Exception:
                logger.exception("Network discovery could not start; will retry")
                self._teardown()
                self._addresses = ()
                return False
            logger.info("Announcing %s on %s", SERVICE_TYPE, ", ".join(current))
            return True

    def _teardown(self) -> None:
        """Unregister and close the current Zeroconf instance (caller holds the lock)."""
        if self._zeroconf is None:
            return
        try:
            self._zeroconf.unregister_service(self._info)
            self._zeroconf.close()
        except Exception:
            logger.exception("Error while stopping network discovery")
        self._zeroconf = None

    def _refresh_loop(self) -> None:
        while not self._stop.wait(self._refresh_seconds):
            try:
                self.refresh()
            except Exception:
                logger.exception("Could not refresh network announcement")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._lock:
            self._teardown()


def _default_zeroconf(addresses: tuple[str, ...]) -> Any:
    from zeroconf import IPVersion, Zeroconf

    # Bind only to the interfaces we announce — the ones a phone can reach.
    return Zeroconf(interfaces=list(addresses), ip_version=IPVersion.V4Only)
