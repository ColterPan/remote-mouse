"""
Generates the README screenshots from the REAL UI (skipped unless asked):

    set RM_SCREENSHOTS=1 && pytest e2e/test_screenshots.py      (Windows cmd)
    $env:RM_SCREENSHOTS=1; pytest e2e/test_screenshots.py      (PowerShell)

Privacy: only demo data appears — PC name "Demo-PC", address 192.168.1.20,
and a throwaway test token. No real names, addresses or pairing codes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import TOKEN, Env, mock_native_bridge, new_phone_page

OUT = Path(__file__).resolve().parents[2] / "docs" / "images"

pytestmark = pytest.mark.skipif(not os.environ.get("RM_SCREENSHOTS"), reason="set RM_SCREENSHOTS=1")


def shoot(page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(1200)  # let animations and transitions settle
    page.screenshot(path=str(OUT / f"{name}.png"))


def connected_page(browser, env: Env, tips: bool = False, viewport=None):
    page = new_phone_page(browser, viewport=viewport, scale=2)
    page.goto(f"{env.base}/#t={TOKEN}&fp=x")
    if not tips:
        page.evaluate(
            "localStorage.setItem('remote-mouse.settings.v1', JSON.stringify({tipsSeen:true}))"
        )
        page.reload()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    return page


def test_phone_screens(browser, env: Env):
    page = connected_page(browser, env, tips=True)
    shoot(page, "phone-touchpad")

    page.locator("#tips-ok").click()
    page.locator('.tool[data-panel="panel-keys"]').click()
    shoot(page, "phone-keys")

    page.locator('.tool[data-panel="panel-shortcuts"]').click()
    shoot(page, "phone-shortcuts")

    page.locator('.tool[data-panel="panel-media"]').click()
    shoot(page, "phone-media")

    page.locator('.tool[data-panel="panel-media"]').click()
    page.locator("#settings-btn").click()
    shoot(page, "phone-settings")
    page.context.close()


def test_landscape(browser, env: Env):
    page = connected_page(browser, env, viewport={"width": 892, "height": 412})
    page.locator('.tool[data-panel="panel-shortcuts"]').click()
    shoot(page, "phone-landscape")
    page.context.close()


def test_app_screens(browser, env: Env):
    page = new_phone_page(browser, init_script=mock_native_bridge(env), scale=2)
    page.goto(f"{env.base}/")
    page.wait_for_selector("#pair-scan:visible", timeout=10_000)
    shoot(page, "app-add-pc")

    page.locator("#pair-scan").click()
    page.wait_for_selector('#status[data-state="connected"]', timeout=10_000)
    page.locator("#tips-ok").click()
    page.locator("#status").click()
    page.wait_for_selector("#pair-screen:not([hidden])")
    shoot(page, "app-your-pcs")
    page.context.close()


def test_offline_banner(browser, env: Env):
    page = connected_page(browser, env)
    env.server.stop()
    page.wait_for_selector("#banner:not([hidden])", timeout=15_000)
    shoot(page, "phone-offline")
    env.restart()
    page.context.close()
