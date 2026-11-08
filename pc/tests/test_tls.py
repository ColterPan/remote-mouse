"""Tests for tls.py — self-signed certificate creation and reuse."""

import datetime as dt
import ssl

from cryptography import x509

from remote_mouse.tls import (
    CERT_VALIDITY_DAYS,
    certificate_fingerprint,
    create_ssl_context,
    ensure_certificate,
    generate_self_signed,
)


def test_generated_certificate_contains_names_and_ips():
    cert_pem, key_pem = generate_self_signed(["my-pc", "localhost"], ["192.168.1.5", "127.0.0.1"])
    cert = x509.load_pem_x509_certificate(cert_pem)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == ["my-pc", "localhost"]
    assert [str(ip) for ip in san.get_values_for_type(x509.IPAddress)] == [
        "192.168.1.5",
        "127.0.0.1",
    ]
    assert b"PRIVATE KEY" in key_pem


def test_certificate_is_reused_so_fingerprint_stays_stable(tmp_path):
    first = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"])
    second = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"])
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert len(first.fingerprint_sha256) == 64


def test_certificate_is_renewed_when_about_to_expire(tmp_path):
    first = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"])
    later = dt.datetime.now(dt.UTC) + dt.timedelta(days=CERT_VALIDITY_DAYS - 1)
    renewed = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"], now=later)
    assert renewed.fingerprint_sha256 != first.fingerprint_sha256


def test_corrupt_certificate_is_regenerated(tmp_path):
    first = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"])
    first.cert_path.write_text("garbage")
    repaired = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"])
    assert repaired.fingerprint_sha256 == certificate_fingerprint(repaired.cert_path.read_bytes())


def test_ssl_context_loads_and_requires_modern_tls(tmp_path):
    info = ensure_certificate(tmp_path, ["pc"], ["127.0.0.1"])
    context = create_ssl_context(info)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
