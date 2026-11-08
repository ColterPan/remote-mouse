"""
tls.py — Creates and loads the HTTPS certificate that encrypts phone ↔ PC traffic.

Why HTTPS on a home network? Everything you type on the phone (including
passwords) travels over Wi-Fi. Without encryption, anyone on the same Wi-Fi
(a guest, a compromised smart device, a café network) could read it.

How it works:
    * On first run we generate a private key (elliptic-curve P-256) and a
      "self-signed" certificate — one that we vouch for ourselves instead of
      a public certificate authority. That is normal for devices on a LAN
      (routers, printers and NAS boxes do the same).
    * The browser can't verify who signed it, so it shows a warning ONCE.
      You tap "Advanced → Proceed", and from then on traffic is encrypted.
    * The certificate's SHA-256 fingerprint is put in the QR code. The Android
      app (phase 2) checks the fingerprint ("certificate pinning"), so it can
      trust the PC without any warning — and would detect an impostor.

The key and certificate are stored next to config.json in %APPDATA%, which
only your Windows user account can read. They are kept for 10 years and
regenerated automatically shortly before they expire.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import os
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERT_FILE_NAME = "cert.pem"
KEY_FILE_NAME = "key.pem"
CERT_VALIDITY_DAYS = 3650
RENEW_BEFORE_DAYS = 30


@dataclass(frozen=True)
class CertificateInfo:
    cert_path: Path
    key_path: Path
    fingerprint_sha256: str  # lowercase hex of SHA-256 over the DER certificate


def certificate_fingerprint(cert_pem: bytes) -> str:
    """SHA-256 fingerprint of a PEM certificate, as lowercase hex."""
    cert = x509.load_pem_x509_certificate(cert_pem)
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def generate_self_signed(
    hostnames: list[str], ip_addresses: list[str], now: dt.datetime | None = None
) -> tuple[bytes, bytes]:
    """Return (cert_pem, key_pem) for a new self-signed server certificate."""
    now = now or dt.datetime.now(dt.UTC)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Remote Mouse")])

    # Subject Alternative Names: the host names / IPs this cert is valid for.
    alt_names: list[x509.GeneralName] = [x509.DNSName(h) for h in dict.fromkeys(hostnames)]
    alt_names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in dict.fromkeys(ip_addresses)]

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))  # tolerate small clock drift
        .not_valid_after(now + dt.timedelta(days=CERT_VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def _needs_renewal(cert_pem: bytes, now: dt.datetime) -> bool:
    cert = x509.load_pem_x509_certificate(cert_pem)
    return cert.not_valid_after_utc - now < dt.timedelta(days=RENEW_BEFORE_DAYS)


def _write_private(path: Path, data: bytes) -> None:
    """Write a file readable only by the owner (where the OS supports it)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def ensure_certificate(
    directory: Path,
    hostnames: list[str],
    ip_addresses: list[str],
    now: dt.datetime | None = None,
) -> CertificateInfo:
    """
    Make sure a valid certificate exists in `directory`, creating one if needed.

    An existing certificate is kept (so the fingerprint the Android app pinned
    stays valid) unless it is unreadable or about to expire.
    """
    now = now or dt.datetime.now(dt.UTC)
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / CERT_FILE_NAME
    key_path = directory / KEY_FILE_NAME

    cert_pem: bytes | None = None
    if cert_path.exists() and key_path.exists():
        try:
            existing = cert_path.read_bytes()
            if not _needs_renewal(existing, now):
                cert_pem = existing
        except (OSError, ValueError):
            cert_pem = None  # unreadable/corrupt → regenerate below

    if cert_pem is None:
        cert_pem, key_pem = generate_self_signed(hostnames, ip_addresses, now)
        _write_private(key_path, key_pem)
        cert_path.write_bytes(cert_pem)

    return CertificateInfo(cert_path, key_path, certificate_fingerprint(cert_pem))


def create_ssl_context(info: CertificateInfo) -> ssl.SSLContext:
    """Server-side TLS settings: modern protocol versions only."""
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(info.cert_path), keyfile=str(info.key_path))
    return context
