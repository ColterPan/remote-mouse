"""Tests for input_controller.py — command routing and the pynput wrapper.

PynputController is tested with *mock* mouse/keyboard objects, so running the
tests never moves your real cursor or presses real keys.
"""

from unittest.mock import MagicMock, call

import pytest
from pynput import keyboard, mouse

from remote_mouse.input_controller import (
    FakeController,
    PynputController,
    build_key_map,
    execute,
    split_subpixel,
)
from remote_mouse.protocol import (
    ALLOWED_KEYS,
    Auth,
    ButtonDown,
    ButtonUp,
    Click,
    KeyPress,
    Move,
    Ping,
    Scroll,
    Text,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (Move(3, -4), ("move", 3, -4)),
        (Click("right", 2), ("click", "right", 2)),
        (ButtonDown("left"), ("press_button", "left")),
        (ButtonUp("left"), ("release_button", "left")),
        (Scroll(0, -1.5), ("scroll", 0, -1.5)),
        (Text("hi"), ("type_text", "hi")),
        (KeyPress("c", ("ctrl",)), ("press_key", "c", ("ctrl",))),
    ],
)
def test_execute_routes_commands(command, expected):
    fake = FakeController()
    execute(fake, command)
    assert fake.calls == [expected]


def test_execute_ignores_non_input_commands():
    fake = FakeController()
    execute(fake, Ping())
    execute(fake, Auth("x", 1))
    assert fake.calls == []


class TestSplitSubpixel:
    def test_whole_numbers_pass_through(self):
        assert split_subpixel(0.0, 5.0) == (5, 0.0)

    def test_fractions_accumulate(self):
        whole, rest = split_subpixel(0.0, 0.4)
        assert whole == 0
        whole, rest = split_subpixel(rest, 0.4)
        assert whole == 0
        whole, rest = split_subpixel(rest, 0.4)
        assert whole == 1
        assert rest == pytest.approx(0.2)

    def test_negative_movement_keeps_sign(self):
        whole, rest = split_subpixel(0.0, -1.75)
        assert whole == -1
        assert rest == pytest.approx(-0.75)


def test_every_allowed_key_has_a_mapping_on_this_platform():
    mapping = build_key_map(keyboard, use_virtual_keys=True)
    assert set(ALLOWED_KEYS) <= set(mapping)


def test_letters_use_virtual_key_codes_on_windows():
    mapping = build_key_map(keyboard, use_virtual_keys=True)
    assert mapping["c"].vk == ord("C")


def test_letters_use_characters_elsewhere():
    mapping = build_key_map(keyboard, use_virtual_keys=False)
    assert mapping["c"].char == "c"


@pytest.fixture
def controller():
    fake_mouse = MagicMock()
    fake_keyboard = MagicMock()
    return PynputController(fake_mouse, fake_keyboard), fake_mouse, fake_keyboard


class TestPynputController:
    def test_move_sends_whole_pixels_and_keeps_remainder(self, controller):
        ctl, fake_mouse, _ = controller
        ctl.move(0.6, 0.0)
        fake_mouse.move.assert_not_called()
        ctl.move(0.6, 2.0)
        fake_mouse.move.assert_called_once_with(1, 2)

    def test_click_press_release(self, controller):
        ctl, fake_mouse, _ = controller
        ctl.click("right", 2)
        ctl.press_button("left")
        ctl.release_button("left")
        assert fake_mouse.click.call_args == call(mouse.Button.right, 2)
        fake_mouse.press.assert_called_once_with(mouse.Button.left)
        fake_mouse.release.assert_called_once_with(mouse.Button.left)

    def test_scroll_sends_exact_wheel_units(self, controller):
        ctl, fake_mouse, _ = controller
        ctl.scroll(0.5, -1.0)
        dx, dy = fake_mouse.scroll.call_args.args
        # pynput does int(value * 120); that must land exactly on our units.
        assert (int(dx * 120), int(dy * 120)) == (60, -120)

    def test_tiny_scrolls_accumulate_instead_of_being_lost(self, controller):
        ctl, fake_mouse, _ = controller
        for _ in range(10):
            ctl.scroll(0.0, 0.004)  # 0.48 units each: too small alone
        total = sum(int(c.args[1] * 120) for c in fake_mouse.scroll.call_args_list)
        assert total == 4  # 10 × 0.48 = 4.8 → 4 whole units sent, 0.8 carried

    def test_no_scroll_call_when_nothing_accumulated(self, controller):
        ctl, fake_mouse, _ = controller
        ctl.scroll(0.0, 0.001)
        fake_mouse.scroll.assert_not_called()


@pytest.mark.parametrize("units", [1, 2, 3, 7, 59, 60, 119, 120, 121, 240, 1199, 2400])
def test_wheel_unit_conversion_is_exact(units):
    from remote_mouse.input_controller import wheel_units_to_notches

    assert int(wheel_units_to_notches(units) * 120) == units
    assert int(wheel_units_to_notches(-units) * 120) == -units
    assert wheel_units_to_notches(0) == 0.0

    def test_type_text(self, controller):
        ctl, _, fake_keyboard = controller
        ctl.type_text("hello")
        fake_keyboard.type.assert_called_once_with("hello")

    def test_shortcut_presses_and_releases_in_order(self, controller):
        ctl, _, fake_keyboard = controller
        ctl.press_key("c", ("ctrl", "shift"))
        c_key = keyboard.KeyCode.from_vk(ord("C"))
        assert fake_keyboard.mock_calls == [
            call.press(keyboard.Key.ctrl),
            call.press(keyboard.Key.shift),
            call.press(c_key),
            call.release(c_key),
            call.release(keyboard.Key.shift),
            call.release(keyboard.Key.ctrl),
        ]

    def test_modifiers_are_released_even_if_key_press_fails(self, controller):
        ctl, _, fake_keyboard = controller

        def press(key):
            if key == keyboard.Key.enter:
                raise RuntimeError("boom")

        fake_keyboard.press.side_effect = press
        with pytest.raises(RuntimeError):
            ctl.press_key("enter", ("alt",))
        fake_keyboard.release.assert_called_once_with(keyboard.Key.alt)

    def test_unknown_key_is_ignored(self, controller):
        ctl, _, fake_keyboard = controller
        ctl.press_key("not-a-key", ())
        fake_keyboard.press.assert_not_called()
