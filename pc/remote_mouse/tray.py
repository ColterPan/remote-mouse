"""
tray.py — The system-tray icon (bottom-right, near the clock) and its menu.

Threading model — the one tricky part of desktop Python:
    * tkinter (the QR window, dialogs) must only be used from the MAIN thread.
    * pystray runs its own Windows message loop on a separate thread, and calls
      our menu handlers on THAT thread.
So menu handlers never touch tkinter directly. They put a small function on a
thread-safe queue, and the main thread checks the queue every 100 ms
(`_poll`) and runs whatever is waiting. Simple and race-free.

Menu:
    Show pairing QR code     (also what a left-click on the icon does)
    Start with Windows       ✓ toggle
    Reset pairing…           new token; every paired phone must re-scan
    Quit
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

import pystray
from PIL import Image

from . import autostart
from .qr_window import QrWindow, apply_app_icon

logger = logging.getLogger(__name__)

POLL_MS = 100


class TrayApp:
    def __init__(
        self,
        *,
        icon_image: Image.Image,
        get_addresses: Callable[[], list[str]],
        build_url: Callable[[str], str],
        on_reset_pairing: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._root = tk.Tk()
        self._root.withdraw()  # invisible root; real windows are Toplevels
        self._apply_theme()
        apply_app_icon(self._root)
        self._tasks: queue.Queue[Callable[[], None]] = queue.Queue()
        self._qr = QrWindow(self._root, get_addresses, build_url)
        self._on_reset_pairing = on_reset_pairing
        self._on_quit = on_quit
        self._icon = pystray.Icon(
            "RemoteMouse",
            icon_image,
            "Remote Mouse — no phone connected",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Show pairing QR code", lambda: self._post(self._qr.show), default=True
                ),
                pystray.MenuItem(
                    "Start with Windows",
                    self._toggle_autostart,
                    checked=lambda _item: autostart.is_enabled(),
                ),
                pystray.MenuItem("Reset pairing…", lambda: self._post(self._confirm_reset)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda: self._post(self._quit)),
            ),
        )

    # --- Public API (safe to call from any thread) ---------------------------

    def run(self, show_qr: bool) -> None:
        """Show the tray icon and block until the user chooses Quit."""
        self._icon.run_detached()
        if show_qr:
            self._post(self._qr.show)
        self._root.after(POLL_MS, self._poll)
        self._root.mainloop()

    def set_client_count(self, count: int) -> None:
        suffix = "1 phone connected" if count == 1 else f"{count or 'no'} phones connected"
        self._icon.title = f"Remote Mouse — {suffix}"

    def notify(self, message: str) -> None:
        try:
            self._icon.notify(message, "Remote Mouse")
        except Exception:  # notifications are best-effort
            logger.debug("Tray notification failed", exc_info=True)

    # --- Internals -------------------------------------------------------------

    def _post(self, task: Callable[[], None]) -> None:
        self._tasks.put(task)

    def _poll(self) -> None:
        while True:
            try:
                task = self._tasks.get_nowait()
            except queue.Empty:
                break
            try:
                task()
            except Exception:
                logger.exception("Tray action failed")
        self._root.after(POLL_MS, self._poll)

    def _apply_theme(self) -> None:
        style = ttk.Style(self._root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

    def _toggle_autostart(self) -> None:
        try:
            if autostart.is_enabled():
                autostart.disable()
            else:
                autostart.enable()
        except OSError:
            logger.exception("Could not change autostart setting")
            self.notify("Couldn't change the 'Start with Windows' setting.")
        self._icon.update_menu()

    def _confirm_reset(self) -> None:
        confirmed = messagebox.askyesno(
            "Reset pairing?",
            "This creates a new pairing code and disconnects every phone.\n"
            "Each phone will need to scan the new QR code.\n\nContinue?",
            parent=self._root,
        )
        if not confirmed:
            return
        try:
            self._on_reset_pairing()
        finally:
            self._qr.show()  # always show the (new) code, even if something failed

    def _quit(self) -> None:
        self._on_quit()
        self._icon.stop()
        self._root.quit()
        self._root.destroy()
