"""
input_controller.py — Turns validated commands into real mouse & keyboard input.

Layers:
    execute(controller, command)   — routes a protocol command to a method
    InputController (Protocol)     — the interface: move, click, type_text, …
    PynputController               — the real thing, using the `pynput` library
                                     (on Windows that calls the SendInput API)
    FakeController                 — records calls; used by tests so they never
                                     move your actual mouse

Why an interface? The server only knows "something that can move/click/type".
Tests plug in FakeController; a future macOS/Linux backend could plug in its
own class without touching server code.

Sub-pixel movement: the phone sends fractional deltas (e.g. 0.4 px) when you
move your finger slowly. The OS only accepts whole pixels, so we keep the
leftover fraction and add it to the next movement. Without this, slow precise
movements would be lost entirely.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Protocol

from .protocol import (
    CHARACTER_KEYS,
    ButtonDown,
    ButtonUp,
    Click,
    Command,
    KeyPress,
    Move,
    Scroll,
    Text,
)

logger = logging.getLogger(__name__)


class InputController(Protocol):
    """Anything that can inject mouse and keyboard input."""

    def move(self, dx: float, dy: float) -> None: ...
    def click(self, button: str, count: int) -> None: ...
    def press_button(self, button: str) -> None: ...
    def release_button(self, button: str) -> None: ...
    def scroll(self, dx: float, dy: float) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press_key(self, key: str, modifiers: tuple[str, ...]) -> None: ...


def execute(controller: InputController, command: Command) -> None:
    """Perform one input command. Non-input commands (auth, ping) are ignored."""
    match command:
        case Move(dx=dx, dy=dy):
            controller.move(dx, dy)
        case Click(button=button, count=count):
            controller.click(button, count)
        case ButtonDown(button=button):
            controller.press_button(button)
        case ButtonUp(button=button):
            controller.release_button(button)
        case Scroll(dx=dx, dy=dy):
            controller.scroll(dx, dy)
        case Text(text=text):
            controller.type_text(text)
        case KeyPress(key=key, modifiers=modifiers):
            controller.press_key(key, modifiers)
        case _:
            pass


def split_subpixel(remainder: float, delta: float) -> tuple[int, float]:
    """
    Combine a leftover fraction with a new delta.

    Returns (whole_pixels_to_move_now, new_leftover). `int()` truncates toward
    zero, so the leftover always has the same sign as the movement.
    """
    total = remainder + delta
    whole = int(total)
    return whole, total - whole


class FakeController:
    """Test double: remembers every call instead of touching the real mouse."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def move(self, dx: float, dy: float) -> None:
        self.calls.append(("move", dx, dy))

    def click(self, button: str, count: int) -> None:
        self.calls.append(("click", button, count))

    def press_button(self, button: str) -> None:
        self.calls.append(("press_button", button))

    def release_button(self, button: str) -> None:
        self.calls.append(("release_button", button))

    def scroll(self, dx: float, dy: float) -> None:
        self.calls.append(("scroll", dx, dy))

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text))

    def press_key(self, key: str, modifiers: tuple[str, ...]) -> None:
        self.calls.append(("press_key", key, modifiers))


def build_key_map(keyboard_module: Any, use_virtual_keys: bool) -> dict[str, Any]:
    """
    Map protocol key names ("enter", "f5", "c", …) to pynput key objects.

    Letters/digits: on Windows we use *virtual-key codes* (VK 0x41 = "A") rather
    than characters, because shortcuts like Ctrl+C only work when the real key
    is pressed — typing the character "c" via Unicode injection would not
    trigger the shortcut.
    """
    key = keyboard_module.Key
    named = {
        "esc": "esc", "tab": "tab", "enter": "enter", "backspace": "backspace",
        "delete": "delete", "insert": "insert", "space": "space",
        "home": "home", "end": "end", "page_up": "page_up", "page_down": "page_down",
        "up": "up", "down": "down", "left": "left", "right": "right",
        "caps_lock": "caps_lock", "print_screen": "print_screen", "menu": "menu",
        "win": "cmd",
        "volume_up": "media_volume_up", "volume_down": "media_volume_down",
        "volume_mute": "media_volume_mute",
        "media_play_pause": "media_play_pause", "media_next": "media_next",
        "media_previous": "media_previous",
        **{f"f{i}": f"f{i}" for i in range(1, 13)},
    }  # fmt: skip

    mapping: dict[str, Any] = {}
    for protocol_name, pynput_name in named.items():
        value = getattr(key, pynput_name, None)  # some keys don't exist on every OS
        if value is not None:
            mapping[protocol_name] = value

    key_code = keyboard_module.KeyCode
    for char in CHARACTER_KEYS:
        mapping[char] = (
            key_code.from_vk(ord(char.upper())) if use_virtual_keys else key_code.from_char(char)
        )
    return mapping


class PynputController:
    """Real input via pynput. Controllers can be injected for testing."""

    def __init__(self, mouse_controller: Any = None, keyboard_controller: Any = None) -> None:
        # Imported here (not at the top) so the rest of the app — and the test
        # suite — can be imported on machines without a desktop session.
        from pynput import keyboard, mouse

        self._mouse = mouse.Controller() if mouse_controller is None else mouse_controller
        self._keyboard = (
            keyboard.Controller() if keyboard_controller is None else keyboard_controller
        )
        self._buttons = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }
        self._keys = build_key_map(keyboard, use_virtual_keys=sys.platform == "win32")
        self._modifiers = {
            "ctrl": keyboard.Key.ctrl,
            "alt": keyboard.Key.alt,
            "shift": keyboard.Key.shift,
            "win": keyboard.Key.cmd,
        }
        self._remainder = (0.0, 0.0)

    def move(self, dx: float, dy: float) -> None:
        step_x, rest_x = split_subpixel(self._remainder[0], dx)
        step_y, rest_y = split_subpixel(self._remainder[1], dy)
        self._remainder = (rest_x, rest_y)
        if step_x or step_y:
            self._mouse.move(step_x, step_y)

    def click(self, button: str, count: int) -> None:
        self._mouse.click(self._buttons[button], count)

    def press_button(self, button: str) -> None:
        self._mouse.press(self._buttons[button])

    def release_button(self, button: str) -> None:
        self._mouse.release(self._buttons[button])

    def scroll(self, dx: float, dy: float) -> None:
        # pynput multiplies by the OS wheel step (120 on Windows), so fractional
        # values give smooth scrolling in apps that support it.
        self._mouse.scroll(dx, dy)

    def type_text(self, text: str) -> None:
        self._keyboard.type(text)

    def press_key(self, key: str, modifiers: tuple[str, ...]) -> None:
        target = self._keys.get(key)
        if target is None:
            logger.warning("Key %r is not available on this platform", key)
            return
        pressed: list[Any] = []
        try:
            for name in modifiers:
                modifier = self._modifiers[name]
                self._keyboard.press(modifier)
                pressed.append(modifier)
            self._keyboard.press(target)
            self._keyboard.release(target)
        finally:
            # Always release modifiers — even if something failed — so Ctrl
            # or Alt never gets "stuck" down on the PC.
            for modifier in reversed(pressed):
                self._keyboard.release(modifier)
