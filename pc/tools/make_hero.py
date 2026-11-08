"""
make_hero.py — Builds the README banner (docs/images/hero.png) from the real
screenshots, laid out with HTML/CSS and rendered by headless Chromium.

Run after the screenshots exist (pc folder):   python tools/make_hero.py
"""

from __future__ import annotations

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"
LOGO = ROOT / "pc" / "remote_mouse" / "web" / "icons" / "icon-512.png"


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> None:
    html = f"""
<html><head><style>
  body {{ margin:0; width:1600px; height:820px; font-family: 'Segoe UI', system-ui, sans-serif;
         background: radial-gradient(circle at 15% 20%, #2b2f8f 0%, transparent 45%),
                     radial-gradient(circle at 90% 90%, #4a2a9a 0%, transparent 40%), #0d0f17;
         color:#eef0f8; overflow:hidden; position:relative; }}
  .text {{ position:absolute; left:90px; top:150px; width:560px; }}
  .logo {{ width:112px; height:112px; border-radius:28px; box-shadow:0 18px 50px rgba(91,92,255,.45); }}
  h1 {{ font-size:72px; margin:26px 0 10px; letter-spacing:-1px; }}
  p {{ font-size:26px; line-height:1.45; color:#b8c0d8; margin:0 0 28px; }}
  .pills span {{ display:inline-block; margin:0 10px 12px 0; padding:10px 18px; border-radius:999px;
                 background:rgba(91,124,255,.16); border:1px solid rgba(91,124,255,.45); font-size:19px; }}
  .phone {{ position:absolute; width:300px; border-radius:44px; padding:12px; background:#05060a;
            box-shadow:0 30px 80px rgba(0,0,0,.6), inset 0 0 0 2px #2a2f45; }}
  .phone img {{ width:100%; border-radius:34px; display:block; }}
  .p1 {{ left:760px; top:70px; transform:rotate(-4deg); }}
  .p2 {{ left:1080px; top:40px; transform:rotate(3deg); }}
  .pc {{ position:absolute; left:1240px; top:430px; width:330px; border-radius:10px;
         box-shadow:0 30px 80px rgba(0,0,0,.6); }}
</style></head><body>
  <div class="text">
    <img class="logo" src="{data_uri(LOGO)}">
    <h1>Remote Mouse</h1>
    <p>Your phone becomes your PC's touchpad &amp; keyboard.<br>Free, open source, no ads, encrypted.</p>
    <div class="pills"><span>Android app</span><span>Windows</span><span>Auto-connect</span><span>Wi-Fi</span></div>
  </div>
  <div class="phone p1"><img src="{data_uri(IMAGES / "phone-touchpad.png")}"></div>
  <div class="phone p2"><img src="{data_uri(IMAGES / "phone-shortcuts.png")}"></div>
  <img class="pc" src="{data_uri(IMAGES / "pc-pairing-window.png")}">
</body></html>"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 820}, device_scale_factor=1)
        page.set_content(html)
        page.wait_for_timeout(300)
        page.screenshot(path=str(IMAGES / "hero.png"))
        browser.close()
    print("Saved", IMAGES / "hero.png")  # noqa: T201 (CLI tool output)


if __name__ == "__main__":
    main()
