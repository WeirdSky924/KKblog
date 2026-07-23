#!/usr/bin/env python3
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps" / "media" / "static" / "media" / "brand"


def default_cover() -> Image.Image:
    image = Image.new("RGB", (1600, 900), "#f2f1ed")
    draw = ImageDraw.Draw(image)

    for x in range(80, 1600, 160):
        draw.line((x, 0, x, 900), fill="#d4d2cd", width=2)
    for y in range(90, 900, 90):
        draw.line((0, y, 1600, y), fill="#d4d2cd", width=2)

    draw.rectangle((0, 0, 78, 900), fill="#7e2637")
    draw.rectangle((80, 90, 560, 630), fill="#f4d9c8")
    draw.rectangle((560, 90, 1040, 450), fill="#ffffff")
    draw.rectangle((1040, 450, 1520, 810), fill="#365f52")
    draw.rectangle((560, 630, 1040, 810), fill="#202124")

    # A geometric K carries the site mark without relying on a font file.
    draw.rectangle((230, 215, 300, 520), fill="#7e2637")
    draw.polygon(
        ((300, 365), (440, 215), (525, 215), (372, 380), (530, 520), (435, 520)),
        fill="#7e2637",
    )
    draw.line((1120, 700, 1435, 530), fill="#f2f1ed", width=24)
    draw.line((1120, 750, 1435, 580), fill="#f2f1ed", width=24)

    for offset in range(5):
        y = 140 + offset * 52
        draw.rectangle((650, y, 930 - offset * 34, y + 12), fill="#202124")
    for offset in range(4):
        x = 1100 + offset * 86
        draw.ellipse((x, 180, x + 36, 216), fill="#7e2637")
    return image


def unavailable_bookmark() -> Image.Image:
    image = Image.new("RGB", (800, 450), "#e7e8e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 800, 28), fill="#202124")
    draw.rectangle((48, 74, 752, 376), outline="#8c9093", width=3)
    draw.rectangle((112, 126, 350, 324), fill="#d2d5d5")
    draw.line((112, 126, 350, 324), fill="#7e2637", width=16)
    draw.line((112, 324, 350, 126), fill="#7e2637", width=16)

    lengths = (286, 248, 300, 176)
    for index, length in enumerate(lengths):
        y = 140 + index * 48
        draw.rectangle((414, y, 414 + length, y + 12), fill="#666b6e")
    draw.rectangle((414, 332, 572, 348), fill="#7e2637")

    # The interrupted rule is unique to the unavailable state.
    draw.line((48, 408, 330, 408), fill="#8c9093", width=3)
    draw.line((470, 408, 752, 408), fill="#8c9093", width=3)
    draw.rectangle((382, 395, 418, 421), fill="#202124")
    return image


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    default_cover().save(OUTPUT / "default-cover.png", format="PNG", optimize=True)
    unavailable_bookmark().save(
        OUTPUT / "unavailable-bookmark.png", format="PNG", optimize=True
    )


if __name__ == "__main__":
    main()
