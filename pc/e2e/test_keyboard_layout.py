"""
E2E: the touchpad layout while the phone keyboard opens and closes.

A real phone keyboard can't be shown in headless Chrome, so we do what the
keyboard does to the page: shrink the visible area after the keyboard panel
is opened, then grow it back. Checked on a big phone, a small phone and in
landscape. After every change the touchpad must still be usable, every control
must be on-screen (not under the keyboard), and the page must not have
scrolled.
"""

from __future__ import annotations

import pytest
from conftest import TOKEN, Env, Touch, center_of, new_phone_page, wait_until

LAYOUT_JS = """() => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el || el.hidden) return null;
    const b = el.getBoundingClientRect();
    return { top: b.top, bottom: b.bottom, height: b.height };
  };
  return {
    scrollY: window.scrollY,
    innerH: window.innerHeight,
    pad: box('#touchpad'),
    toolbar: box('.toolbar'),
    panel: box('#panel-keyboard'),
    buttons: box('.mouse-buttons'),
    kbOpen: document.getElementById('app').classList.contains('kb-open'),
    kbActive: document.getElementById('keyboard-btn').classList.contains('active'),
  };
}"""

MIN_PAD_PX = 96

BOXES_JS = """() => ['#app', '.pad-area', '#touchpad', '#scroll-strip', '.controls', '#panel-keyboard']
  .map((s) => { const b = document.querySelector(s).getBoundingClientRect();
                return `${s}:${Math.round(b.x)},${Math.round(b.y)} ${Math.round(b.width)}x${Math.round(b.height)}`; })
  .join(' | ')"""


def open_page(browser, env: Env, width: int, height: int):
    page = new_phone_page(browser, viewport={"width": width, "height": height})
    page.goto(f"{env.base}/#t={TOKEN}&fp=x")
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    if page.locator("#tips-ok").is_visible():
        page.locator("#tips-ok").click()
    return page


def layout(page) -> dict:
    return page.evaluate(LAYOUT_JS)


def assert_usable(page, *, keyboard_panel: bool) -> dict:
    """Everything a user needs is fully on-screen and the page hasn't moved."""
    state = layout(page)
    assert state["scrollY"] == 0, f"page scrolled: {state}"
    pad = state["pad"]
    assert pad["height"] >= MIN_PAD_PX, f"touchpad too small: {state}"
    assert pad["top"] >= 0 and pad["bottom"] <= state["innerH"], f"touchpad off-screen: {state}"
    for part in ("toolbar", "buttons") + (("panel",) if keyboard_panel else ()):
        box = state[part]
        assert box is not None, f"{part} missing: {state}"
        assert box["bottom"] <= state["innerH"] + 0.5, f"{part} under the keyboard: {state}"
    return state


def show_keyboard(page, width: int, visible_height: int) -> None:
    page.locator("#keyboard-btn").click()
    page.set_viewport_size({"width": width, "height": visible_height})
    page.wait_for_selector("#app.kb-open", state="attached")


def swipe_moves_pointer(page, env: Env) -> None:
    before = len(env.calls)
    x, y = center_of(page, "#touchpad")
    touch = Touch(page)
    touch.swipe([(x - 60, y)], [(x + 60, y)], steps=20)
    touch.end()
    wait_until(
        lambda: sum(c[1] for c in env.calls[before:] if c[0] == "move") > 100,
        what=lambda: (
            f"pointer moves after the keyboard opened; at ({x:.0f},{y:.0f}) got "
            f"{env.calls[before:]}; boxes {page.evaluate(BOXES_JS)}"
        ),
    )
    assert all(c[2] == 0 for c in env.calls[before:] if c[0] == "move")


# Pixel 7 (412×915) with a typical keyboard, a tall keyboard, and a small
# 360×640 phone where space is tightest.
@pytest.mark.parametrize(
    ("width", "height", "keyboard"),
    [(412, 915, 330), (412, 915, 420), (360, 640, 290)],
)
def test_keyboard_open_keeps_touchpad_usable(browser, env: Env, width, height, keyboard):
    page = open_page(browser, env, width, height)
    full = assert_usable(page, keyboard_panel=False)["pad"]["height"]

    show_keyboard(page, width, height - keyboard)
    assert_usable(page, keyboard_panel=True)
    swipe_moves_pointer(page, env)

    # Keyboard hidden (Android back button): full-size pad, panel closed.
    page.set_viewport_size({"width": width, "height": height})
    page.wait_for_selector("#app:not(.kb-open)", state="attached")
    state = assert_usable(page, keyboard_panel=False)
    assert abs(state["pad"]["height"] - full) < 1, "touchpad back to full size"
    assert state["panel"] is None and not state["kbActive"], (
        "keyboard panel closed with the keyboard"
    )
    page.context.close()


def test_rapid_keyboard_toggles_leave_layout_intact(browser, env: Env):
    page = open_page(browser, env, 412, 915)
    original = layout(page)["pad"]
    for _ in range(5):
        show_keyboard(page, 412, 560)
        assert_usable(page, keyboard_panel=True)
        page.locator("#keyboard-btn").click()  # toggle off from the toolbar
        page.set_viewport_size({"width": 412, "height": 915})
        page.wait_for_selector("#app:not(.kb-open)", state="attached")
    state = assert_usable(page, keyboard_panel=False)
    assert state["pad"] == original
    swipe_moves_pointer(page, env)
    page.context.close()


def test_keyboard_in_landscape(browser, env: Env):
    page = open_page(browser, env, 915, 412)
    show_keyboard(page, 915, 412 - 230)
    state = assert_usable(page, keyboard_panel=False)  # controls column scrolls
    assert page.locator(".topbar").is_hidden(), "top bar hidden to give the pad room"
    assert state["pad"]["bottom"] <= state["innerH"]
    swipe_moves_pointer(page, env)
    page.context.close()


def test_typing_still_works_in_compact_mode(browser, env: Env):
    page = open_page(browser, env, 412, 915)
    show_keyboard(page, 412, 560)
    page.keyboard.type("ok")
    wait_until(
        lambda: "".join(c[1] for c in env.calls if c[0] == "type_text") == "ok",
        what="typed text",
    )
    page.context.close()
