"""Draw the desktop installers' artwork in Suzent's neo-brutalist style.

Writes into apps/desktop/installer/:
    dmg-background.png, dmg-background@2x.png   macOS disk image window
    installerSidebar.bmp, uninstallerSidebar.bmp  NSIS welcome/finish pages
    installerHeader.bmp                           NSIS inner pages

Usage: uv run --with pillow python scripts/generate_installer_art.py [--font FILE]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "apps" / "desktop" / "installer"
PAPER = (250, 250, 248)
INK = (0, 0, 0)
YELLOW = (255, 230, 102)
WHITE = (255, 255, 255)
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
    "C:/Windows/Fonts/ariblk.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
)


def font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    for candidate in ((path,) if path else ()) + FONT_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise SystemExit("No bold font found; pass --font")


def brutal_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    unit: int,
) -> None:
    """A filled box with a black outline and a hard drop shadow."""
    x0, y0, x1, y1 = box
    shadow = unit * 2
    draw.rectangle((x0 + shadow, y0 + shadow, x1 + shadow, y1 + shadow), fill=INK)
    draw.rectangle(box, fill=fill, outline=INK, width=unit)


def face(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """The Suzent mark: a black rounded square with two square eyes."""
    radius = size // 6
    draw.rounded_rectangle((x, y, x + size, y + size), radius=radius, fill=INK)
    eye = round(size * 5 / 24)
    top = y + round(size * 8 / 24)
    for left in (x + round(size * 5 / 24), x + round(size * 14 / 24)):
        draw.rounded_rectangle(
            (left, top, left + eye, top + eye), radius=max(1, eye // 3), fill=WHITE
        )


def dmg_background(scale: int, font_path: str | None) -> Image.Image:
    # electron-builder places the icons at these points (see electron-builder.yml).
    width, height = 540 * scale, 380 * scale
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    unit = 3 * scale
    draw.rectangle((0, 0, width - 1, height - 1), outline=INK, width=unit)
    face(draw, 28 * scale, 26 * scale, 30 * scale)
    draw.text(
        (70 * scale, 27 * scale), "SUZENT", font=font(font_path, 24 * scale), fill=INK
    )
    # A yellow arrow between the app (140, 200) and Applications (400, 200).
    y = 200 * scale
    arrow = [
        (222 * scale, y - 11 * scale),
        (292 * scale, y - 11 * scale),
        (292 * scale, y - 30 * scale),
        (330 * scale, y),
        (292 * scale, y + 30 * scale),
        (292 * scale, y + 11 * scale),
        (222 * scale, y + 11 * scale),
    ]
    offset = unit * 2
    draw.polygon([(px + offset, py + offset) for px, py in arrow], fill=INK)
    draw.polygon(arrow, fill=YELLOW, outline=INK, width=unit)
    caption = font(font_path, 15 * scale)
    text = "Drag Suzent into Applications"
    text_width = draw.textlength(text, font=caption)
    brutal_box(
        draw,
        (
            int((width - text_width) / 2 - 14 * scale),
            300 * scale,
            int((width + text_width) / 2 + 14 * scale),
            334 * scale,
        ),
        YELLOW,
        unit,
    )
    draw.text(((width - text_width) / 2, 308 * scale), text, font=caption, fill=INK)
    return image


def sidebar(font_path: str | None) -> Image.Image:
    width, height = 164, 314
    image = Image.new("RGB", (width, height), YELLOW)
    draw = ImageDraw.Draw(image)
    draw.rectangle((width - 4, 0, width, height), fill=INK)
    brutal_box(draw, (34, 56, 122, 144), WHITE, 3)
    face(draw, 44, 66, 68)
    title = font(font_path, 22)
    text_width = draw.textlength("SUZENT", font=title)
    draw.text(((width - 4 - text_width) / 2, 170), "SUZENT", font=title, fill=INK)
    small = font(font_path, 10)
    for index, line in enumerate(("Your sovereign", "personal agent")):
        line_width = draw.textlength(line, font=small)
        draw.text(
            ((width - 4 - line_width) / 2, 204 + index * 14), line, font=small, fill=INK
        )
    for index in range(6):
        x = 16 + index * 22
        draw.rectangle(
            (x, 280, x + 12, 292),
            fill=INK if index % 2 == 0 else WHITE,
            outline=INK,
            width=2,
        )
    return image


def header(font_path: str | None) -> Image.Image:
    width, height = 150, 57
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    brutal_box(draw, (92, 9, 132, 45), YELLOW, 2)
    face(draw, 98, 13, 28)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--font", help="bold font file to draw text with")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    dmg_background(1, args.font).save(OUT / "dmg-background.png")
    dmg_background(2, args.font).save(OUT / "dmg-background@2x.png")
    art = sidebar(args.font)
    art.save(OUT / "installerSidebar.bmp")
    art.save(OUT / "uninstallerSidebar.bmp")
    header(args.font).save(OUT / "installerHeader.bmp")
    print(f"Wrote installer artwork to {OUT}")


if __name__ == "__main__":
    main()
