"""
End-to-end user tests: a phone-sized Chrome uses the real remote page against
the real server. Each test is one thing a user does, checked at the "PC" end.
"""

from __future__ import annotations

import statistics
import time

from conftest import (
    DEMO_PC_NAME,
    TOKEN,
    Env,
    Touch,
    center_of,
    mock_native_bridge,
    new_phone_page,
    wait_until,
)


def names(env: Env) -> list[str]:
    return [c[0] for c in env.calls]


# --- Connecting -------------------------------------------------------------


def test_connects_and_shows_pc_name(phone, env: Env):
    assert phone.locator("#status-text").inner_text() == DEMO_PC_NAME
    assert phone.locator("#banner").is_hidden()
    assert phone.url.endswith("/"), "pairing token removed from the address bar"


def test_wrong_token_shows_pairing_screen(browser, env: Env):
    page = new_phone_page(browser)
    page.goto(f"{env.base}/#t=WrongTokenWrongTokenXX&fp=x")
    page.wait_for_selector("#pair-screen:not([hidden])", timeout=10_000)
    assert "no longer accepts" in page.locator("#pair-reason").inner_text()
    page.context.close()


def test_reconnects_by_itself_after_pc_restart(phone, env: Env):
    env.restart()
    phone.wait_for_selector('#status[data-state="connected"]', timeout=15_000)
    Touch(phone).tap(*center_of(phone, "#touchpad"))
    wait_until(lambda: ("click", "left", 1) in env.calls, what="click after reconnect")


def test_banner_offers_retry_while_pc_is_off(phone, env: Env):
    env.server.stop()
    phone.wait_for_selector("#banner:not([hidden])", timeout=15_000)
    assert "Can't reach" in phone.locator("#banner-text").inner_text()
    assert phone.locator("#banner-retry").is_visible()
    env.restart()
    phone.locator("#banner-retry").click()
    phone.wait_for_selector('#status[data-state="connected"]', timeout=15_000)
    assert phone.locator("#banner").is_hidden()


# --- Touchpad ----------------------------------------------------------------


def test_tap_is_left_click(phone, env: Env):
    Touch(phone).tap(*center_of(phone, "#touchpad"))
    wait_until(lambda: ("click", "left", 1) in env.calls, what="left click")


def test_two_finger_tap_is_right_click(phone, env: Env):
    x, y = center_of(phone, "#touchpad")
    touch = Touch(phone)
    touch.start((x - 30, y), (x + 30, y))
    touch.end()
    wait_until(lambda: ("click", "right", 1) in env.calls, what="right click")
    assert ("click", "left", 1) not in env.calls


def test_swipe_moves_pointer_smoothly(phone, env: Env):
    x, y = center_of(phone, "#touchpad")
    touch = Touch(phone)
    injected = touch.swipe([(x - 100, y)], [(x + 100, y)], steps=30, frame_ms=8)
    touch.end()
    wait_until(lambda: names(env).count("move") >= 24, what="a move for (nearly) every touch")
    moves = [(c, t) for c, t in zip(env.calls, env.calls.times, strict=True) if c[0] == "move"]
    total_dx = sum(c[1] for c, _ in moves)
    assert total_dx > 200, f"pointer travelled {total_dx:.0f}px"
    assert all(c[2] == 0 for c, _ in moves), "horizontal swipe stays horizontal"
    # Latency: time from injecting a touch to the PC performing the move.
    lags = []
    for _, arrived in moves:
        earlier = [t for t in injected if t <= arrived]
        if earlier:
            lags.append(arrived - earlier[-1])
    assert statistics.median(lags) < 0.015, (
        f"median touch→PC lag {statistics.median(lags) * 1000:.1f} ms"
    )


def test_two_finger_scroll_then_momentum(phone, env: Env):
    x, y = center_of(phone, "#touchpad")
    touch = Touch(phone)
    touch.swipe(
        [(x - 30, y + 150), (x + 30, y + 150)],
        [(x - 30, y - 150), (x + 30, y - 150)],
        steps=10,
        frame_ms=8,
    )
    lifted = time.perf_counter()
    touch.end()
    time.sleep(0.6)
    scrolls = [(c, t) for c, t in zip(env.calls, env.calls.times, strict=True) if c[0] == "scroll"]
    assert scrolls, "two-finger slide scrolls"
    assert sum(c[2] for c, _ in scrolls) < 0, "fingers up → page scrolls down (natural)"
    after = [t for _, t in scrolls if t > lifted + 0.1]
    assert after, "keeps gliding after the fingers lift (momentum)"
    assert not any(c[0] == "move" for c in env.calls), "scrolling never moves the pointer"


def test_momentum_can_be_turned_off(browser, env: Env):
    page = new_phone_page(browser)
    page.goto(f"{env.base}/#t={TOKEN}&fp=x")
    page.evaluate(
        "localStorage.setItem('remote-mouse.settings.v1', JSON.stringify({momentum:false, tipsSeen:true}))"
    )
    page.reload()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    x, y = center_of(page, "#touchpad")
    touch = Touch(page)
    touch.swipe(
        [(x - 30, y + 150), (x + 30, y + 150)],
        [(x - 30, y - 150), (x + 30, y - 150)],
        steps=10,
        frame_ms=8,
    )
    lifted = time.perf_counter()
    touch.end()
    time.sleep(0.5)
    assert not [
        t
        for c, t in zip(env.calls, env.calls.times, strict=True)
        if c[0] == "scroll" and t > lifted + 0.1
    ]
    page.context.close()


def test_tap_then_drag_holds_left_button(phone, env: Env):
    x, y = center_of(phone, "#touchpad")
    touch = Touch(phone)
    touch.tap(x, y)
    phone.wait_for_timeout(80)
    touch.swipe([(x, y)], [(x + 120, y + 40)], steps=12)
    touch.end()
    wait_until(lambda: ("release_button", "left") in env.calls, what="drag release")
    sequence = [n for n in names(env) if n in ("press_button", "release_button", "click")]
    assert sequence == ["press_button", "release_button"], f"no stray click: {sequence}"


def test_holding_left_button(phone, env: Env):
    x, y = center_of(phone, '[data-button="left"]')
    touch = Touch(phone)
    touch.start((x, y))
    wait_until(lambda: ("press_button", "left") in env.calls, what="left down")
    touch.end()
    wait_until(lambda: ("release_button", "left") in env.calls, what="left up")


# --- Keyboard & panels ---------------------------------------------------------


def test_typing_and_enter(phone, env: Env):
    phone.locator("#keyboard-btn").click()
    phone.keyboard.type("Hi!")
    phone.keyboard.press("Enter")
    wait_until(lambda: ("press_key", "enter", ()) in env.calls, what="enter")
    typed = "".join(c[1] for c in env.calls if c[0] == "type_text")
    assert typed == "Hi!"


def test_shortcut_and_media_buttons(phone, env: Env):
    phone.locator('.tool[data-panel="panel-shortcuts"]').click()
    phone.locator('.chip-btn:has-text("Copy")').click()
    phone.locator('.tool[data-panel="panel-media"]').click()
    phone.locator('[data-key="media_play_pause"]').click()
    wait_until(lambda: ("press_key", "media_play_pause", ()) in env.calls, what="media key")
    assert ("press_key", "c", ("ctrl",)) in env.calls


def test_sticky_ctrl_then_letter(phone, env: Env):
    phone.locator("#keyboard-btn").click()
    phone.locator('#panel-keyboard [data-mod="ctrl"]').click()
    phone.keyboard.type("v")
    wait_until(lambda: ("press_key", "v", ("ctrl",)) in env.calls, what="Ctrl+V")


# --- Settings ------------------------------------------------------------------


def test_speed_preset_is_remembered(phone, env: Env):
    phone.locator("#settings-btn").click()
    phone.locator('[data-preset="fast"]').click()
    assert "2.4" in phone.locator("#sensitivity-out").inner_text()
    phone.locator('#settings button[type="submit"]').click()
    phone.reload()
    phone.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    phone.locator("#settings-btn").click()
    assert phone.locator('[data-preset="fast"]').get_attribute("class") == "active"


def test_tips_show_once(browser, env: Env):
    page = new_phone_page(browser)
    page.goto(f"{env.base}/#t={TOKEN}&fp=x")
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    assert page.locator("#tips").is_visible()
    page.locator("#tips-ok").click()
    page.reload()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    assert page.locator("#tips").is_hidden()
    page.context.close()


# --- Android-app mode (native bridge) -------------------------------------------


def test_app_first_launch_pairs_then_relaunch_auto_connects(browser, env: Env):
    page = new_phone_page(browser, init_script=mock_native_bridge(env))
    page.goto(f"{env.base}/")
    page.wait_for_selector("#pair-screen:not([hidden])", timeout=10_000)
    assert page.locator("#pair-title").inner_text() == "Add your PC"
    assert page.locator("#pair-scan").is_visible()

    page.locator("#pair-scan").click()  # the app's QR scanner (mocked)
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    assert page.locator("#status-text").inner_text() == DEMO_PC_NAME

    # Relaunch the app: it must connect on its own — NO QR scan.
    page.reload()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    assert page.locator("#pair-screen").is_hidden()
    Touch(page).tap(*center_of(page, "#touchpad"))
    wait_until(lambda: ("click", "left", 1) in env.calls, what="click from the app")

    # The PC list never exposes the token to the page.
    assert TOKEN not in page.content()
    page.context.close()


def test_app_forgetting_current_pc_goes_to_pc_list(browser, env: Env):
    page = new_phone_page(browser, init_script=mock_native_bridge(env))
    page.on("dialog", lambda dialog: dialog.accept())  # "Forget Demo-PC?" → Yes
    page.goto(f"{env.base}/")
    page.wait_for_selector("#pair-scan:visible", timeout=10_000)
    page.locator("#pair-scan").click()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    page.locator("#settings-btn").click()
    page.locator("#forget-pc").click()
    page.wait_for_selector("#pair-screen:not([hidden])", timeout=5_000)
    assert page.locator("#pair-scan").is_visible(), "offers to pair again"
    assert page.locator("#status-text").inner_text() == "Not connected"
    page.context.close()


def test_app_switch_pc_screen_lists_saved_pcs(browser, env: Env):
    page = new_phone_page(browser, init_script=mock_native_bridge(env))
    page.goto(f"{env.base}/")
    page.wait_for_selector("#pair-scan:visible", timeout=10_000)
    page.locator("#pair-scan").click()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    page.locator("#status").click()  # tapping the PC chip opens "Your PCs"
    page.wait_for_selector("#pair-screen:not([hidden])")
    assert page.locator("#pair-title").inner_text() == "Your PCs"
    assert page.locator(".pc-name").first.inner_text() == DEMO_PC_NAME
    page.locator(".pc-main").first.click()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    page.context.close()
