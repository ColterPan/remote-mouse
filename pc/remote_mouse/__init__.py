"""
Remote Mouse — PC side.

This package turns your Windows PC into the "receiver" for the Remote Mouse
phone remote. At a glance:

    phone (web page / Android app)
        │  JSON messages over an encrypted WebSocket (wss://)
        ▼
    server.py          — serves the phone web page and the /ws endpoint
        │  every message is checked by…
        ├─ security.py — only local-network devices, pairing token, lockout
        ├─ protocol.py — strict validation of each message
        ▼
    input_controller.py — turns valid commands into real mouse/keyboard input

The other modules are "glue" for a nice desktop experience:
    config.py      — settings + pairing token saved in %APPDATA%\\RemoteMouse
    tls.py         — creates the self-signed HTTPS certificate on first run
    netinfo.py     — finds this PC's Wi-Fi/LAN address for the QR code
    autostart.py   — "Start with Windows" (per-user registry Run key)
    tray.py        — the system-tray icon and its menu
    qr_window.py   — the pairing window that shows the QR code
    __main__.py    — wires everything together when the app starts
"""

__version__ = "1.1.0"
