"""
protocol.py — The "language" the phone and PC speak, and its strict checker.

Every message is a small JSON object with a type field "t". For example:

    {"t": "move",  "dx": 12.5, "dy": -3}          move the pointer
    {"t": "click", "b": "left", "n": 2}           double-click
    {"t": "key",   "k": "c", "mods": ["ctrl"]}    press Ctrl+C

The full list lives in docs/PROTOCOL.md.

Why so strict? The network is untrusted input. `parse_message` turns raw text
into one of the small, typed, immutable command objects below — or raises
`ProtocolError`. Nothing else in the app ever touches raw JSON, so there is
exactly one place to get validation right:

    * unknown message types and unknown keys/buttons are rejected
    * numbers must be real finite numbers (not true/false, NaN or Infinity)
    * movement and scrolling are clamped to sane per-message limits
    * typed text is length-limited and stripped of invisible control characters

To ADD A FEATURE: add a dataclass, a `_parse_xxx` function, register it in
`_PARSERS`, then handle it in input_controller.execute(). See README.
"""

from __future__ import annotations

import json
import math
import string
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

PROTOCOL_VERSION = 1

# --- Limits (keep in sync with docs/PROTOCOL.md) ---------------------------
MAX_MESSAGE_BYTES = 4096  # also enforced by the WebSocket layer
MAX_MOVE_DELTA = 1000.0  # pixels per message, per axis
MAX_SCROLL_DELTA = 20.0  # wheel "notches" per message, per axis
MAX_TEXT_LENGTH = 500  # characters per text message
MAX_CLICK_COUNT = 3  # 1 = click, 2 = double, 3 = triple
MAX_TOKEN_LENGTH = 256

BUTTONS = frozenset({"left", "right", "middle"})

# Order matters: modifiers are always pressed in this order.
MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")
MODIFIERS = frozenset(MODIFIER_ORDER)

SPECIAL_KEYS = frozenset(
    {
        "esc", "tab", "enter", "backspace", "delete", "insert", "space",
        "home", "end", "page_up", "page_down",
        "up", "down", "left", "right",
        "caps_lock", "print_screen", "menu", "win",
        "volume_up", "volume_down", "volume_mute",
        "media_play_pause", "media_next", "media_previous",
        *(f"f{i}" for i in range(1, 13)),
    }
)  # fmt: skip

# Letters and digits are allowed as *keys* so shortcuts like Ctrl+C work.
# (Normal typing uses the "text" message instead.)
CHARACTER_KEYS = frozenset(string.ascii_lowercase + string.digits)

ALLOWED_KEYS = SPECIAL_KEYS | CHARACTER_KEYS

# Control characters we still allow inside typed text.
_ALLOWED_CONTROL_CHARS = frozenset({"\n", "\t"})


class ProtocolError(ValueError):
    """Raised when a message is malformed. The message text is safe to show."""


# --- Command objects --------------------------------------------------------
# frozen=True makes them immutable: once validated, nobody can alter them.


@dataclass(frozen=True)
class Auth:
    token: str
    version: int


@dataclass(frozen=True)
class Ping:
    """Keep-alive. The server answers {"t": "pong"} so the phone knows we're alive."""


@dataclass(frozen=True)
class Move:
    dx: float
    dy: float


@dataclass(frozen=True)
class Click:
    button: str
    count: int = 1


@dataclass(frozen=True)
class ButtonDown:
    button: str


@dataclass(frozen=True)
class ButtonUp:
    button: str


@dataclass(frozen=True)
class Scroll:
    dx: float
    dy: float


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class KeyPress:
    key: str
    modifiers: tuple[str, ...] = ()


Command = Auth | Ping | Move | Click | ButtonDown | ButtonUp | Scroll | Text | KeyPress


# --- Field helpers ----------------------------------------------------------


def _number(data: dict, field: str, limit: float, default: float | None = None) -> float:
    """Read a finite number and clamp it into [-limit, +limit]."""
    value = data.get(field, default)
    # bool is a subclass of int in Python, so exclude it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"'{field}' must be a number")
    if not math.isfinite(value):
        raise ProtocolError(f"'{field}' must be finite")
    return max(-limit, min(limit, float(value)))


def _button(data: dict) -> str:
    button = data.get("b", "left")
    if button not in BUTTONS:
        raise ProtocolError("unknown mouse button")
    return button


def _sanitize_text(text: str) -> str:
    """Normalise newlines and drop invisible control characters (except \\n, \\t)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        ch for ch in text if ch in _ALLOWED_CONTROL_CHARS or unicodedata.category(ch) != "Cc"
    )


# --- One parser per message type -------------------------------------------


def _parse_auth(data: dict) -> Auth:
    token = data.get("token")
    version = data.get("v")
    if not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_LENGTH:
        raise ProtocolError("'token' must be a non-empty string")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProtocolError("'v' must be an integer")
    return Auth(token=token, version=version)


def _parse_ping(data: dict) -> Ping:
    return Ping()


def _parse_move(data: dict) -> Move:
    return Move(dx=_number(data, "dx", MAX_MOVE_DELTA), dy=_number(data, "dy", MAX_MOVE_DELTA))


def _parse_click(data: dict) -> Click:
    count = data.get("n", 1)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_CLICK_COUNT:
        raise ProtocolError(f"'n' must be an integer from 1 to {MAX_CLICK_COUNT}")
    return Click(button=_button(data), count=count)


def _parse_down(data: dict) -> ButtonDown:
    return ButtonDown(button=_button(data))


def _parse_up(data: dict) -> ButtonUp:
    return ButtonUp(button=_button(data))


def _parse_scroll(data: dict) -> Scroll:
    return Scroll(
        dx=_number(data, "dx", MAX_SCROLL_DELTA, default=0),
        dy=_number(data, "dy", MAX_SCROLL_DELTA, default=0),
    )


def _parse_text(data: dict) -> Text:
    text = data.get("s")
    if not isinstance(text, str):
        raise ProtocolError("'s' must be a string")
    if len(text) > MAX_TEXT_LENGTH:
        raise ProtocolError(f"text longer than {MAX_TEXT_LENGTH} characters")
    clean = _sanitize_text(text)
    if not clean:
        raise ProtocolError("text is empty")
    return Text(text=clean)


def _parse_key(data: dict) -> KeyPress:
    key = data.get("k")
    if key not in ALLOWED_KEYS:
        raise ProtocolError("unknown key")
    mods = data.get("mods", [])
    if not isinstance(mods, list) or len(mods) > len(MODIFIER_ORDER):
        raise ProtocolError("'mods' must be a short list")
    if any(m not in MODIFIERS for m in mods):
        raise ProtocolError("unknown modifier")
    # De-duplicate and put into a fixed order (ctrl, alt, shift, win).
    ordered = tuple(m for m in MODIFIER_ORDER if m in mods)
    return KeyPress(key=key, modifiers=ordered)


_PARSERS: dict[str, Callable[[dict], Command]] = {
    "auth": _parse_auth,
    "ping": _parse_ping,
    "move": _parse_move,
    "click": _parse_click,
    "down": _parse_down,
    "up": _parse_up,
    "scroll": _parse_scroll,
    "text": _parse_text,
    "key": _parse_key,
}


def parse_message(raw: str | bytes) -> Command:
    """
    Turn one raw WebSocket message into a validated Command.

    Raises ProtocolError for anything that isn't a well-formed, known message.
    """
    if isinstance(raw, bytes):
        if len(raw) > MAX_MESSAGE_BYTES:
            raise ProtocolError("message too large")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("message is not valid UTF-8") from exc

    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ProtocolError("message is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ProtocolError("message must be a JSON object")

    parser = _PARSERS.get(data.get("t"))  # type: ignore[arg-type]
    if parser is None:
        raise ProtocolError("unknown message type")
    return parser(data)
