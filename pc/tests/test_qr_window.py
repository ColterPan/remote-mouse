"""Tests for the pairing / "Get the phone app" window (qr_window.py)."""

from __future__ import annotations

import tkinter as tk

import pytest

from remote_mouse.netinfo import APP_DOWNLOAD_URL
from remote_mouse.qr_window import MODE_APP, MODE_PAIR, QrWindow, qr_target


def pairing_url(address: str) -> str:
    return f"https://{address}:8765/#t=TestTokenTestTokenTest&fp=ab"


def test_download_link_is_the_public_latest_apk():
    assert APP_DOWNLOAD_URL == (
        "https://github.com/ColterPan/remote-mouse/releases/latest/download/RemoteMouse.apk"
    )
    assert "#" not in APP_DOWNLOAD_URL, "no token or other secret in the public link"


def test_qr_target_per_mode():
    assert qr_target(MODE_PAIR, "192.168.1.20", pairing_url) == pairing_url("192.168.1.20")
    assert qr_target(MODE_APP, "192.168.1.20", pairing_url) == APP_DOWNLOAD_URL


@pytest.fixture
def root():
    try:
        tk_root = tk.Tk()
    except tk.TclError:  # pragma: no cover - no display (headless CI)
        pytest.skip("no display for tkinter")
    tk_root.withdraw()
    yield tk_root
    tk_root.destroy()


def test_window_switches_between_pairing_and_app_download(root):
    window = QrWindow(root, lambda: ["192.168.1.20"], pairing_url)

    window.show()
    assert window._url.get() == pairing_url("192.168.1.20")
    assert window._title.get() == "Scan to connect your phone"

    window._toggle_mode()  # the "Get the phone app" button
    assert window._url.get() == APP_DOWNLOAD_URL
    assert window._title.get() == "Get the Android app"
    assert window._toggle_label.get() == "Back to pairing"
    assert window._parts[MODE_APP].winfo_manager() == "pack"
    assert window._parts[MODE_PAIR].winfo_manager() == ""

    window._toggle_mode()  # "Back to pairing"
    assert window._url.get() == pairing_url("192.168.1.20")

    window.show_app_download()  # the tray menu item
    assert window._url.get() == APP_DOWNLOAD_URL
