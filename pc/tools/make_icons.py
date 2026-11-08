"""
make_icons.py — Draws the app icon in code and saves every size we need.

Run from the `pc` folder:   python tools/make_icons.py

Outputs:
    remote_mouse/web/icons/icon-192.png, icon-512.png   phone home-screen icon
    remote_mouse/web/icons/icon-maskable-512.png        Android adaptive icon
                                                        (extra padding)
    assets/remote_mouse.ico                             Windows .exe + tray icon

Drawing the icon in code (instead of shipping an image from somewhere) means
there are no licensing questions and anyone can tweak the colours below.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
WEB_ICONS = ROOT / "remote_mouse" / "web" / "icons"
ASSETS = ROOT / "assets"

BACKGROUND_TOP = (91, 140, 255)
BACKGROUND_BOTTOM = (60, 92, 214)
MOUSE_BODY = (255, 255, 255)
MOUSE_DETAIL = (60, 92, 214)
SUPERSAMPLE = 4  # draw big, then shrink, for smooth edges


def _gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(
            round(a + (b - a) * t) for a, b in zip(BACKGROUND_TOP, BACKGROUND_BOTTOM, strict=True)
        )
        draw.line([(0, y), (size, y)], fill=color)
    return image


def draw_icon(size: int, padding: float = 0.0, rounded: bool = True) -> Image.Image:
    """Return an RGBA icon of `size` px. `padding` (0-0.5) shrinks the artwork."""
    big = size * SUPERSAMPLE
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    mask = Image.new("L", (big, big), 0)
    radius = int(big * 0.22) if rounded else 0
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=radius, fill=255)
    canvas.paste(_gradient(big), (0, 0), mask)

    draw = ImageDraw.Draw(canvas)
    scale = 1.0 - 2 * padding
    width, height = big * 0.38 * scale, big * 0.56 * scale
    left, top = (big - width) / 2, (big - height) / 2
    body = [left, top, left + width, top + height]
    draw.rounded_rectangle(body, radius=int(width / 2), fill=MOUSE_BODY)

    # Split line between the two buttons + the scroll wheel.
    center_x = big / 2
    line_w = max(2, int(big * 0.012))
    draw.line([(center_x, top), (center_x, top + height * 0.38)], fill=MOUSE_DETAIL, width=line_w)
    draw.line(
        [(left, top + height * 0.38), (left + width, top + height * 0.38)],
        fill=MOUSE_DETAIL,
        width=line_w,
    )
    wheel_w, wheel_h = width * 0.12, height * 0.14
    draw.rounded_rectangle(
        [
            center_x - wheel_w / 2,
            top + height * 0.12,
            center_x + wheel_w / 2,
            top + height * 0.12 + wheel_h,
        ],
        radius=int(wheel_w / 2),
        fill=MOUSE_DETAIL,
    )
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    WEB_ICONS.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(WEB_ICONS / "icon-192.png")
    draw_icon(512).save(WEB_ICONS / "icon-512.png")
    # Maskable: Android crops to a circle/squircle, so keep art in the safe zone.
    draw_icon(512, padding=0.12, rounded=False).save(WEB_ICONS / "icon-maskable-512.png")
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)]
    draw_icon(256).save(ASSETS / "remote_mouse.ico", sizes=ico_sizes)


if __name__ == "__main__":
    main()
