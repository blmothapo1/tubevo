"""
thumbnail.py - Generate branded YouTube thumbnail variants.

Creates 1280x720 thumbnails with up to 4 distinct concept styles:
  1. Bold Curiosity        - high-contrast text, teal accent
  2. Contrarian Dramatic   - dark split layout, red-orange accent
  3. Clean Authority       - minimal, professional, blue accent
  4. AI Cinematic          - DALL·E 3 generated background + text overlay

Styles 1-3 use pure gradient backgrounds (Pillow only).
Style 4 requires an OpenAI API key and generates a unique background per topic.
Falls back to gradient styles if the API call fails.

Usage:
    from thumbnail import generate_thumbnail, generate_thumbnail_variants

    path = generate_thumbnail(title="5 Frugal Habits That Build Wealth Fast")
    paths = generate_thumbnail_variants(title="...", output_dir="output")
    paths = generate_thumbnail_variants(title="...", openai_api_key="sk-...")  # includes AI variant
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import random
import textwrap
from pathlib import Path

import requests
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
# AI BACKGROUND GENERATION (DALL·E 3)
# ========================================================================

# Niche-specific prompt modifiers for better backgrounds
_NICHE_PROMPTS = {
    "finance": "gold coins, stock charts, luxury lifestyle, wealth symbols",
    "real_estate": "modern architecture, luxury homes, city skylines",
    "tech": "futuristic technology, circuit boards, holographic displays",
    "crypto": "digital currency, blockchain, neon data streams",
    "business": "corporate office, handshake, success, skyscrapers",
    "health": "wellness, vitality, healthy lifestyle, nature",
    "general": "dramatic cinematic scene, motivational, powerful imagery",
}


def _build_dalle_prompt(title: str, niche: str | None = None) -> str:
    """Build a DALL·E 3 prompt for a thumbnail background.

    The prompt is designed to produce a dramatic, cinematic background
    WITHOUT any text — our code overlays the text separately.
    """
    niche_hint = _NICHE_PROMPTS.get((niche or "general").lower(), _NICHE_PROMPTS["general"])

    return (
        f"A dramatic, cinematic YouTube thumbnail background image for a video titled "
        f'"{title}". '
        f"Visual elements: {niche_hint}. "
        f"Style: dark moody atmosphere, dramatic lighting with volumetric rays, "
        f"rich color grading, shallow depth of field, ultra-high quality. "
        f"The image should be a BACKGROUND ONLY — absolutely NO text, NO letters, "
        f"NO words, NO numbers, NO watermarks, NO logos anywhere in the image. "
        f"No human faces. Cinematic 16:9 aspect ratio."
    )


def generate_ai_background(
    title: str,
    *,
    openai_api_key: str,
    niche: str | None = None,
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> Image.Image | None:
    """Generate a thumbnail background image via DALL·E 3.

    Returns a PIL Image sized to (WIDTH, HEIGHT), or None on failure.
    Falls back gracefully — never raises.
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=openai_api_key)

        prompt = _build_dalle_prompt(title, niche)
        logger.info("Generating AI thumbnail background via DALL·E 3…")

        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",  # closest to 16:9 that DALL·E 3 supports
            quality="standard",
            n=1,
        )

        if not response.data:
            logger.warning("DALL·E 3 returned empty data")
            return None

        image_url = response.data[0].url
        if not image_url:
            logger.warning("DALL·E 3 returned no image URL")
            return None

        # Download the image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()

        img = Image.open(io.BytesIO(img_response.content)).convert("RGB")

        # Resize/crop to exact thumbnail dimensions
        img = img.resize(size, Image.Resampling.LANCZOS)

        logger.info("AI background generated successfully (%dx%d)", size[0], size[1])
        return img

    except Exception as e:
        logger.warning("AI background generation failed (non-fatal): %s", e)
        return None


def _generate_ai_cinematic(title, draw, img, *, ai_bg: Image.Image | None = None):
    """Concept 4: AI Cinematic - DALL·E 3 background + bold text overlay.

    If ai_bg is None (API failed), falls back to a dark cinematic gradient.
    """
    if ai_bg:
        # Paste the AI background
        img.paste(ai_bg)
        # Re-acquire draw context since we replaced the image data
        draw = ImageDraw.Draw(img)

        # Darken the bottom third for text readability
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for y in range(HEIGHT // 3, HEIGHT):
            alpha = int(180 * ((y - HEIGHT // 3) / (HEIGHT * 2 / 3)))
            overlay_draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))
        draw = ImageDraw.Draw(img)

        # Subtle top vignette too
        for y in range(0, HEIGHT // 5):
            alpha = int(120 * (1 - y / (HEIGHT // 5)))
            draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0))
    else:
        # Fallback: dark cinematic gradient
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            r = int(8 + 12 * ratio)
            g = int(5 + 8 * ratio)
            b = int(20 + 30 * ratio)
            draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    # Accent: subtle warm glow line at top
    draw.rectangle([(0, 0), (WIDTH, 3)], fill=(255, 165, 50))

    # TUBEVO badge (top-left, glass-morphism style)
    badge_font = _load_font(_FONT_BOLD, 22)
    badge_text = "TUBEVO"
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bb[2] - bb[0] + 24
    bh = bb[3] - bb[1] + 14
    draw.rounded_rectangle(
        [(28, 22), (28 + bw, 22 + bh)],
        radius=6,
        fill=(0, 0, 0, 160) if ai_bg else (20, 15, 40),
    )
    draw.text((40, 26), badge_text, fill=(255, 200, 60), font=badge_font)

    # Hook text — large, dramatic
    hook = make_hook_text(title, "bold_curiosity")  # reuse bold bank
    hook_font = _load_font(_FONT_BOLD, 78)
    hook_lines = textwrap.fill(hook, width=16).split("\n")[:2]

    y = HEIGHT // 2 - len(hook_lines) * 50 - 10
    for line in hook_lines:
        # Shadow
        draw.text((44, y + 4), line, fill=(0, 0, 0), font=hook_font)
        draw.text((42, y + 2), line, fill=(0, 0, 0), font=hook_font)
        # Main text — warm accent
        draw.text((40, y), line, fill=(255, 200, 60), font=hook_font)
        y += 90

    # Title (white, below hook)
    title_font = _load_font(_FONT_BOLD, 44)
    lines = textwrap.fill(title.upper(), width=24).split("\n")[:3]
    y += 15
    for line in lines:
        # Heavy shadow for readability on any background
        draw.text((44, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((42, y + 1), line, fill=(0, 0, 0), font=title_font)
        draw.text((40, y), line, fill=(255, 255, 255), font=title_font)
        y += 54

    # Bottom accent bar
    draw.rectangle([(0, HEIGHT - 5), (WIDTH, HEIGHT)], fill=(255, 165, 50))


# ========================================================================
# PUBLIC API
# ========================================================================

_CONCEPT_GENERATORS = {
    "bold_curiosity": _generate_bold_curiosity,
    "contrarian_dramatic": _generate_contrarian_dramatic,
    "clean_authority": _generate_clean_authority,
    "ai_cinematic": _generate_ai_cinematic,
}


def generate_thumbnail(title, *, output_path=None, concept="bold_curiosity", openai_api_key=None, niche=None):
    """Generate a branded thumbnail and return the file path.

    For the ``ai_cinematic`` concept, pass ``openai_api_key`` to enable
    DALL·E 3 background generation. Without it, a dark gradient fallback
    is used.
    """
    output_path = output_path or str(OUTPUT_DIR / "thumbnail.jpg")
    logger.info("Generating thumbnail (concept=%s) for: %s", concept, title)

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    generator = _CONCEPT_GENERATORS.get(concept, _generate_bold_curiosity)

    if concept == "ai_cinematic":
        # Generate AI background if we have a key
        ai_bg = None
        if openai_api_key:
            ai_bg = generate_ai_background(title, openai_api_key=openai_api_key, niche=niche)
        generator(title, draw, img, ai_bg=ai_bg)
    else:
        generator(title, draw, img)

    img.save(output_path, "JPEG", quality=92)
    size_kb = os.path.getsize(output_path) / 1024
    logger.info(
        "Thumbnail saved -> %s  (%.0f KB, concept=%s)", output_path, size_kb, concept
    )
    return output_path


def generate_thumbnail_variants(title, *, output_dir=None, openai_api_key=None, niche=None):
    """Generate thumbnail concept variants.

    Without ``openai_api_key``: generates 3 template variants.
    With ``openai_api_key``: generates 4 variants (3 template + 1 AI).

    Returns a list of dicts: [{"concept": str, "path": str}, ...]
    """
    output_dir = output_dir or str(OUTPUT_DIR)
    results = []

    # Always generate the 3 template-based variants
    for concept_name in ("bold_curiosity", "contrarian_dramatic", "clean_authority"):
        filename = f"thumbnail_{concept_name}.jpg"
        path = str(Path(output_dir) / filename)
        generate_thumbnail(title, output_path=path, concept=concept_name)
        results.append({"concept": concept_name, "path": path})

    # Generate AI variant if we have an OpenAI key
    if openai_api_key:
        try:
            ai_path = str(Path(output_dir) / "thumbnail_ai_cinematic.jpg")
            generate_thumbnail(
                title,
                output_path=ai_path,
                concept="ai_cinematic",
                openai_api_key=openai_api_key,
                niche=niche,
            )
            results.append({"concept": "ai_cinematic", "path": ai_path})
            logger.info("AI cinematic thumbnail generated successfully")
        except Exception as e:
            logger.warning("AI thumbnail generation failed (non-fatal): %s", e)

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
    # Pass OPENAI_API_KEY env var to test AI variant
    api_key = os.getenv("OPENAI_API_KEY", "")
    variants = generate_thumbnail_variants(test_title, openai_api_key=api_key or None)
    for v in variants:
        print(f"  {v['concept']}: {v['path']}")
    print("Done!")
