"""
pc_screenshot.py — Captures the PC pairing window for the README.

Opens the real QrWindow with DEMO data only (address 192.168.1.20 and a fake
token), so the published image can't be used to pair with anyone's PC.

It also captures the "Get the phone app" mode (a public download QR).

Run from the `pc` folder:   python tools/pc_screenshot.py
Output: docs/images/pc-pairing-window.png, docs/images/pc-get-app-window.png
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from remote_mouse.qr_window import QrWindow, apply_app_icon  # noqa: E402

IMAGES = Path(__file__).resolve().parents[2] / "docs" / "images"
OUT = IMAGES / "pc-pairing-window.png"
OUT_APP = IMAGES / "pc-get-app-window.png"
DEMO_URL = "https://{address}:8765/#t=DemoTokenNotARealOne0&fp=" + "0" * 64
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def window_rect(widget: tk.Misc) -> tuple[int, int, int, int]:
    """Screen rectangle of the whole window including its title bar."""
    hwnd = ctypes.windll.user32.GetParent(widget.winfo_id())
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    return rect.left, rect.top, rect.right, rect.bottom


def main() -> None:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    root = tk.Tk()
    root.withdraw()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    apply_app_icon(root)
    window = QrWindow(root, lambda: ["192.168.1.20"], lambda a: DEMO_URL.format(address=a))
    window.show()

    def grab(path: Path) -> None:
        top = window._window  # noqa: SLF001 (tool needs the Toplevel)
        assert top is not None
        top.attributes("-topmost", True)
        top.update()
        path.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=window_rect(top), all_screens=True).save(path)

    def capture_pairing() -> None:
        grab(OUT)
        window._toggle_mode()  # noqa: SLF001 (same as clicking "Get the phone app")
        root.after(800, capture_app)

    def capture_app() -> None:
        grab(OUT_APP)
        root.destroy()

    root.after(1200, capture_pairing)
    root.mainloop()
    print("Saved", OUT, OUT_APP)  # noqa: T201 (CLI tool output)


if __name__ == "__main__":
    main()
