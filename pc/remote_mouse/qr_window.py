"""
qr_window.py — The pairing window: a QR code plus simple instructions.

Built with tkinter (it ships with Python, so no extra dependency). The QR
image is made by the `qrcode` library and shown via Pillow's ImageTk.

If the PC has several network addresses (VPN, Hyper-V, WSL…), a drop-down
lets you choose the one on the same Wi-Fi as your phone; the QR code is
redrawn instantly.

The window has two modes, switched with one button:
  • "pair" — the private pairing QR (it lets a phone control this PC).
  • "app"  — a public QR that downloads the Android app, so getting the app
             onto a phone is just: scan with the camera → install.

All functions here must run on the main (tkinter) thread — see tray.py for
how other threads ask for the window to be shown.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

import qrcode
from PIL import Image, ImageTk

from .netinfo import APP_DOWNLOAD_URL

QR_PIXELS = 300
ICON_PATH = Path(__file__).resolve().parent / "web" / "icons" / "icon-192.png"


def apply_app_icon(root: tk.Tk) -> None:
    """Use the Remote Mouse logo (not tkinter's feather) on every window."""
    photo = ImageTk.PhotoImage(Image.open(ICON_PATH), master=root)
    root.iconphoto(True, photo)
    root._remote_mouse_icon = photo  # type: ignore[attr-defined]  # keep a reference


STEPS = (
    "1.  Connect your phone to the same Wi-Fi as this PC.",
    "2.  Android app (recommended): open Remote Mouse → Scan QR code.\n"
    "     You only do this once — the app reconnects by itself after that.\n"
    "     No app yet? Click “Get the phone app” below.",
    "3.  No app? Scan with the phone camera to open the remote in Chrome.\n"
    "     First time only: tap Advanced → Proceed on the certificate warning.",
)

APP_STEPS = (
    "1.  Scan this with your phone's camera → the Remote Mouse app downloads.",
    "2.  Open the download and allow “Install unknown apps” when asked.",
    "3.  Open Remote Mouse, then click “Back to pairing” here and scan\n"
    "     the pairing code with the app.",
)

MODE_PAIR = "pair"
MODE_APP = "app"
_TITLES = {MODE_PAIR: "Scan to connect your phone", MODE_APP: "Get the Android app"}
_TOGGLE_LABELS = {MODE_PAIR: "Get the phone app", MODE_APP: "Back to pairing"}


def qr_target(mode: str, address: str, build_url: Callable[[str], str]) -> str:
    """What the QR code encodes in each mode."""
    return APP_DOWNLOAD_URL if mode == MODE_APP else build_url(address)


class QrWindow:
    """A single pairing / app-download window that can be shown, refreshed and closed."""

    def __init__(
        self,
        root: tk.Tk,
        get_addresses: Callable[[], list[str]],
        build_url: Callable[[str], str],
    ) -> None:
        self._root = root
        self._get_addresses = get_addresses
        self._build_url = build_url
        self._window: tk.Toplevel | None = None
        self._photo: ImageTk.PhotoImage | None = None  # keep a reference or tk drops it
        self._mode = MODE_PAIR
        self._address = tk.StringVar(master=root)
        self._url = tk.StringVar(master=root)
        self._title = tk.StringVar(master=root)
        self._toggle_label = tk.StringVar(master=root)
        self._image_label: ttk.Label | None = None
        self._picker: ttk.Combobox | None = None
        self._parts: dict[str, ttk.Frame] = {}
        self._buttons: ttk.Frame | None = None

    def show(self, mode: str = MODE_PAIR) -> None:
        if self._window is None or not self._window.winfo_exists():
            self._build()
        self._set_mode(mode)
        self.refresh()
        window = self._window
        if window is None:
            return
        window.deiconify()
        window.lift()
        # Briefly force it on top so it doesn't open hidden behind other apps.
        window.attributes("-topmost", True)
        window.after(300, lambda: window.attributes("-topmost", False))
        window.focus_force()

    def show_app_download(self) -> None:
        self.show(MODE_APP)

    def refresh(self) -> None:
        """Redraw for the current addresses/token (e.g. after Reset pairing)."""
        if self._window is None or not self._window.winfo_exists():
            return
        addresses = self._get_addresses()
        if self._picker is None or not addresses:
            return
        self._picker["values"] = addresses
        if self._address.get() not in addresses:
            self._address.set(addresses[0])
        self._render()

    def _set_mode(self, mode: str) -> None:
        self._mode = mode if mode in _TITLES else MODE_PAIR
        self._title.set(_TITLES[self._mode])
        self._toggle_label.set(_TOGGLE_LABELS[self._mode])
        for name, part in self._parts.items():
            if name == self._mode:
                part.pack(fill="x", before=self._buttons)
            else:
                part.pack_forget()

    def _toggle_mode(self) -> None:
        self._set_mode(MODE_APP if self._mode == MODE_PAIR else MODE_PAIR)
        self._render()

    def _render(self) -> None:
        url = qr_target(self._mode, self._address.get(), self._build_url)
        self._url.set(url)
        qr = qrcode.QRCode(border=2, box_size=10)
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white").get_image()
        image = image.convert("RGB").resize((QR_PIXELS, QR_PIXELS))
        self._photo = ImageTk.PhotoImage(image, master=self._root)
        if self._image_label is not None:
            self._image_label.configure(image=self._photo)

    def _build(self) -> None:
        window = tk.Toplevel(self._root)
        window.title("Remote Mouse")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)  # close = hide
        self._window = window

        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, textvariable=self._title, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self._image_label = ttk.Label(frame)
        self._image_label.pack(pady=12)

        self._buttons = ttk.Frame(frame)
        self._buttons.pack(fill="x", side="bottom", pady=(12, 0))
        ttk.Button(self._buttons, text="Copy link", command=self._copy).pack(side="left")
        ttk.Button(self._buttons, textvariable=self._toggle_label, command=self._toggle_mode).pack(
            side="left", padx=8
        )
        ttk.Button(self._buttons, text="Close", command=window.withdraw).pack(side="right")

        self._parts = {
            MODE_PAIR: self._build_pair_part(frame),
            MODE_APP: self._build_app_part(frame),
        }

    def _build_pair_part(self, parent: ttk.Frame) -> ttk.Frame:
        part = ttk.Frame(parent)
        for step in STEPS:
            ttk.Label(part, text=step, justify="left").pack(anchor="w", pady=1)

        row = ttk.Frame(part)
        row.pack(fill="x", pady=(14, 4))
        ttk.Label(row, text="Network address:").pack(side="left")
        self._picker = ttk.Combobox(row, textvariable=self._address, state="readonly", width=16)
        self._picker.pack(side="left", padx=6)
        self._picker.bind("<<ComboboxSelected>>", lambda _e: self._render())

        ttk.Entry(part, textvariable=self._url, state="readonly", width=58).pack(
            fill="x", pady=(6, 0)
        )
        ttk.Label(
            part,
            text="Keep this link private — it lets a device control this PC.",
            foreground="#a05a00",
        ).pack(anchor="w", pady=(10, 0))
        return part

    def _build_app_part(self, parent: ttk.Frame) -> ttk.Frame:
        part = ttk.Frame(parent)
        for step in APP_STEPS:
            ttk.Label(part, text=step, justify="left").pack(anchor="w", pady=1)
        ttk.Entry(part, textvariable=self._url, state="readonly", width=58).pack(
            fill="x", pady=(14, 0)
        )
        ttk.Label(
            part,
            text="This link is public and safe to share — it only downloads the app.",
            foreground="#1f7a3f",
        ).pack(anchor="w", pady=(10, 0))
        return part

    def _copy(self) -> None:
        self._root.clipboard_clear()
        self._root.clipboard_append(self._url.get())
