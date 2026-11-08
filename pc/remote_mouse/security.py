"""
security.py — The three locks on the door.

Anyone who can send input to your PC effectively controls it, so the server
checks three things before it obeys a phone:

1. **Where is the connection coming from?**  `is_private_address`
   Only devices on your own local network (home Wi-Fi, LAN, the PC itself)
   are allowed. A connection from a public internet address is refused before
   it can even try a password. This matters if a router ever forwards the port
   by accident.

2. **Does it know the secret?**  `tokens_match`
   The phone must send the pairing token from the QR code. The comparison uses
   `hmac.compare_digest`, which takes the same time no matter how many
   characters match, so an attacker can't guess the token one character at a
   time by measuring response times.

3. **Is it guessing?**  `FailedAuthLimiter`
   After `max_failures` wrong tokens from one IP address, that address is
   locked out for `lockout_seconds`. Together with a 128-bit token this makes
   brute-forcing impossible in practice.
"""

from __future__ import annotations

import hmac
import ipaddress
import time
from collections.abc import Callable

DEFAULT_MAX_FAILURES = 5
DEFAULT_LOCKOUT_SECONDS = 60.0


def is_private_address(address: str | None) -> bool:
    """
    Return True if `address` belongs to a local/private network.

    Accepted: 10.x, 172.16-31.x, 192.168.x (RFC 1918), link-local
    (169.254.x / fe80::), loopback (127.x / ::1) and IPv6 unique-local (fc00::/7).
    Everything else — public addresses, garbage strings, None — is refused.
    """
    if not address:
        return False
    try:
        # IPv6 addresses may carry a "zone id" like fe80::1%eth0 — strip it.
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False

    # "::ffff:192.168.1.5" is an IPv4 address wrapped in IPv6 — judge the IPv4.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if ip.is_multicast or ip.is_unspecified:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def is_trusted_host(host: str | None, local_names: frozenset[str]) -> bool:
    """
    Check the HTTP `Host` header (e.g. "192.168.1.5:8765").

    Defends against *DNS rebinding*: a malicious website could make its own
    domain name (evil.example) point at your PC's IP, and the browser would
    then send requests to your PC with `Host: evil.example`. We only accept a
    private IP address, "localhost", or this PC's own name.
    """
    if not host:
        return False
    if host.startswith("["):  # IPv6 literal: "[fe80::1]:8765"
        name = host[1 : host.find("]")] if "]" in host else ""
    else:
        name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    name = name.lower().rstrip(".")
    return name in local_names or is_private_address(name)


def tokens_match(provided: object, expected: str) -> bool:
    """Constant-time comparison of the token a phone sent with the real one."""
    if not isinstance(provided, str) or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


class FailedAuthLimiter:
    """
    Counts wrong pairing attempts per IP address and locks out guessers.

    State per IP is `(failure_count, locked_until)`. `clock` is injectable so
    tests can fast-forward time without sleeping.
    """

    def __init__(
        self,
        max_failures: int = DEFAULT_MAX_FAILURES,
        lockout_seconds: float = DEFAULT_LOCKOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_failures < 1:
            raise ValueError("max_failures must be at least 1")
        self._max_failures = max_failures
        self._lockout_seconds = lockout_seconds
        self._clock = clock
        self._entries: dict[str, tuple[int, float]] = {}

    def is_locked(self, ip: str) -> bool:
        """True while `ip` is serving a lockout. Expired lockouts are forgotten."""
        entry = self._entries.get(ip)
        if entry is None:
            return False
        _, locked_until = entry
        if locked_until == 0.0:
            return False  # some failures recorded, but not locked yet
        if self._clock() < locked_until:
            return True
        # Lockout is over: give the address a clean slate.
        self._entries = {k: v for k, v in self._entries.items() if k != ip}
        return False

    def record_failure(self, ip: str) -> None:
        """Note a wrong token from `ip`; start a lockout when the limit is hit."""
        count = self._entries.get(ip, (0, 0.0))[0] + 1
        locked_until = self._clock() + self._lockout_seconds if count >= self._max_failures else 0.0
        self._entries = {**self._entries, ip: (count, locked_until)}

    def record_success(self, ip: str) -> None:
        """A correct token resets the counter for that address."""
        self._entries = {k: v for k, v in self._entries.items() if k != ip}
