# remote_mouse.spec — PyInstaller recipe for RemoteMouse.exe
#
# Build (from the `pc` folder):   pyinstaller remote_mouse.spec --clean --noconfirm
# Output:                          dist/RemoteMouse.exe  (single file, no console)
#
# What goes in:
#   * the Python code, starting from remote_mouse_launcher.py
#   * remote_mouse/web/  — the phone remote page (HTML/CSS/JS/icons)
#   * hidden imports: pynput and pystray choose their Windows backend at
#     runtime, so PyInstaller can't see those imports by itself.
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["remote_mouse_launcher.py"],
    pathex=["."],
    datas=[("remote_mouse/web", "remote_mouse/web")],
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pystray._win32",
    ],
    excludes=["pytest", "_pytest", "ruff", "bandit"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RemoteMouse",
    icon="assets/remote_mouse.ico",
    console=False,  # tray app: no black console window
    upx=False,  # UPX compression triggers more antivirus false positives
    debug=False,
    strip=False,
)
