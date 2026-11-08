"""Tests for discovery.py — mDNS announcement, using a fake Zeroconf."""

import socket
import time

import pytest

from remote_mouse.discovery import (
    SERVICE_TYPE,
    ServiceAdvertiser,
    build_properties,
    service_instance_name,
    usable_addresses,
)
from remote_mouse.netinfo import get_lan_ip

FP = "ab" * 32


class FakeZeroconf:
    def __init__(self, addresses):
        self.addresses = addresses
        self.registered = []
        self.unregistered = []
        self.closed = False

    def register_service(self, info, allow_name_change=False):
        assert allow_name_change, "name clashes must not silently disable discovery"
        self.registered.append(info)

    def unregister_service(self, info):
        self.unregistered.append(info)

    def close(self):
        self.closed = True


class Factory:
    """Records every Zeroconf instance the advertiser creates."""

    def __init__(self):
        self.instances = []

    def __call__(self, addresses):
        zc = FakeZeroconf(addresses)
        self.instances.append(zc)
        return zc


def make(factory, addresses):
    return ServiceAdvertiser(
        port=8765,
        fingerprint=FP,
        get_addresses=lambda: list(addresses),
        zeroconf_factory=factory,
        refresh_seconds=3600,
    )


def test_txt_record_contains_no_token_and_no_pc_name():
    assert build_properties(FP) == {"v": "1", "fp": FP}


def test_instance_name_is_neutral_and_short():
    name = service_instance_name(FP)
    assert name == "Remote Mouse abababab"
    assert socket.gethostname().lower() not in name.lower()
    assert len(name.encode()) <= 63


def test_loopback_is_never_announced():
    assert usable_addresses(["127.0.0.1", "192.168.1.5", ""]) == ("192.168.1.5",)


def test_start_registers_service_without_revealing_hostname():
    factory = Factory()
    advertiser = make(factory, ["192.168.1.5"])
    advertiser.start()
    zc = factory.instances[0]
    info = zc.registered[0]
    assert zc.addresses == ("192.168.1.5",), "bound to the announced interface"
    assert info.type == SERVICE_TYPE
    assert info.port == 8765
    assert info.addresses == [socket.inet_aton("192.168.1.5")]
    assert info.properties[b"fp"] == FP.encode()
    assert socket.gethostname().lower() not in info.server.lower()
    advertiser.stop()
    assert zc.unregistered and zc.closed


def test_address_change_rebuilds_zeroconf_on_the_new_interface():
    factory = Factory()
    addresses = ["192.168.1.5"]
    advertiser = make(factory, addresses)
    advertiser.start()
    assert advertiser.refresh() is False, "no change, no rebuild"
    addresses[0] = "192.168.1.77"
    assert advertiser.refresh() is True
    old, new = factory.instances
    assert old.closed, "old sockets (bound to the dead address) are closed"
    assert new.addresses == ("192.168.1.77",)
    assert new.registered[0].addresses == [socket.inet_aton("192.168.1.77")]
    advertiser.stop()


def test_starts_announcing_once_wifi_connects():
    """Autostart at login: no network yet, then Wi-Fi comes up."""
    factory = Factory()
    addresses = ["127.0.0.1"]
    advertiser = make(factory, addresses)
    advertiser.start()
    assert not advertiser.announcing
    assert factory.instances == []
    addresses[0] = "10.0.0.8"
    assert advertiser.refresh() is True
    assert advertiser.announcing
    assert factory.instances[0].addresses == ("10.0.0.8",)
    advertiser.stop()


def test_startup_failure_is_not_fatal_and_is_retried():
    calls = []

    def flaky(addresses):
        calls.append(addresses)
        if len(calls) == 1:
            raise OSError("no multicast yet")
        return FakeZeroconf(addresses)

    advertiser = ServiceAdvertiser(
        port=1,
        fingerprint=FP,
        get_addresses=lambda: ["10.0.0.1"],
        zeroconf_factory=flaky,
        refresh_seconds=3600,
    )
    advertiser.start()  # must not raise
    assert not advertiser.announcing
    assert advertiser.refresh() is True  # retried and succeeded
    assert advertiser.announcing
    advertiser.stop()


def test_stop_prevents_further_refreshes():
    factory = Factory()
    advertiser = make(factory, ["192.168.1.5"])
    advertiser.start()
    advertiser.stop()
    assert advertiser.refresh() is False
    assert not advertiser.announcing


def test_real_zeroconf_announces_and_can_be_found():
    """Integration: announce on this PC's real network interface and browse for it."""
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

    lan_ip = get_lan_ip()
    if lan_ip.startswith("127."):
        pytest.skip("no network connection")
    fingerprint = "cd" * 32
    advertiser = ServiceAdvertiser(
        port=8799, fingerprint=fingerprint, get_addresses=lambda: [lan_ip]
    )
    advertiser.start()
    found = []
    browser_zc = Zeroconf()
    try:

        def on_change(zeroconf, service_type, name, state_change):
            if state_change is ServiceStateChange.Added:
                found.append(name)

        ServiceBrowser(browser_zc, SERVICE_TYPE, handlers=[on_change])
        deadline = time.monotonic() + 6
        while not any("cdcdcdcd" in n for n in found) and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        browser_zc.close()
        advertiser.stop()
    assert any("cdcdcdcd" in name for name in found)
