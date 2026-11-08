"""
autostart.py — "Start with Windows" on/off.

Windows runs every program listed under this registry key when you log in:

    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

It's the per-user key (HKCU), so no admin rights are needed, and it only
affects your own account. We store one value named "RemoteMouse" holding the
command to launch, with `--background` so it starts quietly in the tray
instead of popping up the QR window every boot.

The `registry` parameter defaults to Python's built-in `winreg` module; tests
pass in a fake so they never touch your real registry.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "RemoteMouse"
BACKGROUND_FLAG = "--background"

# Used when running from source instead of the .exe (see README).
LAUNCHER = Path(__file__).resolve().parent.parent / "remote_mouse_launcher.py"


def _default_registry() -> Any:
    import winreg  # Windows-only module, imported lazily

    return winreg


def build_command(executable: str, frozen: bool, launcher: Path = LAUNCHER) -> str:
    """
    The command line Windows should run at login.

    * Packaged .exe:   "C:\\…\\RemoteMouse.exe" --background
    * From source:     "C:\\…\\pythonw.exe" "C:\\…\\remote_mouse_launcher.py" --background
      (pythonw = Python without a console window)
    """
    if frozen:
        return f'"{executable}" {BACKGROUND_FLAG}'
    exe = Path(executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    return f'"{interpreter}" "{launcher}" {BACKGROUND_FLAG}'


def current_command() -> str:
    return build_command(sys.executable, frozen=bool(getattr(sys, "frozen", False)))


def get_registered_command(registry: Any = None) -> str | None:
    """The command currently registered, or None if autostart is off."""
    reg = registry or _default_registry()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            value, _ = reg.QueryValueEx(key, VALUE_NAME)
    except OSError:  # FileNotFoundError when the value doesn't exist
        return None
    return value if isinstance(value, str) else None


def is_enabled(registry: Any = None) -> bool:
    return get_registered_command(registry) is not None


def enable(registry: Any = None, command: str | None = None) -> None:
    reg = registry or _default_registry()
    with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command or current_command())


def disable(registry: Any = None) -> None:
    reg = registry or _default_registry()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass  # already disabled


def refresh_if_enabled(registry: Any = None) -> None:
    """If autostart is on but points to an old location (you moved or updated
    the .exe), update it to the current one."""
    registered = get_registered_command(registry)
    expected = current_command()
    if registered is not None and registered != expected:
        enable(registry, expected)
