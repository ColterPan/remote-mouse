"""
netinfo.py — Finds this PC's local network address and builds the pairing link.

The phone needs to know where to connect, e.g. https://192.168.1.23:8765.
`get_lan_ip()` asks the operating system which local address it would use to
reach the outside world. The trick: "connecting" a UDP socket sends NO packets
— it only asks the routing table to pick an interface — so this works offline
and never contacts the internet.

PCs with VPNs, Hyper-V or WSL have several addresses; `list_private_ipv4()`
returns all of them so the pairing window can let you pick another one.
"""

from __future__ import annotations

import socket
from urllib.parse import quote

from .security import is_private_address

# TEST-NET-1 (RFC 5737): reserved for documentation, never a real host.
_ROUTE_PROBE_ADDRESS = ("192.0.2.1", 9)
LOOPBACK = "127.0.0.1"

# Where phones download the Android app. "latest" always points at the newest
# GitHub release, so this link never needs updating. It's public (no secrets).
APP_DOWNLOAD_URL = (
    "https://github.com/ColterPan/remote-mouse/releases/latest/download/RemoteMouse.apk"
)


def list_private_ipv4() -> list[str]:
    """All private, non-loopback IPv4 addresses of this machine (no duplicates)."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    addresses = (str(info[4][0]) for info in infos)
    return list(
        dict.fromkeys(a for a in addresses if is_private_address(a) and not a.startswith("127."))
    )


def get_lan_ip() -> str:
    """Best guess at the address phones on the same Wi-Fi can reach."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(_ROUTE_PROBE_ADDRESS)
            address = str(probe.getsockname()[0])
    except OSError:
        address = ""
    if is_private_address(address) and not address.startswith("127."):
        return address
    others = list_private_ipv4()
    return others[0] if others else LOOPBACK


def build_pairing_url(host: str, port: int, token: str, fingerprint: str) -> str:
    """
    The link encoded in the QR code.

    The secrets go in the URL *fragment* (after '#'). Browsers never send the
    fragment to the server, so the token doesn't show up in any request line
    or log; the page's JavaScript reads it locally and then removes it.
    """
    return f"https://{host}:{port}/#t={quote(token, safe='')}&fp={quote(fingerprint, safe='')}"
