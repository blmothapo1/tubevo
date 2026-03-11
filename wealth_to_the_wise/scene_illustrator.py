"""
scene_illustrator.py — AI-Generated Scene Illustrations (DALL-E 3)

Generates custom illustrations for each scene in a video using OpenAI's
DALL-E 3 image generation API.  Each scene's narration text is transformed
into a cinematic image prompt, generating visuals that *depict exactly
what's being spoken about* rather than generic stock footage.

This is the core differentiator between free-tier (stock footage) and
premium-tier (custom AI art) videos.

Pipeline integration:
  • Scene planner produces ScenePlan objects with .text and .label
  • This module takes those plans → generates DALL-E 3 prompts → downloads
    the resulting images → converts each image to an animated video clip
    (Ken Burns pan/zoom) using FFmpeg
  • Returns data in the same format as stock_footage.download_clips_for_scenes()
    so video_builder needs zero changes to its interface

Cost: ~$0.04 per image (1024×1024 standard) × 6–18 scenes = $0.24–$0.72/video.
Acceptable for Pro ($79/mo) and Agency ($199/mo) plans.

Memory: Static PNG/JPG → zoompan is lighter than video decoding.
Safe for Railway 512 MB containers.

Usage:
    from scene_illustrator import generate_illustrations_for_scenes

    scene_clip_data = generate_illustrations_for_scenes(
        scene_plans,
        openai_api_key="sk-...",
        clips_dir=Path("output/clips"),
    )
    # → [{"label": "intro", "clips": ["clip_0.mp4"], "duration": 12.5}, ...]
"""

from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from pipeline_errors import ExternalServiceError

logger = logging.getLogger("tubevo.scene_illustrator")

# ── Defaults ─────────────────────────────────────────────────────────
CLIPS_DIR = Path("output/clips")
IMAGE_SIZE = "1024x1024"           # DALL-E 3 standard quality
IMAGE_QUALITY = "standard"          # "standard" ($0.04) or "hd" ($0.08)
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
FPS = 24

# Max concurrent image generations (DALL-E 3 rate limit: 7 images/min)
MAX_PARALLEL_IMAGES = 2
# Retry config
MAX_RETRIES = 2
RETRY_DELAY = 3.0

# ── Visual style presets for prompts ────────────────────────────────
# These are appended to every DALL-E prompt to ensure consistent,
# premium aesthetic across all scenes.
ILLUSTRATION_STYLES = {
    "cinematic": (
        "Digital illustration, cinematic lighting, rich color palette, "
        "professional quality, 4K detail, dramatic composition, "
        "subtle depth of field, modern and sleek aesthetic"
    ),
    "finance": (
        "Professional financial illustration, clean modern design, "
        "deep blues and golds, corporate elegance, sharp lines, "
        "premium infographic style, authoritative and trustworthy"
    ),
    "documentary": (
        "Photorealistic digital art, natural lighting, documentary style, "
        "real-world setting, high detail, warm tones, editorial quality"
    ),
    "modern": (
        "Clean modern digital illustration, minimalist design, "
        "vibrant accent colors on neutral background, tech-forward, "
        "flat design elements with depth, premium UI aesthetic"
    ),
    "conceptual": (
        "Conceptual art illustration, symbolic imagery, metaphorical, "
        "thought-provoking composition, rich symbolism, editorial style, "
        "museum-quality digital art"
    ),
}

# Negative prompt elements to avoid (appended to all prompts)
NEGATIVE_PROMPT_SUFFIX = (
    ". No text, no words, no letters, no numbers, no watermarks, "
    "no logos, no signatures. No cartoon style, no clipart."
)

# Scene-type → preferred style mapping
SCENE_STYLE_MAP = {
    "intro": "cinematic",
    "conclusion": "cinematic",
}


@dataclass
class IllustrationResult:
    """Result of generating an illustration for a single scene."""
    label: str
    image_path: str           # local path to downloaded image
    clip_path: str            # local path to animated video clip
    prompt_used: str          # the actual prompt sent to DALL-E
    duration: float           # target clip duration
    success: bool = True
    error: str | None = None


# ══════════════════════════════════════════════════════════════════════
# 1.  PROMPT ENGINEERING — Turn scene text into DALL-E 3 prompts
# ══════════════════════════════════════════════════════════════════════

def _build_scene_prompt(
    scene_text: str,
    scene_label: str,
    scene_index: int,
    total_scenes: int,
    *,
    topic: str = "",
    style_seed: str = "",
) -> str:
    """Convert scene narration text into a DALL-E 3 image prompt.

    Strategy:
      1. Use GPT-style prompt engineering to extract the *visual essence*
         of what's being said (not just keywords)
      2. Append a consistent style directive for premium aesthetic
      3. Add negative prompts to avoid text/watermarks in generated images
    """
    # Pick style based on scene type
    style_key = SCENE_STYLE_MAP.get(scene_label.split("-")[0], "")
    if not style_key:
        # Rotate body scene styles for visual variety
        rng = random.Random(f"style-{style_seed}-{scene_index}")
        style_key = rng.choice(["cinematic", "finance", "modern", "conceptual", "documentary"])

    style_desc = ILLUSTRATION_STYLES[style_key]

    # Truncate scene text to focus on the key visual content
    # DALL-E 3 prompts work best at 200-400 chars
    text_excerpt = scene_text.strip()[:500]

    # Build the visual description prompt
    prompt = (
        f"Create a stunning, premium illustration that visually represents "
        f"this concept: {text_excerpt}\n\n"
        f"Style: {style_desc}"
        f"{NEGATIVE_PROMPT_SUFFIX}"
    )

    return prompt


def _build_scene_prompts_with_ai(
    scene_plans: list,
    *,
    topic: str = "",
    style_seed: str = "",
    openai_api_key: str = "",
) -> list[str]:
    """Use GPT-4o to generate optimal DALL-E 3 prompts for all scenes at once.

    This is MUCH better than naive text extraction because GPT understands
    the *visual metaphor* that best represents each concept.

    Example:
      Scene text: "Compound interest is the 8th wonder of the world.
                   A single dollar invested at age 20 becomes $88 by 65."
      →
      Prompt: "A dramatic visualization of exponential growth — a small
              golden seed growing into a massive tree made of dollar bills,
              with concentric rings showing the passage of decades.
              Cinematic lighting, rich golds and deep greens, 4K detail."
    """
    if not openai_api_key:
        logger.warning("No OpenAI key for AI prompt generation — using basic prompts")
        return [
            _build_scene_prompt(
                getattr(sp, "text", ""),
                getattr(sp, "label", "body"),
                i,
                len(scene_plans),
                topic=topic,
                style_seed=style_seed,
            )
            for i, sp in enumerate(scene_plans)
        ]

    # Build the GPT request for batch prompt generation
    scenes_desc = []
    for i, sp in enumerate(scene_plans):
        label = getattr(sp, "label", f"scene-{i}")
        text = getattr(sp, "text", "")[:400]
        scenes_desc.append(f"Scene {i + 1} ({label}): {text}")

    scenes_block = "\n\n".join(scenes_desc)

    system_prompt = """You are a world-class visual director creating DALL-E 3 image prompts for a premium YouTube video.

Your job: For each scene, create a vivid, specific image prompt that VISUALLY DEPICTS the concept being discussed.

Rules:
1. Each prompt must describe a SINGLE powerful visual that captures the scene's message
2. Use concrete visual metaphors — not abstract concepts
3. Include lighting, composition, color palette, and mood
4. Every prompt must end with: "No text, no words, no letters, no numbers, no watermarks."
5. Keep each prompt 150-300 characters
6. Make consecutive scenes visually distinct but thematically cohesive
7. Think like a film director — what would the audience SEE while hearing these words?

Examples of GREAT prompts:
- For "compound interest": "A tiny golden seed sprouting into a massive tree made of swirling currency and gold coins, with ethereal light rays, cinematic depth of field, rich warm tones"
- For "emergency fund": "A glowing crystalline shield protecting a miniature house from a dramatic storm, photorealistic, dramatic lighting, deep blues and warm amber"
- For "budget planning": "An elegant architectural blueprint unfurling on a mahogany desk, with golden financial instruments and a compass, top-down view, cinematic lighting"

Return ONLY a JSON array of strings, one prompt per scene, in order."""

    user_prompt = (
        f"Video topic: {topic}\n\n"
        f"Generate one DALL-E 3 image prompt per scene:\n\n{scenes_block}"
    )

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.85,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        parsed = json.loads(content)
        # Accept both {"prompts": [...]} and bare [...]
        if isinstance(parsed, list):
            prompts = parsed
        elif isinstance(parsed, dict):
            prompts = parsed.get("prompts", parsed.get("scenes", []))
            if not prompts:
                # Try first list value in the dict
                for v in parsed.values():
                    if isinstance(v, list):
                        prompts = v
                        break
        else:
            prompts = []

        # Ensure we have the right number of prompts
        if len(prompts) != len(scene_plans):
            logger.warning(
                "GPT returned %d prompts for %d scenes — padding/trimming",
                len(prompts), len(scene_plans),
            )
            # Pad with basic prompts if short
            while len(prompts) < len(scene_plans):
                idx = len(prompts)
                sp = scene_plans[idx]
                prompts.append(
                    _build_scene_prompt(
                        getattr(sp, "text", ""),
                        getattr(sp, "label", "body"),
                        idx,
                        len(scene_plans),
                        topic=topic,
                        style_seed=style_seed,
                    )
                )
            prompts = prompts[:len(scene_plans)]

        # Ensure all prompts have the negative suffix
        cleaned = []
        for p in prompts:
            if isinstance(p, str):
                if "no text" not in p.lower():
                    p += NEGATIVE_PROMPT_SUFFIX
                cleaned.append(p)
            else:
                cleaned.append(str(p) + NEGATIVE_PROMPT_SUFFIX)

        logger.info("AI-generated %d DALL-E prompts for %d scenes", len(cleaned), len(scene_plans))
        return cleaned

    except Exception as e:
        logger.warning("GPT prompt generation failed — using basic prompts: %s", e)
        return [
            _build_scene_prompt(
                getattr(sp, "text", ""),
                getattr(sp, "label", "body"),
                i,
                len(scene_plans),
                topic=topic,
                style_seed=style_seed,
            )
            for i, sp in enumerate(scene_plans)
        ]


# ══════════════════════════════════════════════════════════════════════
# 2.  DALL-E 3 IMAGE GENERATION
# ══════════════════════════════════════════════════════════════════════

def _generate_image(
    prompt: str,
    output_path: str,
    *,
    openai_api_key: str,
    size: str = IMAGE_SIZE,
    quality: str = IMAGE_QUALITY,
) -> str:
    """Generate a single image via DALL-E 3 and save it locally.

    Returns the local file path on success.
    Raises ExternalServiceError on failure after retries.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                    "quality": quality,
                    "response_format": "url",
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            image_url = data["data"][0]["url"]

            # Download the image
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_resp.content)

            file_size = os.path.getsize(output_path) / 1024
            logger.info("Generated image: %s (%.0f KB)", output_path, file_size)
            return output_path

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429:
                # Rate limited — wait and retry
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning("DALL-E rate limited — waiting %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
                continue
            elif status == 400:
                # Content policy rejection — try with a sanitized prompt
                logger.warning("DALL-E rejected prompt (content policy) — simplifying")
                prompt = (
                    f"A beautiful, professional illustration related to personal finance "
                    f"and wealth building. Cinematic lighting, premium quality, 4K detail. "
                    f"No text, no words, no watermarks."
                )
                continue
            else:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                raise ExternalServiceError(
                    f"DALL-E 3 image generation failed (HTTP {status}): {e}",
                    user_hint="AI image generation failed. Please check your OpenAI API key and billing.",
                )
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            raise ExternalServiceError(
                f"DALL-E 3 image generation failed: {e}",
                user_hint="AI image generation failed. Please try again.",
            )

    raise ExternalServiceError(
        "DALL-E 3 image generation failed after all retries",
        user_hint="AI image generation failed after multiple attempts. Please try again.",
    )


# ══════════════════════════════════════════════════════════════════════
# 3.  IMAGE → ANIMATED VIDEO CLIP (Ken Burns on stills)
# ══════════════════════════════════════════════════════════════════════

# Pan/zoom directions for visual variety
_ANIMATION_DIRECTIONS = [
    "slow_zoom_in",
    "slow_zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "zoom_to_center",
    "drift_diagonal",
]


def _image_to_animated_clip(
    image_path: str,
    output_path: str,
    duration: float,
    *,
    direction: str = "slow_zoom_in",
    width: int = VIDEO_WIDTH,
    height: int = VIDEO_HEIGHT,
    fps: int = FPS,
) -> str:
    """Convert a static image into a smooth animated video clip.

    Uses FFmpeg zoompan filter for Ken Burns effect — the image slowly
    pans and zooms, creating cinematic motion from a still image.

    This is how premium YouTube channels make AI-generated art look
    like video — slow, deliberate camera movement.

    Memory usage: ~30-50 MB (FFmpeg processes frame-by-frame).
    """
    total_frames = int(duration * fps)
    if total_frames < fps:
        total_frames = fps  # minimum 1 second

    # DALL-E images are 1024×1024.  We'll scale up for zoompan headroom,
    # then output at target resolution.
    # Zoompan needs a source larger than the output to have room to pan.
    src_w = width * 2    # 2560 for 1280 output
    src_h = height * 2   # 1440 for 720 output

    # Define zoompan expressions per direction
    # z = zoom factor, x/y = pan position
    # All expressions use 'on' (frame number) for smooth animation
    zoom_start = 1.0
    zoom_end = 1.3       # 30% zoom range over duration
    z_inc = (zoom_end - zoom_start) / max(total_frames, 1)

    if direction == "slow_zoom_in":
        zp = (
            f"zoompan=z='min({zoom_start}+{z_inc:.6f}*on,{zoom_end})':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "slow_zoom_out":
        zp = (
            f"zoompan=z='max({zoom_end}-{z_inc:.6f}*on,{zoom_start})':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "pan_left":
        # Zoom in slightly, pan from right to left
        zp = (
            f"zoompan=z='1.15':"
            f"d={total_frames}:"
            f"x='max(iw-iw/zoom-on*{0.8 * width / max(total_frames, 1):.6f},0)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "pan_right":
        zp = (
            f"zoompan=z='1.15':"
            f"d={total_frames}:"
            f"x='min(on*{0.8 * width / max(total_frames, 1):.6f},iw-iw/zoom)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "pan_up":
        zp = (
            f"zoompan=z='1.15':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='max(ih-ih/zoom-on*{0.6 * height / max(total_frames, 1):.6f},0)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "pan_down":
        zp = (
            f"zoompan=z='1.15':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='min(on*{0.6 * height / max(total_frames, 1):.6f},ih-ih/zoom)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "zoom_to_center":
        # Start wide, zoom into center
        zp = (
            f"zoompan=z='min(1.0+{z_inc * 1.5:.6f}*on,1.45)':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "drift_diagonal":
        # Gentle diagonal drift with slight zoom
        zp = (
            f"zoompan=z='min(1.05+{z_inc * 0.5:.6f}*on,1.2)':"
            f"d={total_frames}:"
            f"x='min(on*{0.4 * width / max(total_frames, 1):.6f},iw-iw/zoom)':"
            f"y='min(on*{0.3 * height / max(total_frames, 1):.6f},ih-ih/zoom)':"
            f"s={width}x{height}:fps={fps}"
        )
    else:
        # Default: slow zoom in
        zp = (
            f"zoompan=z='min({zoom_start}+{z_inc:.6f}*on,{zoom_end})':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )

    # Build FFmpeg command:
    # 1. Scale source image up for zoompan headroom
    # 2. Apply zoompan for smooth Ken Burns animation
    # 3. Ensure pixel format for H.264 compatibility
    vf = (
        f"scale={src_w}:{src_h}:force_original_aspect_ratio=decrease,"
        f"pad={src_w}:{src_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"format=rgba,"
        f"{zp},"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", vf,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-nostdin",
        "-threads", "1",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("FFmpeg image→clip failed: %s", result.stderr[-500:])
            raise RuntimeError(f"FFmpeg failed: {result.stderr[-200:]}")

        logger.info("Animated clip: %s (%.1fs, %s)", output_path, duration, direction)
        return output_path

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg timed out converting image to clip: {image_path}")


def _pick_direction(scene_index: int, seed: str = "") -> str:
    """Deterministically pick an animation direction for variety."""
    rng = random.Random(f"anim-{seed}-{scene_index}")
    return rng.choice(_ANIMATION_DIRECTIONS)


# ══════════════════════════════════════════════════════════════════════
# 4.  MAIN ENTRY POINT — Generate illustrations for all scenes
# ══════════════════════════════════════════════════════════════════════

def generate_illustrations_for_scenes(
    scene_plans: list,  # list[ScenePlan] — avoid import cycle
    *,
    openai_api_key: str = "",
    topic: str = "",
    style_seed: str = "",
    clips_dir: Path | None = None,
    image_quality: str = IMAGE_QUALITY,
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    video_fps: int = FPS,
) -> list[dict]:
    """Generate AI illustrations for each scene and convert to video clips.

    Returns data in the SAME FORMAT as stock_footage.download_clips_for_scenes():
        [{"label": "intro", "clips": ["output/clips/clip_0.mp4"], "duration": 12.5}, ...]

    This is a drop-in replacement — video_builder doesn't need to know
    whether clips came from stock footage or AI generation.

    Parameters
    ----------
    scene_plans : list[ScenePlan]
        Scene plans from scene_planner.plan_scenes().
    openai_api_key : str
        OpenAI API key for DALL-E 3 + GPT-4o.
    topic : str
        Video topic for prompt context.
    style_seed : str
        Seed for deterministic style variation.
    clips_dir : Path
        Where to save generated clips.
    image_quality : str
        DALL-E quality: "standard" ($0.04) or "hd" ($0.08).
    """
    if not openai_api_key:
        raise ExternalServiceError(
            "OpenAI API key required for AI illustration generation",
            user_hint="AI illustrations require an OpenAI API key. Please add one in Settings.",
        )

    _effective_clips_dir = clips_dir or CLIPS_DIR
    _effective_clips_dir.mkdir(parents=True, exist_ok=True)

    # Clean out old clips
    for old in _effective_clips_dir.glob("clip_*.mp4"):
        old.unlink()
    for old in _effective_clips_dir.glob("scene_*.png"):
        old.unlink()

    logger.info(
        "AI Illustration: generating images for %d scenes (quality=%s)",
        len(scene_plans), image_quality,
    )

    # ── Step 1: Generate DALL-E prompts for all scenes ───────────────
    prompts = _build_scene_prompts_with_ai(
        scene_plans,
        topic=topic,
        style_seed=style_seed,
        openai_api_key=openai_api_key,
    )

    # ── Step 2: Generate images + convert to clips (sequential) ──────
    # Sequential to respect DALL-E rate limits (7 img/min) and minimize
    # memory on Railway.  Each image is generated, downloaded, converted
    # to clip, then the image can be discarded.
    scene_clip_data: list[dict] = []

    for i, sp in enumerate(scene_plans):
        label = getattr(sp, "label", f"scene-{i}")
        duration = getattr(sp, "estimated_duration", 8.0)
        prompt = prompts[i] if i < len(prompts) else f"Premium illustration for {topic}"

        image_path = str(_effective_clips_dir / f"scene_{i:03d}.png")
        clip_path = str(_effective_clips_dir / f"clip_{i}.mp4")

        try:
            # Generate image via DALL-E 3
            logger.info(
                "Scene %d/%d ('%s'): generating AI illustration…",
                i + 1, len(scene_plans), label,
            )
            _generate_image(
                prompt,
                image_path,
                openai_api_key=openai_api_key,
                quality=image_quality,
            )

            # Convert to animated video clip
            direction = _pick_direction(i, seed=style_seed or topic)
            _image_to_animated_clip(
                image_path,
                clip_path,
                duration,
                direction=direction,
                width=video_width,
                height=video_height,
                fps=video_fps,
            )

            scene_clip_data.append({
                "label": label,
                "clips": [clip_path],
                "duration": duration,
                "_prompt": prompt[:200],  # Store truncated prompt for debugging
            })

            logger.info(
                "Scene %d/%d ('%s'): ✓ image + clip ready (%.1fs, %s)",
                i + 1, len(scene_plans), label, duration, direction,
            )

            # Small delay between DALL-E calls to respect rate limits
            if i < len(scene_plans) - 1:
                time.sleep(1.0)

        except Exception as e:
            logger.warning(
                "Scene %d ('%s') illustration failed: %s — will use fallback",
                i, label, e,
            )
            # Append empty entry — video_builder handles missing clips gracefully
            scene_clip_data.append({
                "label": label,
                "clips": [],
                "duration": duration,
            })

    total_clips = sum(len(sd["clips"]) for sd in scene_clip_data)
    total_images = sum(1 for sd in scene_clip_data if sd["clips"])

    if total_clips == 0:
        raise ExternalServiceError(
            "Could not generate any AI illustrations. "
            "Check your OpenAI API key and billing.",
            user_hint="AI image generation failed for all scenes. Please check your OpenAI API key.",
        )

    logger.info(
        "AI Illustration complete: %d/%d scenes illustrated, %d clips → %s/",
        total_images, len(scene_plans), total_clips, _effective_clips_dir,
    )

    # Clean up image files to save disk space (clips are all we need)
    for img in _effective_clips_dir.glob("scene_*.png"):
        try:
            img.unlink()
        except Exception:
            pass

    return scene_clip_data


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # Quick test with a mock scene plan
    @dataclass
    class MockScene:
        label: str
        text: str
        estimated_duration: float = 8.0

    test_scenes = [
        MockScene("intro", "Compound interest is the 8th wonder of the world. Let me show you why."),
        MockScene("body-1", "If you invest just $100 per month starting at age 25, by 65 you'll have over $500,000."),
        MockScene("conclusion", "Start today. Your future self will thank you."),
    ]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Set OPENAI_API_KEY to test")
        sys.exit(1)

    result = generate_illustrations_for_scenes(
        test_scenes,
        openai_api_key=api_key,
        topic="The Power of Compound Interest",
    )
    for sd in result:
        print(f"  {sd['label']}: {len(sd['clips'])} clips, {sd['duration']:.1f}s")
