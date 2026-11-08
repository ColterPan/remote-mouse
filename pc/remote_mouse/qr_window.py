"""
qr_window.py — The pairing window: a QR code plus simple instructions.

Built with tkinter (it ships with Python, so no extra dependency). The QR
image is made by the `qrcode` library and shown via Pillow's ImageTk.

If the PC has several network addresses (VPN, Hyper-V, WSL…), a drop-down
lets you choose the one on the same Wi-Fi as your phone; the QR code is
redrawn instantly.

All functions here must run on the main (tkinter) thread — see tray.py for
how other threads ask for the window to be shown.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

import qrcode
from PIL import ImageTk

QR_PIXELS = 300
STEPS = (
    "1.  Connect your phone to the same Wi-Fi as this PC.",
    "2.  Open the phone camera and scan this code.",
    "3.  The first time, Chrome warns about the certificate:\n"
    "     tap Advanced → Proceed. (It's this PC's own certificate.)",
    "4.  In Chrome's ⋮ menu, tap “Add to Home screen” for a one-tap icon.",
)


class QrWindow:
    """A single pairing window that can be shown, refreshed and closed."""

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
        self._address = tk.StringVar(master=root)
        self._url = tk.StringVar(master=root)
        self._image_label: ttk.Label | None = None
        self._picker: ttk.Combobox | None = None

    def show(self) -> None:
        if self._window is None or not self._window.winfo_exists():
            self._build()
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

    def _render(self) -> None:
        url = self._build_url(self._address.get())
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
        window.title("Remote Mouse — Pair your phone")
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)  # close = hide
        self._window = window

        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Scan to connect your phone", font=("Segoe UI", 14, "bold")).pack(
            anchor="w"
        )
        self._image_label = ttk.Label(frame)
        self._image_label.pack(pady=12)

        for step in STEPS:
            ttk.Label(frame, text=step, justify="left").pack(anchor="w", pady=1)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(14, 4))
        ttk.Label(row, text="Network address:").pack(side="left")
        self._picker = ttk.Combobox(row, textvariable=self._address, state="readonly", width=16)
        self._picker.pack(side="left", padx=6)
        self._picker.bind("<<ComboboxSelected>>", lambda _e: self._render())

        link = ttk.Entry(frame, textvariable=self._url, state="readonly", width=58)
        link.pack(fill="x", pady=(6, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Copy link", command=self._copy).pack(side="left")
        ttk.Button(buttons, text="Close", command=window.withdraw).pack(side="right")
        ttk.Label(
            frame,
            text="Keep this link private — it lets a device control this PC.",
            foreground="#a05a00",
        ).pack(anchor="w", pady=(10, 0))

    def _copy(self) -> None:
        self._root.clipboard_clear()
        self._root.clipboard_append(self._url.get())
