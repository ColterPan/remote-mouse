"""
remote_mouse_launcher.py — A tiny script that starts the app.

Why does this exist when `python -m remote_mouse` works?
    * PyInstaller (which builds RemoteMouse.exe) needs a plain script as its
      entry point, not a `-m` module.
    * "Start with Windows" from source runs `pythonw.exe remote_mouse_launcher.py`
      from an arbitrary folder, so the script adds its own folder to the
      import path first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from remote_mouse.__main__ import main  # noqa: E402  (must come after the path fix)

if __name__ == "__main__":
    raise SystemExit(main())
