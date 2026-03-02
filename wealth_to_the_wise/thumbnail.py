"""
thumbnail.py — Generate branded YouTube thumbnail variants.

Creates 1280×720 thumbnails with 3 distinct concept styles:
  1. Bold Curiosity — high-contrast text, dramatic lighting, question/bold claim
  2. Contrarian Dramatic — dark split layout, red/orange accent, "myth bust" feel
  3. Clean Authority — minimal, professional, data-driven aesthetic

Usage:
    from thumbnail import generate_thumbnail, generate_thumbnail_variants

    path = generate_thumbnail(title="5 Frugal Habits That Build Wealth Fast")
    paths = generate_thumbnail_variants(title="...", output_dir="output")
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

# ── Concept colour palettes ─────────────────────────────────────────
CONCEPTS = {
    "bold_curiosity": {
        "bg_top": (10, 10, 30),
        "bg_bottom": (15, 15, 50),
        "accent": (0, 212, 170),        # #00D4AA — teal
        "text": (255, 255, 255),
        "subtitle": (200, 200, 200),
        "badge_bg": (0, 212, 170),
        "badge_text": (10, 10, 30),
    },
    "contrarian_dramatic": {
        "bg_top": (20, 5, 5),
        "bg_bottom": (40, 10, 10),
        "accent": (255, 75, 43),         # #FF4B2B — hot red-orange
        "text": (255, 255, 255),
        "subtitle": (200, 180, 180),
        "badge_bg": (255, 75, 43),
        "badge_text": (255, 255, 255),
    },
    "clean_authority": {
        "bg_top": (245, 245, 248),
        "bg_bottom": (225, 225, 232),
        "accent": (30, 64, 175),         # #1E40AF — deep blue
        "text": (15, 15, 20),
        "subtitle": (80, 80, 100),
        "badge_bg": (30, 64, 175),
        "badge_text": (255, 255, 255),
    },
}

# ── Fonts ────────────────────────────────────────────────────────────
def _find_system_font(bold: bool = True) -> str:
    if bold:
        for p in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if os.path.isfile(p):
                return p
    else:
        for p in [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]:
            if os.path.isfile(p):
                return p
    return ""

_FONT_BOLD = _find_system_font(bold=True)
_FONT_REGULAR = _find_system_font(bold=False)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font, falling back to Pillow's default if the file is missing."""
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        logger.warning("Font not found: %s — using default", path)
        return ImageFont.load_default()


def _draw_gradient(draw: ImageDraw.ImageDraw, top: tuple, bottom: tuple) -> None:
    """Draw a vertical gradient background."""
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def _generate_bold_curiosity(title: str, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
    """Concept 1: Bold Curiosity — dramatic, high-contrast, teal accent."""
    c = CONCEPTS["bold_curiosity"]
    _draw_gradient(draw, c["bg_top"], c["bg_bottom"])

    # Left accent strip
    draw.rectangle([(0, 0), (8, HEIGHT)], fill=c["accent"])

    # Diagonal accent slash (top-right)
    for i in range(6):
        draw.line([(WIDTH - 200 + i, 0), (WIDTH + i, 200)], fill=c["accent"], width=1)

    # Channel badge
    badge_font = _load_font(_FONT_BOLD, 24)
    badge_text = "TUBEVO"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 24
    badge_h = badge_bbox[3] - badge_bbox[1] + 12
    badge_x, badge_y = 30, 30
    draw.rounded_rectangle(
        [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
        radius=6, fill=c["badge_bg"],
    )
    draw.text((badge_x + 12, badge_y + 4), badge_text, fill=c["badge_text"], font=badge_font)

    # Title — large, left-aligned, wrapped
    title_font = _load_font(_FONT_BOLD, 68)
    wrapped = textwrap.fill(title.upper(), width=18)
    lines = wrapped.split("\n")[:4]

    y_cursor = HEIGHT // 2 - len(lines) * 42
    for line in lines:
        # Shadow
        draw.text((42, y_cursor + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((40, y_cursor), line, fill=c["text"], font=title_font)
        y_cursor += 80

    # Bottom accent bar
    draw.rectangle([(0, HEIGHT - 6), (WIDTH, HEIGHT)], fill=c["accent"])


def _generate_contrarian_dramatic(title: str, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
    """Concept 2: Contrarian Dramatic — dark split, red-orange accent, "myth bust" feel."""
    c = CONCEPTS["contrarian_dramatic"]
    _draw_gradient(draw, c["bg_top"], c["bg_bottom"])

    # Vertical split bar (off-centre)
    split_x = WIDTH // 3
    draw.rectangle([(split_x - 3, 0), (split_x + 3, HEIGHT)], fill=c["accent"])

    # Top-left accent triangle
    draw.polygon([(0, 0), (120, 0), (0, 120)], fill=(*c["accent"], 80))

    # "MYTH BUSTED" or "THINK AGAIN" badge
    badge_font = _load_font(_FONT_BOLD, 20)
    badge_text = "THINK AGAIN"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 20
    badge_h = badge_bbox[3] - badge_bbox[1] + 10
    draw.rounded_rectangle(
        [(split_x + 40, 35), (split_x + 40 + badge_w, 35 + badge_h)],
        radius=4, fill=c["badge_bg"],
    )
    draw.text((split_x + 50, 39), badge_text, fill=c["badge_text"], font=badge_font)

    # Title — right side of split
    title_font = _load_font(_FONT_BOLD, 60)
    max_width = WIDTH - split_x - 80
    # Estimate chars per line based on available width
    chars_per_line = max(12, max_width // 36)
    wrapped = textwrap.fill(title.upper(), width=chars_per_line)
    lines = wrapped.split("\n")[:5]

    y_cursor = HEIGHT // 2 - len(lines) * 38
    for line in lines:
        draw.text((split_x + 42, y_cursor + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((split_x + 40, y_cursor), line, fill=c["text"], font=title_font)
        y_cursor += 72

    # Bottom double-line accent
    draw.rectangle([(0, HEIGHT - 8), (WIDTH, HEIGHT - 4)], fill=c["accent"])
    draw.rectangle([(0, HEIGHT - 2), (WIDTH, HEIGHT)], fill=c["accent"])

    # Branding bottom-left
    brand_font = _load_font(_FONT_BOLD, 22)
    draw.text((20, HEIGHT - 40), "TUBEVO", fill=c["accent"], font=brand_font)


def _generate_clean_authority(title: str, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
    """Concept 3: Clean Authority — light background, minimal, professional."""
    c = CONCEPTS["clean_authority"]
    _draw_gradient(draw, c["bg_top"], c["bg_bottom"])

    # Thin top accent line
    draw.rectangle([(0, 0), (WIDTH, 5)], fill=c["accent"])

    # Brand badge — top-right
    badge_font = _load_font(_FONT_BOLD, 20)
    badge_text = "TUBEVO"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 20
    badge_h = badge_bbox[3] - badge_bbox[1] + 10
    draw.rounded_rectangle(
        [(WIDTH - badge_w - 30, 25), (WIDTH - 30, 25 + badge_h)],
        radius=4, fill=c["badge_bg"],
    )
    draw.text((WIDTH - badge_w - 20, 29), badge_text, fill=c["badge_text"], font=badge_font)

    # Centre-aligned title
    title_font = _load_font(_FONT_BOLD, 62)
    wrapped = textwrap.fill(title.upper(), width=22)
    lines = wrapped.split("\n")[:4]

    # Calculate total height
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_heights.append(bbox[3] - bbox[1])

    spacing = 14
    total_h = sum(line_heights) + spacing * (len(lines) - 1)
    y_cursor = (HEIGHT - total_h) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_w = bbox[2] - bbox[0]
        x = (WIDTH - line_w) // 2
        draw.text((x, y_cursor), line, fill=c["text"], font=title_font)
        y_cursor += line_heights[i] + spacing

    # Subtle bottom accent line
    draw.rectangle([(WIDTH // 4, HEIGHT - 40), (3 * WIDTH // 4, HEIGHT - 36)], fill=c["accent"])


# Mapping of concept name → generator function
_CONCEPT_GENERATORS = {
    "bold_curiosity": _generate_bold_curiosity,
    "contrarian_dramatic": _generate_contrarian_dramatic,
    "clean_authority": _generate_clean_authority,
}


def generate_thumbnail(
    title: str,
    *,
    output_path: str | None = None,
    concept: str = "bold_curiosity",
) -> str:
    """Generate a branded thumbnail and return the file path.

    Parameters
    ----------
    title : str
        The video title to display on the thumbnail.
    output_path : str | None
        Where to save. Defaults to ``output/thumbnail.jpg``.
    concept : str
        Which visual concept to use. One of: bold_curiosity, contrarian_dramatic, clean_authority.
    """
    output_path = output_path or str(OUTPUT_DIR / "thumbnail.jpg")

    logger.info("Generating thumbnail (concept=%s) for: %s", concept, title)

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    generator = _CONCEPT_GENERATORS.get(concept, _generate_bold_curiosity)
    generator(title, draw, img)

    img.save(output_path, "JPEG", quality=92)

    size_kb = os.path.getsize(output_path) / 1024
    logger.info("Thumbnail saved → %s  (%.0f KB, concept=%s)", output_path, size_kb, concept)

    return output_path


def generate_thumbnail_variants(
    title: str,
    *,
    output_dir: str | None = None,
) -> list[dict]:
    """Generate all 3 thumbnail concept variants.

    Returns a list of dicts: [{"concept": str, "path": str}, ...]
    """
    output_dir = output_dir or str(OUTPUT_DIR)
    results = []

    for concept_name in _CONCEPT_GENERATORS:
        filename = f"thumbnail_{concept_name}.jpg"
        path = str(Path(output_dir) / filename)
        generate_thumbnail(title, output_path=path, concept=concept_name)
        results.append({"concept": concept_name, "path": path})

    logger.info("Generated %d thumbnail variants", len(results))
    return results


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import config  # noqa: F401 — ensure logging is configured
    variants = generate_thumbnail_variants("Unlock Wealth: The Power of Compound Interest Revealed!")
    for v in variants:
        print(f"  {v['concept']}: {v['path']}")
    print("Done!")
