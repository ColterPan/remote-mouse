"""
render_icons.py — Renders EVERY app icon from the one master logo.

    branding/logo.svg  ──►  PC:      pc/assets/remote_mouse.ico (exe + installer)
                            phone:   pc/remote_mouse/web/icons/*.png (web app + tray)
                            Android: android/app/src/main/res/mipmap-*/…

Run from the `pc` folder (needs the dev requirements + `playwright install chromium`):
    python tools/render_icons.py

Why a browser? SVG is the best format for a crisp logo at any size, and
Chromium renders SVG perfectly. Playwright drives a headless Chromium to
"screenshot" the SVG at each size we need. Pillow then packs the Windows .ico.

Android "adaptive icons" are two layers (background + foreground) that the
launcher may crop into a circle, squircle, etc. Only the centre ~61% is
guaranteed visible, so the foreground artwork is scaled down to fit that
"safe zone".
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

PC_DIR = Path(__file__).resolve().parent.parent
ROOT = PC_DIR.parent
LOGO = ROOT / "branding" / "logo.svg"
WEB_ICONS = PC_DIR / "remote_mouse" / "web" / "icons"
ASSETS = PC_DIR / "assets"
ANDROID_RES = ROOT / "android" / "app" / "src" / "main" / "res"

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
# Android density buckets: launcher icon is 48dp, adaptive layers are 108dp.
DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
ADAPTIVE_ART_SCALE = 0.84  # keeps the artwork inside the adaptive-icon safe zone
MASKABLE_ART_SCALE = 0.86  # web "maskable" icons have a similar safe zone


def load_logo() -> str:
    return LOGO.read_text(encoding="utf-8")


def _strip_comments(svg: str) -> str:
    return re.sub(r"<!--.*?-->", "", svg, flags=re.S)


def variant(
    svg: str, *, background: str = "rounded", art_scale: float = 1.0, art: bool = True
) -> str:
    """
    Make a variant of the master SVG.

    background: "rounded" (as designed), "square" (full-bleed, no corners),
                or "none" (transparent).
    art_scale:  shrink the artwork around the centre (for safe zones).
    art:        False renders the background alone.
    """
    svg = _strip_comments(svg)
    if background == "none":
        svg = re.sub(r'<g id="bg">.*?</g>', "", svg, count=1, flags=re.S)
    elif background == "square":
        svg = svg.replace('rx="232"', 'rx="0"')
    if not art:
        svg = re.sub(r'<g id="art">.*</g>\s*</svg>', "</svg>", svg, count=1, flags=re.S)
    elif art_scale != 1.0:
        offset = 512 * (1 - art_scale)
        svg = svg.replace(
            '<g id="art">',
            f'<g id="art" transform="translate({offset:.2f} {offset:.2f}) scale({art_scale})">',
            1,
        )
    return svg


def render(page: Page, svg: str, size: int) -> Image.Image:
    """Rasterise `svg` to a size×size RGBA image using Chromium."""
    sized = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f"<html><body style='margin:0;background:transparent'>{sized}</body></html>")
    png = page.locator("svg").screenshot(omit_background=True)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def circle_crop(image: Image.Image) -> Image.Image:
    """Round launcher icon for old Android launchers."""
    mask = Image.new("L", image.size, 0)
    from PIL import ImageDraw

    ImageDraw.Draw(mask).ellipse([0, 0, image.width - 1, image.height - 1], fill=255)
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    out.paste(image, (0, 0), mask)
    return out


def write_web_and_pc(page: Page, svg: str) -> None:
    WEB_ICONS.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    render(page, svg, 192).save(WEB_ICONS / "icon-192.png")
    render(page, svg, 512).save(WEB_ICONS / "icon-512.png")
    maskable = variant(svg, background="square", art_scale=MASKABLE_ART_SCALE)
    render(page, maskable, 512).save(WEB_ICONS / "icon-maskable-512.png")

    # Windows .ico: render the biggest size, let Pillow build every size in it.
    big = render(page, svg, 256)
    big.save(ASSETS / "remote_mouse.ico", sizes=[(s, s) for s in ICO_SIZES])
    big.save(ASSETS / "logo-256.png")


def write_android(page: Page, svg: str) -> None:
    foreground = variant(svg, background="none", art_scale=ADAPTIVE_ART_SCALE)
    background = variant(svg, background="square", art=False)
    for bucket, factor in DENSITIES.items():
        folder = ANDROID_RES / f"mipmap-{bucket}"
        folder.mkdir(parents=True, exist_ok=True)
        legacy = round(48 * factor)
        layer = round(108 * factor)
        icon = render(page, svg, legacy)
        icon.save(folder / "ic_launcher.png")
        circle_crop(render(page, variant(svg, background="square"), legacy)).save(
            folder / "ic_launcher_round.png"
        )
        render(page, foreground, layer).save(folder / "ic_launcher_foreground.png")
        render(page, background, layer).save(folder / "ic_launcher_background.png")


def main() -> None:
    svg = load_logo()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        write_web_and_pc(page, svg)
        if ANDROID_RES.parent.exists():
            write_android(page, svg)
        browser.close()
    print("Icons rendered from", LOGO)  # noqa: T201 (CLI tool output)


if __name__ == "__main__":
    main()
