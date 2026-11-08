"""Tests for protocol.py — the validator every network message passes through."""

import json

import pytest

from remote_mouse.protocol import (
    ALLOWED_KEYS,
    MAX_MESSAGE_BYTES,
    MAX_MOVE_DELTA,
    MAX_SCROLL_DELTA,
    MAX_TEXT_LENGTH,
    Auth,
    ButtonDown,
    ButtonUp,
    Click,
    KeyPress,
    Move,
    Ping,
    ProtocolError,
    Scroll,
    Text,
    parse_message,
)


def msg(**fields) -> str:
    return json.dumps(fields)


class TestValidMessages:
    def test_auth(self):
        assert parse_message(msg(t="auth", token="abc", v=1)) == Auth("abc", 1)

    def test_ping(self):
        assert parse_message(msg(t="ping")) == Ping()

    def test_move_accepts_floats_and_ints(self):
        assert parse_message(msg(t="move", dx=1.5, dy=-2)) == Move(1.5, -2.0)

    def test_click_defaults_to_single_left(self):
        assert parse_message(msg(t="click")) == Click("left", 1)

    def test_double_right_click(self):
        assert parse_message(msg(t="click", b="right", n=2)) == Click("right", 2)

    def test_button_down_and_up(self):
        assert parse_message(msg(t="down", b="middle")) == ButtonDown("middle")
        assert parse_message(msg(t="up", b="middle")) == ButtonUp("middle")

    def test_scroll_axes_default_to_zero(self):
        assert parse_message(msg(t="scroll", dy=-1.25)) == Scroll(0.0, -1.25)

    def test_text(self):
        assert parse_message(msg(t="text", s="héllo 👋")) == Text("héllo 👋")

    def test_key_with_modifiers_is_ordered_and_deduplicated(self):
        result = parse_message(msg(t="key", k="c", mods=["shift", "ctrl", "ctrl"]))
        assert result == KeyPress("c", ("ctrl", "shift"))

    def test_bytes_input_is_accepted(self):
        assert parse_message(b'{"t":"ping"}') == Ping()


class TestClamping:
    def test_move_is_clamped(self):
        result = parse_message(msg(t="move", dx=10**9, dy=-(10**9)))
        assert result == Move(MAX_MOVE_DELTA, -MAX_MOVE_DELTA)

    def test_scroll_is_clamped(self):
        result = parse_message(msg(t="scroll", dx=999, dy=-999))
        assert result == Scroll(MAX_SCROLL_DELTA, -MAX_SCROLL_DELTA)


class TestTextSanitizing:
    def test_control_characters_are_removed(self):
        assert parse_message(msg(t="text", s="a\x00b\x1bc\x7f")) == Text("abc")

    def test_newlines_and_tabs_are_kept_and_normalised(self):
        assert parse_message(msg(t="text", s="a\r\nb\rc\td")) == Text("a\nb\nc\td")

    def test_text_that_is_only_control_chars_is_rejected(self):
        with pytest.raises(ProtocolError):
            parse_message(msg(t="text", s="\x00\x01"))

    def test_text_too_long_is_rejected(self):
        with pytest.raises(ProtocolError):
            parse_message(msg(t="text", s="x" * (MAX_TEXT_LENGTH + 1)))


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2, 3]",
        '"just a string"',
        msg(t="explode"),
        msg(dx=1, dy=2),  # missing type
        msg(t="move", dx="1", dy=2),  # string instead of number
        msg(t="move", dx=True, dy=2),  # bool is not a number here
        msg(t="move", dx=1),  # missing dy
        '{"t":"move","dx":NaN,"dy":0}',
        '{"t":"move","dx":Infinity,"dy":0}',
        msg(t="click", b="side"),
        msg(t="click", n=0),
        msg(t="click", n=4),
        msg(t="click", n=True),
        msg(t="key", k="rm -rf"),
        msg(t="key", k="a", mods=["hyper"]),
        msg(t="key", k="a", mods="ctrl"),
        msg(t="key", k="a", mods=["ctrl"] * 5),
        msg(t="text", s=42),
        msg(t="auth", token="", v=1),
        msg(t="auth", token="x" * 300, v=1),
        msg(t="auth", token="abc", v="1"),
        msg(t="auth", token="abc", v=True),
    ],
)
def test_invalid_messages_are_rejected(raw):
    with pytest.raises(ProtocolError):
        parse_message(raw)


def test_oversized_message_is_rejected():
    with pytest.raises(ProtocolError):
        parse_message(msg(t="text", s="a" * MAX_MESSAGE_BYTES))


def test_oversized_bytes_are_rejected():
    with pytest.raises(ProtocolError):
        parse_message(b"x" * (MAX_MESSAGE_BYTES + 1))


def test_invalid_utf8_bytes_are_rejected():
    with pytest.raises(ProtocolError):
        parse_message(b"\xff\xfe")


def test_shortcut_letters_and_function_keys_are_allowed():
    for key in ("a", "z", "0", "9", "f1", "f12", "enter", "media_play_pause"):
        assert key in ALLOWED_KEYS
