"""Tests for netinfo.py — LAN address discovery and the pairing link."""

import socket

from remote_mouse import netinfo


def test_pairing_url_puts_secrets_in_fragment():
    url = netinfo.build_pairing_url("192.168.1.5", 8765, "tok_en-123", "ab" * 32)
    assert url == f"https://192.168.1.5:8765/#t=tok_en-123&fp={'ab' * 32}"


def test_get_lan_ip_returns_a_private_or_loopback_address():
    address = netinfo.get_lan_ip()
    assert address == netinfo.LOOPBACK or netinfo.is_private_address(address)


def test_list_private_ipv4_filters_public_and_loopback(monkeypatch):
    fake = [
        (socket.AF_INET, 0, 0, "", ("192.168.1.5", 0)),
        (socket.AF_INET, 0, 0, "", ("192.168.1.5", 0)),  # duplicate
        (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
        (socket.AF_INET, 0, 0, "", ("127.0.0.1", 0)),
        (socket.AF_INET, 0, 0, "", ("10.0.0.7", 0)),
    ]
    monkeypatch.setattr(netinfo.socket, "getaddrinfo", lambda *a, **k: fake)
    assert netinfo.list_private_ipv4() == ["192.168.1.5", "10.0.0.7"]


def test_list_private_ipv4_survives_resolver_errors(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("no resolver")

    monkeypatch.setattr(netinfo.socket, "getaddrinfo", broken)
    assert netinfo.list_private_ipv4() == []


class _NoRouteSocket:
    """A socket whose connect() fails, as on a PC with no network at all."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def connect(self, address):
        raise OSError("network unreachable")


def test_get_lan_ip_falls_back_to_interface_list(monkeypatch):
    monkeypatch.setattr(netinfo.socket, "socket", _NoRouteSocket)
    monkeypatch.setattr(netinfo, "list_private_ipv4", lambda: ["10.1.2.3"])
    assert netinfo.get_lan_ip() == "10.1.2.3"


def test_get_lan_ip_falls_back_to_loopback(monkeypatch):
    monkeypatch.setattr(netinfo.socket, "socket", _NoRouteSocket)
    monkeypatch.setattr(netinfo, "list_private_ipv4", lambda: [])
    assert netinfo.get_lan_ip() == netinfo.LOOPBACK
