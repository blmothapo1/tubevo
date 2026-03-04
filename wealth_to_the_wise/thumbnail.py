"""
thumbnail.py - Generate branded YouTube thumbnail variants.

Creates 1280x720 thumbnails with 3 distinct concept styles:
  1. Bold Curiosity   - high-contrast text, teal accent
  2. Contrarian Dramatic - dark split layout, red-orange accent
  3. Clean Authority   - minimal, professional, blue accent

Pure gradient backgrounds, Pillow only, zero external dependencies.

Usage:
    from thumbnail import generate_thumbnail, generate_thumbnail_variants

    path = generate_thumbnail(title="5 Frugal Habits That Build Wealth Fast")
    paths = generate_thumbnail_variants(title="...", output_dir="output")
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("tubevo.thumbnail")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

WIDTH = 1280
HEIGHT = 720

# ========================================================================
# CONCEPT COLOUR PALETTES
# ========================================================================

CONCEPTS = {
    "bold_curiosity": {
        "bg_top": (10, 10, 30),
        "bg_bottom": (15, 15, 50),
        "accent": (0, 212, 170),
        "text": (255, 255, 255),
        "badge_bg": (0, 212, 170),
        "badge_text": (10, 10, 30),
    },
    "contrarian_dramatic": {
        "bg_top": (20, 5, 5),
        "bg_bottom": (40, 10, 10),
        "accent": (255, 75, 43),
        "text": (255, 255, 255),
        "badge_bg": (255, 75, 43),
        "badge_text": (255, 255, 255),
    },
    "clean_authority": {
        "bg_top": (245, 245, 248),
        "bg_bottom": (225, 225, 232),
        "accent": (30, 64, 175),
        "text": (15, 15, 20),
        "badge_bg": (30, 64, 175),
        "badge_text": (255, 255, 255),
    },
}

# ========================================================================
# FONTS
# ========================================================================


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


def _load_font(path: str, size: int):
    """Load a font, falling back to Pillow default if file is missing."""
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        logger.warning("Font not found: %s - using default", path)
        return ImageFont.load_default()


# ========================================================================
# GRADIENT BACKGROUND
# ========================================================================


def _draw_gradient(draw, top: tuple, bottom: tuple) -> None:
    """Draw a vertical gradient background."""
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


# ========================================================================
# HOOK TEXT
# ========================================================================

_HOOK_BANKS = {
    "bold_curiosity": [
        "THIS CHANGES EVERYTHING",
        "YOU NEED TO SEE THIS",
        "NOBODY TALKS ABOUT THIS",
        "THE REAL SECRET",
        "GAME CHANGER",
        "DON'T MISS THIS",
        "FINALLY REVEALED",
        "HERE'S THE PROOF",
        "WATCH BEFORE IT'S LATE",
        "SHOCKING TRUTH",
    ],
    "contrarian_dramatic": [
        "STOP DOING THIS",
        "YOU'RE WRONG ABOUT THIS",
        "THE UGLY TRUTH",
        "THINK AGAIN",
        "WAKE UP",
        "IT'S A TRAP",
        "BIGGEST MISTAKE EVER",
        "THEY LIED TO YOU",
        "DEAD WRONG",
        "TOTAL SCAM",
    ],
    "clean_authority": [
        "THE REAL TRUTH",
        "YOU'RE MISSING THIS",
        "DATA DOESN'T LIE",
        "HERE'S THE PLAN",
        "PROVEN STRATEGY",
        "SMART MOVE",
        "THE BLUEPRINT",
        "DO THIS INSTEAD",
        "STEP BY STEP",
        "WORKS EVERY TIME",
    ],
}


def make_hook_text(title: str, concept: str) -> str:
    """Pick a short hook that does NOT repeat title words. Deterministic."""
    title_words = {w.lower().strip(".,!?\"'") for w in title.split()}
    seed = int(hashlib.sha256(f"{title}{concept}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    bank = list(_HOOK_BANKS.get(concept, _HOOK_BANKS["bold_curiosity"]))
    rng.shuffle(bank)

    for hook in bank:
        hook_words = {w.lower().strip(".,!?\"'") for w in hook.split()}
        if not hook_words & title_words:
            return hook
    return bank[0]


# ========================================================================
# CONCEPT GENERATORS
# ========================================================================


def _generate_bold_curiosity(title, draw, img):
    """Concept 1: Bold Curiosity - dramatic, high-contrast, teal accent."""
    c = CONCEPTS["bold_curiosity"]

    _draw_gradient(draw, c["bg_top"], c["bg_bottom"])

    # Left accent strip
    draw.rectangle([(0, 0), (8, HEIGHT)], fill=c["accent"])

    # Diagonal accent slash
    for i in range(6):
        draw.line(
            [(WIDTH - 200 + i, 0), (WIDTH + i, 200)], fill=c["accent"], width=1
        )

    # TUBEVO badge
    badge_font = _load_font(_FONT_BOLD, 24)
    badge_text = "TUBEVO"
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bb[2] - bb[0] + 24
    bh = bb[3] - bb[1] + 12
    draw.rounded_rectangle(
        [(30, 30), (30 + bw, 30 + bh)], radius=6, fill=c["badge_bg"]
    )
    draw.text((42, 34), badge_text, fill=c["badge_text"], font=badge_font)

    # Hook text (large)
    hook = make_hook_text(title, "bold_curiosity")
    hook_font = _load_font(_FONT_BOLD, 82)
    hook_lines = textwrap.fill(hook, width=14).split("\n")[:2]

    y = HEIGHT // 2 - len(hook_lines) * 52 - 30
    for line in hook_lines:
        draw.text((44, y + 4), line, fill=(0, 0, 0), font=hook_font)
        draw.text((40, y), line, fill=c["accent"], font=hook_font)
        y += 95

    # Title (secondary)
    title_font = _load_font(_FONT_BOLD, 42)
    lines = textwrap.fill(title.upper(), width=26).split("\n")[:3]
    y += 10
    for line in lines:
        draw.text((42, y + 2), line, fill=(0, 0, 0), font=title_font)
        draw.text((40, y), line, fill=c["text"], font=title_font)
        y += 52

    # Bottom accent bar
    draw.rectangle([(0, HEIGHT - 6), (WIDTH, HEIGHT)], fill=c["accent"])


def _generate_contrarian_dramatic(title, draw, img):
    """Concept 2: Contrarian Dramatic - dark split, red-orange accent."""
    c = CONCEPTS["contrarian_dramatic"]

    _draw_gradient(draw, c["bg_top"], c["bg_bottom"])

    # Split bar
    split_x = WIDTH // 3
    draw.rectangle([(split_x - 3, 0), (split_x + 3, HEIGHT)], fill=c["accent"])
    draw.polygon([(0, 0), (120, 0), (0, 120)], fill=(*c["accent"], 80))

    # Hook badge
    hook = make_hook_text(title, "contrarian_dramatic")
    badge_font = _load_font(_FONT_BOLD, 22)
    bb = draw.textbbox((0, 0), hook, font=badge_font)
    bw = bb[2] - bb[0] + 24
    bh = bb[3] - bb[1] + 14
    draw.rounded_rectangle(
        [(split_x + 40, 35), (split_x + 40 + bw, 35 + bh)],
        radius=4,
        fill=c["badge_bg"],
    )
    draw.text(
        (split_x + 52, 40), hook, fill=c["badge_text"], font=badge_font
    )

    # Title (right side)
    title_font = _load_font(_FONT_BOLD, 60)
    max_w = WIDTH - split_x - 80
    cpl = max(12, max_w // 36)
    lines = textwrap.fill(title.upper(), width=cpl).split("\n")[:5]
    y = HEIGHT // 2 - len(lines) * 38
    for line in lines:
        draw.text((split_x + 42, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((split_x + 40, y), line, fill=c["text"], font=title_font)
        y += 72

    # Bottom accents
    draw.rectangle([(0, HEIGHT - 8), (WIDTH, HEIGHT - 4)], fill=c["accent"])
    draw.rectangle([(0, HEIGHT - 2), (WIDTH, HEIGHT)], fill=c["accent"])
    brand_font = _load_font(_FONT_BOLD, 22)
    draw.text((20, HEIGHT - 40), "TUBEVO", fill=c["accent"], font=brand_font)


def _generate_clean_authority(title, draw, img):
    """Concept 3: Clean Authority - light background, minimal, professional."""
    c = CONCEPTS["clean_authority"]

    _draw_gradient(draw, c["bg_top"], c["bg_bottom"])

    # Top accent line
    draw.rectangle([(0, 0), (WIDTH, 5)], fill=c["accent"])

    # TUBEVO badge (top-right)
    badge_font = _load_font(_FONT_BOLD, 20)
    badge_text = "TUBEVO"
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bb[2] - bb[0] + 20
    bh = bb[3] - bb[1] + 10
    draw.rounded_rectangle(
        [(WIDTH - bw - 30, 25), (WIDTH - 30, 25 + bh)],
        radius=4,
        fill=c["badge_bg"],
    )
    draw.text(
        (WIDTH - bw - 20, 29), badge_text, fill=c["badge_text"], font=badge_font
    )

    # Hook text (centred)
    hook = make_hook_text(title, "clean_authority")
    hook_font = _load_font(_FONT_BOLD, 76)
    hbb = draw.textbbox((0, 0), hook, font=hook_font)
    hw = hbb[2] - hbb[0]
    hx = (WIDTH - hw) // 2
    hy = HEIGHT // 2 - 100
    draw.text((hx + 3, hy + 3), hook, fill=(0, 0, 0), font=hook_font)
    draw.text((hx, hy), hook, fill=c["accent"], font=hook_font)

    # Title (secondary, centred)
    title_font = _load_font(_FONT_BOLD, 40)
    lines = textwrap.fill(title.upper(), width=30).split("\n")[:3]
    line_heights = []
    for line in lines:
        bb2 = draw.textbbox((0, 0), line, font=title_font)
        line_heights.append(bb2[3] - bb2[1])

    y = hy + 110
    for i, line in enumerate(lines):
        bb2 = draw.textbbox((0, 0), line, font=title_font)
        lw = bb2[2] - bb2[0]
        x = (WIDTH - lw) // 2
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=title_font)
        draw.text((x, y), line, fill=c["text"], font=title_font)
        y += line_heights[i] + 12

    # Bottom accent
    draw.rectangle(
        [(WIDTH // 4, HEIGHT - 40), (3 * WIDTH // 4, HEIGHT - 36)],
        fill=c["accent"],
    )


# ========================================================================
# PUBLIC API
# ========================================================================

_CONCEPT_GENERATORS = {
    "bold_curiosity": _generate_bold_curiosity,
    "contrarian_dramatic": _generate_contrarian_dramatic,
    "clean_authority": _generate_clean_authority,
}


def generate_thumbnail(title, *, output_path=None, concept="bold_curiosity"):
    """Generate a branded thumbnail and return the file path."""
    output_path = output_path or str(OUTPUT_DIR / "thumbnail.jpg")
    logger.info("Generating thumbnail (concept=%s) for: %s", concept, title)

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    generator = _CONCEPT_GENERATORS.get(concept, _generate_bold_curiosity)
    generator(title, draw, img)

    img.save(output_path, "JPEG", quality=92)
    size_kb = os.path.getsize(output_path) / 1024
    logger.info(
        "Thumbnail saved -> %s  (%.0f KB, concept=%s)", output_path, size_kb, concept
    )
    return output_path


def generate_thumbnail_variants(title, *, output_dir=None):
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


# -- CLI test -------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    test_title = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Housing Market Crash Explained"
    )
    variants = generate_thumbnail_variants(test_title)
    for v in variants:
        print(f"  {v['concept']}: {v['path']}")
    print("Done!")
