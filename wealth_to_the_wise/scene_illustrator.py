"""
scene_illustrator.py — AI-Generated Scene Videos (DALL-E 3 + Runway)

Generates custom AI VIDEO CLIPS for each scene in a video.  Pipeline:
  1.  GPT-4o  → cinematic image prompt per scene
  2.  DALL-E 3 → custom still illustration per scene
  3.  Runway gen4_turbo (image-to-video) → real AI-generated motion video

The result is ACTUAL MOVING VISUALS — objects animate, cameras pan through
3D scenes, particles flow — not just static images with a Ken Burns zoom.
This is the *premium differentiator* for Pro ($79) and Agency ($199) plans.

Fallback chain per scene:
  Runway img→vid ─fail─▶ FFmpeg zoompan on DALL-E image ─fail─▶ empty clip entry

Pipeline integration:
  • Returns data in the same format as stock_footage.download_clips_for_scenes()
    so video_builder needs zero changes to its interface
  • [{"label": "intro", "clips": ["clip_0.mp4"], "duration": 12.5}, ...]

Cost per video (Pro, 14 scenes × 5s × gen4_turbo):
  DALL-E images: $0.04 × 14 = $0.56
  Runway video:  $0.25 × 14 = $3.50
  Total: ~$4.06/video  (acceptable for $79/mo plan)

Cost per video (Agency, 18 scenes × 5s × gen4_turbo):
  DALL-E images: $0.08 × 18 = $1.44  (HD quality)
  Runway video:  $0.25 × 18 = $4.50
  Total: ~$5.94/video  (acceptable for $199/mo plan)

Usage:
    from scene_illustrator import generate_illustrations_for_scenes

    scene_clip_data = generate_illustrations_for_scenes(
        scene_plans,
        openai_api_key="sk-...",
        runway_api_key="key_...",    # NEW — Runway API key
        clips_dir=Path("output/clips"),
    )
"""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import subprocess
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

# ── Runway API config ───────────────────────────────────────────────
RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"
RUNWAY_API_VERSION = "2024-11-06"
RUNWAY_DEFAULT_MODEL = "gen4_turbo"      # 5 credits/sec = $0.05/sec
RUNWAY_DEFAULT_DURATION = 5              # 5-second clips (25 credits = $0.25)
RUNWAY_POLL_INTERVAL = 5.0              # poll every 5s (API docs: ≥5s between polls)
RUNWAY_MAX_POLL_TIME = 300              # max 5 minutes per clip
RUNWAY_MAX_RETRIES = 1                  # retry once on transient failures

# Supported Runway output ratios
RUNWAY_RATIOS = [
    "1280:720", "720:1280", "1104:832", "960:960", "832:1104", "1584:672",
]

# ── Visual style presets for prompts ────────────────────────────────
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
    image_path: str
    clip_path: str
    prompt_used: str
    duration: float
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
    """Convert scene narration text into a DALL-E 3 image prompt."""
    style_key = SCENE_STYLE_MAP.get(scene_label.split("-")[0], "")
    if not style_key:
        rng = random.Random(f"style-{style_seed}-{scene_index}")
        style_key = rng.choice(["cinematic", "finance", "modern", "conceptual", "documentary"])

    style_desc = ILLUSTRATION_STYLES[style_key]
    text_excerpt = scene_text.strip()[:500]

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
    """Use GPT-4o to generate optimal DALL-E 3 prompts for all scenes."""
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

    scenes_desc = []
    for i, sp in enumerate(scene_plans):
        label = getattr(sp, "label", f"scene-{i}")
        text = getattr(sp, "text", "")[:400]
        scenes_desc.append(f"Scene {i + 1} ({label}): {text}")

    scenes_block = "\n\n".join(scenes_desc)

    system_prompt = (
        "You are a world-class visual director creating DALL-E 3 image prompts "
        "for a premium YouTube video.\n\n"
        "Your job: For each scene, create a vivid, specific image prompt that "
        "VISUALLY DEPICTS the concept being discussed.\n\n"
        "Rules:\n"
        "1. Each prompt must describe a SINGLE powerful visual that captures "
        "the scene's message\n"
        "2. Use concrete visual metaphors — not abstract concepts\n"
        "3. Include lighting, composition, color palette, and mood\n"
        "4. Every prompt must end with: \"No text, no words, no letters, "
        "no numbers, no watermarks.\"\n"
        "5. Keep each prompt 150-300 characters\n"
        "6. Make consecutive scenes visually distinct but thematically cohesive\n"
        "7. Think like a film director — what would the audience SEE while "
        "hearing these words?\n\n"
        "Return ONLY a JSON object with key \"prompts\" containing an array "
        "of strings, one prompt per scene, in order."
    )

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
        if isinstance(parsed, list):
            prompts = parsed
        elif isinstance(parsed, dict):
            prompts = parsed.get("prompts", parsed.get("scenes", []))
            if not prompts:
                for v in parsed.values():
                    if isinstance(v, list):
                        prompts = v
                        break
        else:
            prompts = []

        if len(prompts) != len(scene_plans):
            logger.warning(
                "GPT returned %d prompts for %d scenes — padding/trimming",
                len(prompts), len(scene_plans),
            )
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
            prompts = prompts[: len(scene_plans)]

        cleaned = []
        for p in prompts:
            if isinstance(p, str):
                if "no text" not in p.lower():
                    p += NEGATIVE_PROMPT_SUFFIX
                cleaned.append(p)
            else:
                cleaned.append(str(p) + NEGATIVE_PROMPT_SUFFIX)

        logger.info(
            "AI-generated %d DALL-E prompts for %d scenes",
            len(cleaned), len(scene_plans),
        )
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
    """Generate a single image via DALL-E 3 and save it locally."""
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
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(
                    "DALL-E rate limited — waiting %.1fs (attempt %d)",
                    wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            elif status == 400:
                logger.warning("DALL-E rejected prompt (content policy) — simplifying")
                prompt = (
                    "A beautiful, professional illustration related to personal "
                    "finance and wealth building. Cinematic lighting, premium "
                    "quality, 4K detail. No text, no words, no watermarks."
                )
                continue
            else:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                raise ExternalServiceError(
                    f"DALL-E 3 image generation failed (HTTP {status}): {e}",
                    user_hint=(
                        "AI image generation failed. Please check your "
                        "OpenAI API key and billing."
                    ),
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
        user_hint="AI image generation failed after multiple attempts.",
    )


# ══════════════════════════════════════════════════════════════════════
# 3.  RUNWAY API — Image-to-Video (REAL AI-generated motion)
# ══════════════════════════════════════════════════════════════════════

def _runway_create_task(
    image_url: str,
    motion_prompt: str,
    *,
    runway_api_key: str,
    model: str = RUNWAY_DEFAULT_MODEL,
    duration: int = RUNWAY_DEFAULT_DURATION,
    ratio: str = "1280:720",
) -> str:
    """Start a Runway image-to-video task.  Returns the task ID.

    API: POST /v1/image_to_video
    """
    payload: dict[str, Any] = {
        "model": model,
        "promptText": motion_prompt[:1000],
        "promptImage": image_url,
        "ratio": ratio,
        "duration": max(2, min(duration, 10)),
    }

    resp = requests.post(
        f"{RUNWAY_API_BASE}/image_to_video",
        headers={
            "Authorization": f"Bearer {runway_api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": RUNWAY_API_VERSION,
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    task_id = data["id"]
    logger.info(
        "Runway task created: %s (model=%s, duration=%ds)",
        task_id, model, duration,
    )
    return task_id


def _runway_poll_task(
    task_id: str,
    *,
    runway_api_key: str,
    poll_interval: float = RUNWAY_POLL_INTERVAL,
    max_poll_time: float = RUNWAY_MAX_POLL_TIME,
) -> dict:
    """Poll a Runway task until it completes or fails.

    Returns the full task dict including output URLs.
    """
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > max_poll_time:
            raise ExternalServiceError(
                f"Runway task {task_id} timed out after {max_poll_time:.0f}s",
                user_hint="AI video generation timed out. Please try again.",
            )

        resp = requests.get(
            f"{RUNWAY_API_BASE}/tasks/{task_id}",
            headers={
                "Authorization": f"Bearer {runway_api_key}",
                "X-Runway-Version": RUNWAY_API_VERSION,
            },
            timeout=15,
        )
        resp.raise_for_status()
        task = resp.json()

        status = task.get("status", "UNKNOWN")
        if status == "SUCCEEDED":
            logger.info("Runway task %s completed (%.0fs)", task_id, elapsed)
            return task
        elif status in ("FAILED", "CANCELLED"):
            failure = task.get("failure", "Unknown error")
            raise ExternalServiceError(
                f"Runway task {task_id} failed: {failure}",
                user_hint="AI video generation failed. Please try again.",
            )
        else:
            # PENDING, RUNNING, THROTTLED — keep polling
            logger.debug(
                "Runway task %s: %s (%.0fs elapsed)",
                task_id, status, elapsed,
            )
            time.sleep(poll_interval)


def _runway_download_video(task: dict, output_path: str) -> str:
    """Download the video output from a completed Runway task."""
    output_list = task.get("output", [])
    if not output_list:
        raise ExternalServiceError(
            "Runway task completed but returned no output",
            user_hint="AI video generation completed but no video was returned.",
        )

    video_url = output_list[0]
    if isinstance(video_url, dict):
        video_url = video_url.get("url", video_url.get("uri", ""))

    if not video_url:
        raise ExternalServiceError(
            "Runway task output has no URL",
            user_hint="AI video generation returned an empty result.",
        )

    resp = requests.get(video_url, timeout=60, stream=True)
    resp.raise_for_status()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)

    file_size = os.path.getsize(output_path) / 1024
    logger.info("Downloaded Runway video: %s (%.0f KB)", output_path, file_size)
    return output_path


def _generate_ai_video(
    image_path: str,
    output_path: str,
    motion_prompt: str,
    *,
    runway_api_key: str,
    model: str = RUNWAY_DEFAULT_MODEL,
    duration: int = RUNWAY_DEFAULT_DURATION,
    ratio: str = "1280:720",
) -> str:
    """Full Runway image-to-video pipeline for a single scene.

    1. Read image → base64 data URI
    2. Create image-to-video task
    3. Poll until complete
    4. Download video to output_path
    """
    # Read image and build data URI for Runway API
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime = mime_map.get(ext, "image/png")
    data_uri = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"

    # Create task with retry on rate-limit
    for attempt in range(RUNWAY_MAX_RETRIES + 1):
        try:
            task_id = _runway_create_task(
                data_uri,
                motion_prompt,
                runway_api_key=runway_api_key,
                model=model,
                duration=duration,
                ratio=ratio,
            )
            break
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429 and attempt < RUNWAY_MAX_RETRIES:
                wait = 10.0 * (attempt + 1)
                logger.warning("Runway rate limited — waiting %.0fs", wait)
                time.sleep(wait)
                continue
            raise
        except Exception:
            if attempt < RUNWAY_MAX_RETRIES:
                time.sleep(5.0)
                continue
            raise

    # Poll until complete
    task = _runway_poll_task(task_id, runway_api_key=runway_api_key)

    # Download the resulting video
    return _runway_download_video(task, output_path)


def _build_motion_prompt(scene_text: str, scene_label: str) -> str:
    """Build a concise motion description for Runway image-to-video.

    Tells Runway HOW to animate the DALL-E image — camera motion,
    particle effects, element animation, etc.
    """
    label_base = scene_label.split("-")[0]

    if label_base == "intro":
        return (
            "Slow dramatic camera push-in with parallax depth effect. "
            "Subtle particles and light rays animate in the scene. "
            "Cinematic opening shot feel."
        )
    elif label_base == "conclusion":
        return (
            "Slow camera pull-back revealing the full scene. "
            "Warm golden light intensifies. Triumphant, hopeful mood. "
            "Subtle floating particles."
        )

    # Body scenes — tailor motion to content keywords
    text_lower = scene_text.lower()[:200]

    if any(w in text_lower for w in ["grow", "increase", "compound", "rise", "wealth"]):
        return (
            "Upward camera movement. Elements in the scene grow and expand. "
            "Light intensifies. Particles float upward. Growth and abundance."
        )
    elif any(w in text_lower for w in ["risk", "danger", "loss", "crash", "fall"]):
        return (
            "Slow dramatic camera movement. Dark clouds or shadows shift. "
            "Dramatic lighting changes. Tension and urgency in the motion."
        )
    elif any(w in text_lower for w in ["save", "protect", "secure", "safety", "fund"]):
        return (
            "Gentle camera orbit. A protective glow pulses around key elements. "
            "Calm, steady movement conveying security and stability."
        )
    elif any(w in text_lower for w in ["plan", "strategy", "step", "build", "create"]):
        return (
            "Smooth tracking shot across the scene. Elements assemble and "
            "organize. Methodical, purposeful camera movement."
        )

    return (
        "Smooth cinematic camera movement with subtle parallax. "
        "Elements in the scene gently animate. Soft lighting shifts. "
        "Professional, polished motion."
    )


# ══════════════════════════════════════════════════════════════════════
# 3b.  FALLBACK — FFmpeg zoompan (if Runway unavailable/fails)
# ══════════════════════════════════════════════════════════════════════

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
    """FALLBACK: Convert a static image into a Ken Burns clip via FFmpeg.

    Used only when Runway API is unavailable (no key, rate limit, error).
    """
    total_frames = int(duration * fps)
    if total_frames < fps:
        total_frames = fps

    src_w = width * 2
    src_h = height * 2

    zoom_start = 1.0
    zoom_end = 1.3
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
        zp = (
            f"zoompan=z='min(1.0+{z_inc * 1.5:.6f}*on,1.45)':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
    elif direction == "drift_diagonal":
        zp = (
            f"zoompan=z='min(1.05+{z_inc * 0.5:.6f}*on,1.2)':"
            f"d={total_frames}:"
            f"x='min(on*{0.4 * width / max(total_frames, 1):.6f},iw-iw/zoom)':"
            f"y='min(on*{0.3 * height / max(total_frames, 1):.6f},ih-ih/zoom)':"
            f"s={width}x{height}:fps={fps}"
        )
    else:
        zp = (
            f"zoompan=z='min({zoom_start}+{z_inc:.6f}*on,{zoom_end})':"
            f"d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )

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

        logger.info(
            "Animated clip (fallback): %s (%.1fs, %s)",
            output_path, duration, direction,
        )
        return output_path

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"FFmpeg timed out converting image to clip: {image_path}"
        )


def _pick_direction(scene_index: int, seed: str = "") -> str:
    """Deterministically pick an animation direction for variety."""
    rng = random.Random(f"anim-{seed}-{scene_index}")
    return rng.choice(_ANIMATION_DIRECTIONS)


# ══════════════════════════════════════════════════════════════════════
# 4.  MAIN ENTRY POINT — Generate AI video clips for all scenes
# ══════════════════════════════════════════════════════════════════════

def generate_illustrations_for_scenes(
    scene_plans: list,  # list[ScenePlan] — avoid import cycle
    *,
    openai_api_key: str = "",
    runway_api_key: str = "",
    topic: str = "",
    style_seed: str = "",
    clips_dir: Path | None = None,
    image_quality: str = IMAGE_QUALITY,
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    video_fps: int = FPS,
    ai_video_model: str = RUNWAY_DEFAULT_MODEL,
    ai_video_duration: int = RUNWAY_DEFAULT_DURATION,
) -> list[dict]:
    """Generate AI video clips for each scene.

    Pipeline per scene:
      1. DALL-E 3 → custom illustration (still image)
      2. Runway gen4_turbo → image-to-video (real AI motion)
      3. Fallback: FFmpeg zoompan if Runway unavailable/fails

    Returns data in the SAME FORMAT as stock_footage.download_clips_for_scenes():
        [{"label": "intro", "clips": [".../clip_0.mp4"], "duration": 12.5}, ...]

    Parameters
    ----------
    runway_api_key : str
        Runway API key.  If empty, falls back to FFmpeg zoompan.
    ai_video_model : str
        Runway model: "gen4_turbo" (cheap) or "gen4.5" (premium).
    ai_video_duration : int
        Clip duration in seconds (2-10).
    """
    if not openai_api_key:
        raise ExternalServiceError(
            "OpenAI API key required for AI illustration generation",
            user_hint=(
                "AI illustrations require an OpenAI API key. "
                "Please add one in Settings."
            ),
        )

    _clips_dir = clips_dir or CLIPS_DIR
    _clips_dir.mkdir(parents=True, exist_ok=True)

    # Clean out old clips
    for old in _clips_dir.glob("clip_*.mp4"):
        old.unlink()
    for old in _clips_dir.glob("scene_*.png"):
        old.unlink()

    _use_runway = bool(runway_api_key)
    if _use_runway:
        logger.info(
            "AI Video Generation: %d scenes (model=%s, duration=%ds, quality=%s)",
            len(scene_plans), ai_video_model, ai_video_duration, image_quality,
        )
    else:
        logger.info(
            "AI Illustration (fallback): %d scenes — no Runway key, using zoompan",
            len(scene_plans),
        )

    # ── Step 1: Generate DALL-E prompts for all scenes ───────────────
    prompts = _build_scene_prompts_with_ai(
        scene_plans,
        topic=topic,
        style_seed=style_seed,
        openai_api_key=openai_api_key,
    )

    # ── Step 2: Generate images + convert to video clips ─────────────
    scene_clip_data: list[dict] = []
    runway_successes = 0
    fallback_count = 0

    # Determine Runway aspect ratio
    ratio = f"{video_width}:{video_height}"
    if ratio not in RUNWAY_RATIOS:
        ratio = "1280:720"

    for i, sp in enumerate(scene_plans):
        label = getattr(sp, "label", f"scene-{i}")
        duration = getattr(sp, "estimated_duration", 8.0)
        prompt = prompts[i] if i < len(prompts) else f"Premium illustration for {topic}"

        image_path = str(_clips_dir / f"scene_{i:03d}.png")
        clip_path = str(_clips_dir / f"clip_{i}.mp4")

        try:
            # Step A: Generate image via DALL-E 3
            logger.info(
                "Scene %d/%d ('%s'): generating DALL-E illustration…",
                i + 1, len(scene_plans), label,
            )
            _generate_image(
                prompt,
                image_path,
                openai_api_key=openai_api_key,
                quality=image_quality,
            )

            # Step B: Convert to AI video (Runway) or fallback (zoompan)
            clip_generated = False

            if _use_runway:
                try:
                    motion_prompt = _build_motion_prompt(
                        getattr(sp, "text", ""), label,
                    )
                    logger.info(
                        "Scene %d/%d ('%s'): generating AI video via Runway %s…",
                        i + 1, len(scene_plans), label, ai_video_model,
                    )
                    _generate_ai_video(
                        image_path,
                        clip_path,
                        motion_prompt,
                        runway_api_key=runway_api_key,
                        model=ai_video_model,
                        duration=ai_video_duration,
                        ratio=ratio,
                    )
                    clip_generated = True
                    runway_successes += 1
                    logger.info(
                        "Scene %d/%d ('%s'): ✓ AI video ready (Runway %s, %ds)",
                        i + 1, len(scene_plans), label,
                        ai_video_model, ai_video_duration,
                    )
                except Exception as runway_err:
                    logger.warning(
                        "Scene %d ('%s') Runway failed — zoompan fallback: %s",
                        i, label, runway_err,
                    )

            if not clip_generated:
                # Fallback: FFmpeg zoompan
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
                fallback_count += 1
                logger.info(
                    "Scene %d/%d ('%s'): ✓ clip ready (zoompan, %.1fs)",
                    i + 1, len(scene_plans), label, duration,
                )

            scene_clip_data.append({
                "label": label,
                "clips": [clip_path],
                "duration": duration,
                "_prompt": prompt[:200],
                "_method": "runway" if clip_generated else "zoompan",
            })

            # Delay between API calls to respect rate limits
            if i < len(scene_plans) - 1:
                time.sleep(1.0)

        except Exception as e:
            logger.warning(
                "Scene %d ('%s') failed entirely: %s — empty entry",
                i, label, e,
            )
            scene_clip_data.append({
                "label": label,
                "clips": [],
                "duration": duration,
            })

    total_clips = sum(len(sd["clips"]) for sd in scene_clip_data)

    if total_clips == 0:
        raise ExternalServiceError(
            "Could not generate any AI illustrations. "
            "Check your OpenAI API key and billing.",
            user_hint=(
                "AI image generation failed for all scenes. "
                "Please check your OpenAI API key."
            ),
        )

    logger.info(
        "AI Video Generation complete: %d/%d scenes "
        "(%d Runway, %d zoompan fallback) → %s/",
        total_clips, len(scene_plans),
        runway_successes, fallback_count, _clips_dir,
    )

    # Clean up image files to save disk space
    for img in _clips_dir.glob("scene_*.png"):
        try:
            img.unlink()
        except Exception:
            pass

    return scene_clip_data


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    @dataclass
    class MockScene:
        label: str
        text: str
        estimated_duration: float = 8.0

    test_scenes = [
        MockScene(
            "intro",
            "Compound interest is the 8th wonder of the world. "
            "Let me show you why.",
        ),
        MockScene(
            "body-1",
            "If you invest just $100 per month starting at age 25, "
            "by 65 you'll have over $500,000.",
        ),
        MockScene("conclusion", "Start today. Your future self will thank you."),
    ]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    runway_key = os.environ.get("RUNWAYML_API_SECRET", "")

    if not api_key:
        print("Set OPENAI_API_KEY to test")
        sys.exit(1)

    result = generate_illustrations_for_scenes(
        test_scenes,
        openai_api_key=api_key,
        runway_api_key=runway_key,
        topic="The Power of Compound Interest",
    )
    for sd in result:
        method = sd.get("_method", "unknown")
        print(
            f"  {sd['label']}: {len(sd['clips'])} clips, "
            f"{sd['duration']:.1f}s ({method})"
        )
