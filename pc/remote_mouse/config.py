"""
config.py — Loads and saves the PC app's settings.

What is stored (in %APPDATA%\\RemoteMouse\\config.json):
    token  — the secret pairing code. A phone must present it before the PC
             accepts any mouse/keyboard command. It is put into the QR code.
    port   — the TCP port the server listens on (default 8765).
    discovery — announce this PC on the local network so the phone app can
             find it after an IP change (default true; set false to turn off).

Design notes:
    * `Config` is an immutable (frozen) dataclass. To change a value you make
      a *new* Config (see `with_new_token`). This avoids "who changed this?"
      bugs when several threads read the config.
    * A missing or corrupt file is never fatal: we fall back to safe defaults,
      generate a fresh token, and save the repaired file.
    * Files are written atomically (write to a temp file, then rename) so a
      crash or power cut can't leave a half-written config behind.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from dataclasses import asdict, dataclass, replace
from pathlib import Path

logger = logging.getLogger(__name__)

APP_DIR_NAME = "RemoteMouse"
CONFIG_FILE_NAME = "config.json"

DEFAULT_PORT = 8765
MIN_PORT = 1024  # ports below 1024 need admin rights on many systems
MAX_PORT = 65535

# 16 random bytes = 128 bits of entropy. Guessing that is not feasible,
# especially combined with the lockout in security.py.
TOKEN_BYTES = 16

# token_urlsafe(16) produces 22 URL-safe characters. We accept a slightly
# wider range so people can paste a longer token by hand if they want.
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22,128}$")


@dataclass(frozen=True)
class Config:
    """The app's persistent settings. Immutable — use `replace()` to change."""

    token: str
    port: int = DEFAULT_PORT
    discovery: bool = True


def new_token() -> str:
    """Create a new random pairing token using the OS's secure RNG."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def with_new_token(config: Config) -> Config:
    """Return a copy of `config` with a freshly generated token."""
    return replace(config, token=new_token())


def default_config_dir() -> Path:
    """Where settings live: %APPDATA%\\RemoteMouse on Windows (~/.config elsewhere)."""
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_DIR_NAME


def is_valid_token(value: object) -> bool:
    """True if `value` looks like a token we generated (right length/charset)."""
    return isinstance(value, str) and bool(_TOKEN_PATTERN.match(value))


def is_valid_port(value: object) -> bool:
    """True for an int (not a bool!) inside the allowed port range."""
    return isinstance(value, int) and not isinstance(value, bool) and MIN_PORT <= value <= MAX_PORT


def _read_json_object(path: Path) -> dict:
    """Read a JSON object from disk; return {} if missing, unreadable or invalid."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Config file %s is unreadable (%s); using defaults", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("Config file %s is not a JSON object; using defaults", path)
        return {}
    return data


def load_config(path: Path) -> Config:
    """
    Load settings from `path`, repairing anything missing or invalid.

    If the file had to be repaired (or didn't exist yet) the fixed version is
    saved straight away, so the token stays the same across restarts.
    """
    raw = _read_json_object(path)

    token = raw.get("token")
    port = raw.get("port")
    discovery = raw.get("discovery")
    config = Config(
        token=token if is_valid_token(token) else new_token(),
        port=port if is_valid_port(port) else DEFAULT_PORT,
        discovery=discovery if isinstance(discovery, bool) else True,
    )

    if asdict(config) != raw:
        save_config(config, path)
    return config


def save_config(config: Config, path: Path) -> None:
    """Atomically write `config` to `path` as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    os.replace(temp_path, path)  # atomic rename on Windows and POSIX
