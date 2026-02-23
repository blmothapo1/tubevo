"""
thumbnail.py — Generate a branded YouTube thumbnail image.

Creates a 1280×720 thumbnail with:
  • A dark gradient background
  • The video title in large bold white text
  • Channel branding ("TUBEVO") with accent colour
  • A subtle accent-coloured border strip

Usage:
    from thumbnail import generate_thumbnail

    path = generate_thumbnail(title="5 Frugal Habits That Build Wealth Fast")
    # → "output/thumbnail.jpg"
"""

from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("tubevo.thumbnail")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Dimensions (YouTube recommended) ────────────────────────────────
WIDTH = 1280
HEIGHT = 720

# ── Colours ──────────────────────────────────────────────────────────
BG_COLOR_TOP = (10, 10, 10)
BG_COLOR_BOTTOM = (25, 25, 35)
ACCENT_RGB = (0, 212, 170)       # #00D4AA
TEXT_COLOR = (255, 255, 255)
SUBTITLE_COLOR = (200, 200, 200)

# ── Fonts ────────────────────────────────────────────────────────────
# macOS system fonts — fallback to default if unavailable
_FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
_FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font, falling back to Pillow's default if the file is missing."""
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        logger.warning("Font not found: %s — using default", path)
        return ImageFont.load_default()


def _draw_gradient(draw: ImageDraw.ImageDraw) -> None:
    """Draw a vertical dark gradient background."""
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(BG_COLOR_TOP[0] + (BG_COLOR_BOTTOM[0] - BG_COLOR_TOP[0]) * ratio)
        g = int(BG_COLOR_TOP[1] + (BG_COLOR_BOTTOM[1] - BG_COLOR_TOP[1]) * ratio)
        b = int(BG_COLOR_TOP[2] + (BG_COLOR_BOTTOM[2] - BG_COLOR_TOP[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def generate_thumbnail(
    title: str,
    *,
    output_path: str | None = None,
) -> str:
    """Generate a branded thumbnail and return the file path.

    Parameters
    ----------
    title : str
        The video title to display on the thumbnail.
    output_path : str | None
        Where to save. Defaults to ``output/thumbnail.jpg``.
    """
    output_path = output_path or str(OUTPUT_DIR / "thumbnail.jpg")

    logger.info("Generating thumbnail for: %s", title)

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    # ── Background gradient ──────────────────────────────────────────
    _draw_gradient(draw)

    # ── Accent border strip (left edge) ──────────────────────────────
    draw.rectangle([(0, 0), (8, HEIGHT)], fill=ACCENT_RGB)

    # ── Accent horizontal line (centre) ──────────────────────────────
    line_y = HEIGHT // 2 - 30
    line_width = 300
    line_x = (WIDTH - line_width) // 2
    draw.rectangle([(line_x, line_y), (line_x + line_width, line_y + 4)], fill=ACCENT_RGB)

    # ── Channel branding (above the line) ────────────────────────────
    brand_font = _load_font(_FONT_BOLD, 30)
    brand_text = "TUBEVO"
    brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
    brand_w = brand_bbox[2] - brand_bbox[0]
    brand_x = (WIDTH - brand_w) // 2
    brand_y = line_y - 55
    draw.text((brand_x, brand_y), brand_text, fill=ACCENT_RGB, font=brand_font)

    # ── Title text (below the line) ──────────────────────────────────
    title_font = _load_font(_FONT_BOLD, 62)
    wrapped = textwrap.fill(title.upper(), width=22)
    lines = wrapped.split("\n")

    # Calculate total height of title block
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_heights.append(bbox[3] - bbox[1])

    line_spacing = 12
    total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    start_y = line_y + 30

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_w = bbox[2] - bbox[0]
        x = (WIDTH - line_w) // 2
        y = start_y + sum(line_heights[:i]) + line_spacing * i

        # Draw text shadow for depth
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=title_font)
        # Draw main text
        draw.text((x, y), line, fill=TEXT_COLOR, font=title_font)

    # ── Bottom accent strip ──────────────────────────────────────────
    draw.rectangle([(0, HEIGHT - 6), (WIDTH, HEIGHT)], fill=ACCENT_RGB)

    # ── Save ─────────────────────────────────────────────────────────
    img.save(output_path, "JPEG", quality=92)

    size_kb = os.path.getsize(output_path) / 1024
    logger.info("Thumbnail saved → %s  (%.0f KB)", output_path, size_kb)

    return output_path


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import config  # noqa: F401 — ensure logging is configured
    path = generate_thumbnail("Unlock Wealth: The Power of Compound Interest Revealed!")
    print(f"Done: {path}")
