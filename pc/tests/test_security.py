"""Tests for security.py — network allow-list, token check and lockout."""

import pytest

from remote_mouse.security import (
    FailedAuthLimiter,
    is_private_address,
    is_trusted_host,
    tokens_match,
)


class FakeClock:
    """A clock we can move forward by hand instead of sleeping in tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    "address",
    [
        "192.168.1.20",
        "10.0.0.5",
        "172.16.4.4",
        "172.31.255.255",
        "127.0.0.1",
        "169.254.10.10",
        "::1",
        "fe80::1%12",
        "fd00::abcd",
        "::ffff:192.168.0.9",
    ],
)
def test_private_addresses_are_allowed(address):
    assert is_private_address(address)


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "1.1.1.1",
        "172.32.0.1",  # just outside 172.16/12
        "2606:4700:4700::1111",
        "::ffff:8.8.8.8",
        "0.0.0.0",
        "224.0.0.1",  # multicast
        "not-an-ip",
        "",
        None,
    ],
)
def test_public_or_invalid_addresses_are_refused(address):
    assert not is_private_address(address)


LOCAL = frozenset({"localhost", "my-pc", "my-pc.local"})


@pytest.mark.parametrize(
    "host",
    [
        "192.168.1.5:8765",
        "192.168.1.5",
        "127.0.0.1:8765",
        "localhost:8765",
        "MY-PC:8765",
        "my-pc.local.:8765",
        "[::1]:8765",
        "[fe80::1]:8765",
    ],
)
def test_trusted_hosts(host):
    assert is_trusted_host(host, LOCAL)


@pytest.mark.parametrize(
    "host",
    [
        "evil.example:8765",
        "evil.example",
        "8.8.8.8:8765",
        "[2606:4700::1111]:8765",
        "[::1",
        "",
        None,
    ],
)
def test_untrusted_hosts_dns_rebinding(host):
    assert not is_trusted_host(host, LOCAL)


class TestTokensMatch:
    def test_same_token_matches(self):
        assert tokens_match("secret-token", "secret-token")

    def test_different_token_does_not_match(self):
        assert not tokens_match("secret-tokeN", "secret-token")

    def test_non_string_is_refused(self):
        assert not tokens_match(None, "secret-token")
        assert not tokens_match(123, "secret-token")

    def test_empty_expected_token_never_matches(self):
        assert not tokens_match("", "")


class TestFailedAuthLimiter:
    def test_locks_after_max_failures(self):
        limiter = FailedAuthLimiter(max_failures=3, lockout_seconds=60, clock=FakeClock())
        for _ in range(2):
            limiter.record_failure("10.0.0.2")
        assert not limiter.is_locked("10.0.0.2")
        limiter.record_failure("10.0.0.2")
        assert limiter.is_locked("10.0.0.2")

    def test_lockout_is_per_address(self):
        limiter = FailedAuthLimiter(max_failures=1, clock=FakeClock())
        limiter.record_failure("10.0.0.2")
        assert limiter.is_locked("10.0.0.2")
        assert not limiter.is_locked("10.0.0.3")

    def test_lockout_expires_and_counter_resets(self):
        clock = FakeClock()
        limiter = FailedAuthLimiter(max_failures=2, lockout_seconds=60, clock=clock)
        limiter.record_failure("10.0.0.2")
        limiter.record_failure("10.0.0.2")
        assert limiter.is_locked("10.0.0.2")

        clock.now += 61
        assert not limiter.is_locked("10.0.0.2")
        # A single new failure must not immediately re-lock (clean slate).
        limiter.record_failure("10.0.0.2")
        assert not limiter.is_locked("10.0.0.2")

    def test_success_resets_counter(self):
        limiter = FailedAuthLimiter(max_failures=2, clock=FakeClock())
        limiter.record_failure("10.0.0.2")
        limiter.record_success("10.0.0.2")
        limiter.record_failure("10.0.0.2")
        assert not limiter.is_locked("10.0.0.2")

    def test_invalid_configuration_is_rejected(self):
        with pytest.raises(ValueError):
            FailedAuthLimiter(max_failures=0)
