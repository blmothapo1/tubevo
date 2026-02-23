"""
video_builder.py — Assemble a cinematic video from stock footage + voiceover.

Creates a video with:
  • Stock footage B-roll clips stitched together with crossfade transitions
  • Animated subtitle captions with fade-in and semi-transparent background boxes
  • Animated title card intro + subscribe outro card
  • Subtle Ken Burns (slow zoom) effect on each clip
  • Thin progress bar along the bottom
  • Channel branding lower-third
  • Professional color grading (slight dark overlay for text readability)

Usage:
    from video_builder import build_video

    video_path = build_video(
        audio_path="output/voiceover.mp3",
        title="5 Frugal Habits That Build Wealth Fast",
        script="Your script text ...",
    )
    # → "output/final_video.mp4"
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

logger = logging.getLogger("wealth_to_the_wise.video_builder")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Video settings ───────────────────────────────────────────────────
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 30                  # ↑ from 24 → smoother playback

# ── Styling ──────────────────────────────────────────────────────────
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_BODY = "/System/Library/Fonts/Supplemental/Arial.ttf"

# Caption style — large, centered, white text with dark stroke
CAPTION_FONT_SIZE = 62        # ↑ slightly larger for readability
CAPTION_COLOR = "white"
CAPTION_STROKE_COLOR = "black"
CAPTION_STROKE_WIDTH = 3
CAPTION_BG_COLOR = (0, 0, 0)  # semi-transparent background box behind captions
CAPTION_BG_OPACITY = 0.55
CAPTION_FADE_DURATION = 0.30  # fade-in duration (seconds)

# Branding
ACCENT_COLOR = "#00D4AA"
ACCENT_COLOR_RGB = (0, 212, 170)
BRAND_FONT_SIZE = 32

# Crossfade duration between clips (seconds)
CROSSFADE_DURATION = 0.8

# Dark overlay opacity on stock footage (0.0-1.0) for text readability
DARK_OVERLAY_OPACITY = 0.35  # ↓ slightly less dark — footage is more visible

# Title card / outro durations
TITLE_CARD_DURATION = 3.5     # seconds
OUTRO_CARD_DURATION = 4.0     # seconds

# Number of stock clips to download (more = more visual variety)
NUM_STOCK_CLIPS = 12          # ↑ from 6

# Encoding quality
ENCODING_PRESET = "medium"    # good quality/speed balance
VIDEO_BITRATE = "8000k"      # explicit bitrate for consistent quality


def _split_script_to_sentences(script: str) -> list[str]:
    """Split a script into individual sentences for caption display.

    Also breaks overly long sentences so each caption fits comfortably.
    """
    raw = re.split(r'(?<=[.!?])\s+', script.strip())
    sentences = [s.strip() for s in raw if s.strip()]

    # Break very long sentences at commas / colons / dashes
    final: list[str] = []
    for sent in sentences:
        if len(sent) > 100:
            parts = re.split(r'(?<=,)\s+|(?<=:)\s+|(?<=—)\s*|(?<=-)\s+', sent)
            parts = [p.strip() for p in parts if p.strip()]
            final.extend(parts)
        else:
            final.append(sent)

    return final


def _prepare_stock_clips(
    clip_paths: list[str],
    target_duration: float,
) -> list:
    """Load stock clips and trim/loop them to fill the target duration.

    Each clip is loaded at native resolution, resized to target, and ready
    to go.  (Ken Burns is skipped for render-speed; the crossfade transitions
    between 12 clips already give plenty of visual motion.)
    """
    if not clip_paths:
        return [ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=(15, 15, 15),
        ).with_duration(target_duration)]

    raw_clips = []
    for path in clip_paths:
        try:
            clip = VideoFileClip(path)
            clip = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))
            raw_clips.append(clip)
        except Exception as e:
            logger.warning("Could not load clip %s: %s", path, e)

    if not raw_clips:
        return [ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=(15, 15, 15),
        ).with_duration(target_duration)]

    total_raw_duration = sum(c.duration for c in raw_clips)

    if total_raw_duration >= target_duration:
        trimmed = []
        remaining = target_duration
        for clip in raw_clips:
            if remaining <= 0:
                clip.close()
                break
            share = max(3.0, (clip.duration / total_raw_duration) * target_duration)
            share = min(share, remaining, clip.duration)
            segment = clip.subclipped(0, share)
            trimmed.append(segment)
            remaining -= share
        return trimmed
    else:
        looped = []
        remaining = target_duration
        idx = 0
        while remaining > 0.5:
            clip = raw_clips[idx % len(raw_clips)]
            use_duration = min(clip.duration, remaining)
            if use_duration < 1.0:
                break
            segment = clip.subclipped(0, use_duration)
            looped.append(segment)
            remaining -= use_duration
            idx += 1
        return looped


def _create_caption_clips(
    sentences: list[str],
    total_duration: float,
) -> list:
    """Create timed caption TextClips with fade-in + semi-transparent background box.

    Timing is proportional to word count so that longer sentences stay on
    screen longer — this keeps the subtitles closely in sync with the
    narration instead of drifting out of alignment.
    """
    if not sentences:
        return []

    captions = []

    # Weight each sentence by word count so timing matches speech pacing
    word_counts = [max(len(s.split()), 1) for s in sentences]
    total_words = sum(word_counts)

    # Build start/end times proportionally
    current_time = 0.0
    timing: list[tuple[float, float]] = []
    for wc in word_counts:
        duration = (wc / total_words) * total_duration
        timing.append((current_time, current_time + duration))
        current_time += duration

    for i, sentence in enumerate(sentences):
        start, end = timing[i]

        wrapped = textwrap.fill(sentence, width=42)

        try:
            # ── Text clip ──
            txt = TextClip(
                text=wrapped,
                font_size=CAPTION_FONT_SIZE,
                color=CAPTION_COLOR,
                font=FONT,
                stroke_color=CAPTION_STROKE_COLOR,
                stroke_width=CAPTION_STROKE_WIDTH,
                method="caption",
                size=(VIDEO_WIDTH - 200, None),
                text_align="center",
            )

            # ── Background box behind the caption ──
            txt_w, txt_h = txt.size
            pad_x, pad_y = 40, 20
            bg_box = ColorClip(
                size=(txt_w + pad_x * 2, txt_h + pad_y * 2),
                color=CAPTION_BG_COLOR,
            )
            bg_box = bg_box.with_opacity(CAPTION_BG_OPACITY)

            # Position both centred near the bottom
            caption_y = VIDEO_HEIGHT - 260
            bg_box = bg_box.with_position(
                ("center", caption_y - pad_y)
            ).with_start(start).with_end(end)

            txt = txt.with_position(("center", caption_y))
            txt = txt.with_start(start).with_end(end)

            # ── Fade-in effect ──
            try:
                from moviepy.video.fx import CrossFadeIn
                bg_box = bg_box.with_effects([CrossFadeIn(CAPTION_FADE_DURATION)])
                txt = txt.with_effects([CrossFadeIn(CAPTION_FADE_DURATION)])
            except Exception:
                pass  # graceful fallback if fx not available

            captions.append(bg_box)
            captions.append(txt)
        except Exception as e:
            logger.warning("Caption creation failed for sentence %d: %s", i, e)

    return captions


def _create_branding_clip(duration: float):
    """Persistent channel watermark in the top-left with accent underline."""
    try:
        brand = TextClip(
            text="WEALTH TO THE WISE",
            font_size=BRAND_FONT_SIZE,
            color=ACCENT_COLOR,
            font=FONT,
        )
        brand = brand.with_position((50, 35)).with_duration(duration)

        # Thin accent-coloured underline beneath branding
        underline = ColorClip(
            size=(brand.size[0], 3),
            color=ACCENT_COLOR_RGB,
        )
        underline = underline.with_position((50, 35 + BRAND_FONT_SIZE + 6))
        underline = underline.with_duration(duration)

        return [brand, underline]
    except Exception:
        return []


def _create_dark_overlay(duration: float):
    """Semi-transparent dark overlay so captions pop over any footage."""
    overlay = ColorClip(
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        color=(0, 0, 0),
    )
    overlay = overlay.with_opacity(DARK_OVERLAY_OPACITY)
    overlay = overlay.with_duration(duration)
    return overlay


def _create_title_card(title: str, duration: float = TITLE_CARD_DURATION):
    """Animated intro title card — dark background, big title, accent line."""
    layers = []

    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(10, 10, 10))
    bg = bg.with_duration(duration)
    layers.append(bg)

    # Accent horizontal line
    line = ColorClip(size=(400, 4), color=ACCENT_COLOR_RGB)
    line = line.with_position(("center", VIDEO_HEIGHT // 2 - 60))
    line = line.with_duration(duration)
    layers.append(line)

    # Channel name (small, above the line)
    channel = TextClip(
        text="WEALTH TO THE WISE",
        font_size=28,
        color=ACCENT_COLOR,
        font=FONT,
    )
    channel = channel.with_position(("center", VIDEO_HEIGHT // 2 - 110))
    channel = channel.with_duration(duration)
    layers.append(channel)

    # Episode title (large, below the line)
    wrapped_title = textwrap.fill(title, width=35)
    title_txt = TextClip(
        text=wrapped_title,
        font_size=54,
        color="white",
        font=FONT,
        method="caption",
        size=(VIDEO_WIDTH - 400, None),
        text_align="center",
    )
    title_txt = title_txt.with_position(("center", VIDEO_HEIGHT // 2 - 20))
    title_txt = title_txt.with_duration(duration)
    layers.append(title_txt)

    card = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    card = card.with_duration(duration)

    # Fade in
    try:
        from moviepy.video.fx import CrossFadeIn
        card = card.with_effects([CrossFadeIn(0.6)])
    except Exception:
        pass

    return card


def _create_outro_card(duration: float = OUTRO_CARD_DURATION):
    """Subscribe / CTA outro card."""
    layers = []

    bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(10, 10, 10))
    bg = bg.with_duration(duration)
    layers.append(bg)

    # Big CTA text
    cta = TextClip(
        text="SUBSCRIBE FOR MORE",
        font_size=64,
        color=ACCENT_COLOR,
        font=FONT,
    )
    cta = cta.with_position(("center", VIDEO_HEIGHT // 2 - 80))
    cta = cta.with_duration(duration)
    layers.append(cta)

    # Sub-text
    sub = TextClip(
        text="Like · Comment · Share",
        font_size=34,
        color="white",
        font=FONT_BODY,
    )
    sub = sub.with_position(("center", VIDEO_HEIGHT // 2 + 20))
    sub = sub.with_duration(duration)
    layers.append(sub)

    # Accent line
    line = ColorClip(size=(300, 3), color=ACCENT_COLOR_RGB)
    line = line.with_position(("center", VIDEO_HEIGHT // 2 + 80))
    line = line.with_duration(duration)
    layers.append(line)

    # Channel name
    channel = TextClip(
        text="WEALTH TO THE WISE",
        font_size=24,
        color="#888888",
        font=FONT,
    )
    channel = channel.with_position(("center", VIDEO_HEIGHT // 2 + 110))
    channel = channel.with_duration(duration)
    layers.append(channel)

    card = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    card = card.with_duration(duration)

    try:
        from moviepy.video.fx import CrossFadeIn
        card = card.with_effects([CrossFadeIn(0.6)])
    except Exception:
        pass

    return card


def _create_progress_bar(duration: float):
    """A thin accent-coloured bar that grows left→right across the video bottom."""
    bar_height = 5

    def make_frame(t):
        progress = t / duration if duration > 0 else 0
        bar_width = max(1, int(VIDEO_WIDTH * progress))
        frame = np.zeros((bar_height, VIDEO_WIDTH, 3), dtype=np.uint8)
        frame[:, :bar_width] = ACCENT_COLOR_RGB
        return frame

    from moviepy import VideoClip
    bar = VideoClip(make_frame, duration=duration)
    bar = bar.with_position((0, VIDEO_HEIGHT - bar_height))
    return bar


def build_video(
    audio_path: str,
    title: str,
    script: str,
    *,
    output_path: str | None = None,
    stock_clip_paths: list[str] | None = None,
) -> str:
    """Build a cinematic video from stock footage + voiceover + captions.

    Parameters
    ----------
    audio_path : str
        Path to the voiceover MP3/WAV.
    title : str
        Video title (used to search for relevant stock footage).
    script : str
        The full script text (split into caption sentences).
    output_path : str | None
        Where to save. Defaults to ``output/final_video.mp4``.
    stock_clip_paths : list[str] | None
        Paths to stock footage clips. If None, auto-downloads via Pexels.
    """
    if output_path is None:
        # Build a filename from the title so each video is kept, not overwritten
        slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
        slug = re.sub(r'[\s_]+', '_', slug)[:80]
        output_path = str(OUTPUT_DIR / f"{slug}.mp4")
    

    logger.info("Building cinematic video …")

    # ── Audio ────────────────────────────────────────────────────────
    audio = AudioFileClip(audio_path)
    narration_duration = audio.duration
    logger.info("Audio duration: %.1fs", narration_duration)

    # Total video = title card + narration + outro
    total_duration = TITLE_CARD_DURATION + narration_duration + OUTRO_CARD_DURATION

    # ── Stock footage ────────────────────────────────────────────────
    if stock_clip_paths is None:
        logger.info("Downloading %d stock footage clips …", NUM_STOCK_CLIPS)
        from stock_footage import download_clips_for_topic
        stock_clip_paths = download_clips_for_topic(title, num_clips=NUM_STOCK_CLIPS)

    video_clips = _prepare_stock_clips(stock_clip_paths, narration_duration)
    logger.info("Using %d video segments", len(video_clips))

    # Concatenate all B-roll clips into one continuous background
    if len(video_clips) == 1:
        background = video_clips[0].with_duration(narration_duration)
    else:
        try:
            from moviepy.video.fx import CrossFadeIn
            transition_clips = []
            for i, clip in enumerate(video_clips):
                if i > 0:
                    clip = clip.with_effects([CrossFadeIn(CROSSFADE_DURATION)])
                transition_clips.append(clip)
            background = concatenate_videoclips(
                transition_clips,
                method="compose",
                padding=-CROSSFADE_DURATION,  # type: ignore[arg-type]  — moviepy accepts float
            )
        except Exception:
            background = concatenate_videoclips(video_clips, method="compose")

    # Ensure background fills the full narration duration
    if background.duration < narration_duration:
        background = background.with_duration(narration_duration)

    background = background.without_audio()

    # ── Dark overlay for readability ─────────────────────────────────
    dark_overlay = _create_dark_overlay(narration_duration)

    # ── Caption overlays ─────────────────────────────────────────────
    sentences = _split_script_to_sentences(script)
    logger.info("Creating %d caption segments (with fade-in + background)", len(sentences))
    captions = _create_caption_clips(sentences, narration_duration)

    # ── Branding ─────────────────────────────────────────────────────
    branding_layers = _create_branding_clip(narration_duration)

    # ── Progress bar ─────────────────────────────────────────────────
    progress_bar = _create_progress_bar(narration_duration)
    logger.info("Added progress bar")

    # ── Compose main narration section ───────────────────────────────
    layers = [background, dark_overlay]
    layers.extend(branding_layers)
    layers.extend(captions)
    layers.append(progress_bar)

    main_section = CompositeVideoClip(
        layers,
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
    ).with_audio(audio).with_duration(narration_duration)

    # ── Title card + outro ───────────────────────────────────────────
    logger.info("Adding %.1fs title card + %.1fs outro", TITLE_CARD_DURATION, OUTRO_CARD_DURATION)
    title_card = _create_title_card(title)
    outro_card = _create_outro_card()

    # ── Final assembly: title → main → outro ─────────────────────────
    final = concatenate_videoclips(
        [title_card, main_section, outro_card],
        method="compose",
    )

    logger.info("Rendering %.0fs video @ %d×%d / %d fps …", final.duration, VIDEO_WIDTH, VIDEO_HEIGHT, FPS)
    logger.info("Encoding: preset=%s, bitrate=%s", ENCODING_PRESET, VIDEO_BITRATE)

    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset=ENCODING_PRESET,
        bitrate=VIDEO_BITRATE,
        logger="bar",
    )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("Video saved → %s  (%.1f MB)", output_path, size_mb)

    # Clean up
    audio.close()
    final.close()
    for clip in video_clips:
        try:
            clip.close()
        except Exception:
            pass

    # ── File-size gate: re-encode if too large ───────────────────────
    output_path = _enforce_size_limit(output_path)

    return output_path


def _enforce_size_limit(video_path: str) -> str:
    """Re-encode the video at a lower bitrate if it exceeds the configured
    maximum file size.  Returns the (possibly re-encoded) path."""
    import config as _cfg

    max_mb = _cfg.MAX_VIDEO_SIZE_MB
    size_mb = os.path.getsize(video_path) / (1024 * 1024)

    if size_mb <= max_mb:
        logger.info("File size %.1f MB is within the %d MB limit ✓", size_mb, max_mb)
        return video_path

    logger.info(
        "File size %.1f MB exceeds %d MB limit — re-encoding with lower bitrate …",
        size_mb, max_mb,
    )

    # Calculate target bitrate from file-size budget
    clip = VideoFileClip(video_path)
    duration_s = clip.duration
    clip.close()

    # target bytes  = max_mb * 1024 * 1024 * 0.95  (5 % headroom)
    target_bytes = max_mb * 1024 * 1024 * 0.95
    # total bitrate (video + audio);  audio ≈ 128 kbps
    audio_bps = 128_000
    target_video_bps = max(500_000, int((target_bytes * 8 / duration_s) - audio_bps))
    target_bitrate = f"{target_video_bps // 1000}k"

    compressed_path = video_path.replace(".mp4", "_compressed.mp4")

    logger.info("    Target bitrate: %s  (duration %.0fs)", target_bitrate, duration_s)

    src = VideoFileClip(video_path)
    src.write_videofile(
        compressed_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="slow",  # slower preset = better quality at lower bitrate
        bitrate=target_bitrate,
        logger="bar",
    )
    src.close()

    new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
    logger.info("    Compressed: %.1f MB → %.1f MB", size_mb, new_size_mb)

    # Replace original with compressed version
    os.replace(compressed_path, video_path)
    return video_path


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json as _json

    test_audio = str(OUTPUT_DIR / "voiceover.mp3")
    script_path = OUTPUT_DIR / "latest_script.txt"
    meta_path = OUTPUT_DIR / "latest_metadata.json"

    if os.path.isfile(test_audio) and script_path.exists() and meta_path.exists():
        script_text = script_path.read_text(encoding="utf-8")
        meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        clip_dir = OUTPUT_DIR / "clips"
        clip_paths = sorted(str(p) for p in clip_dir.glob("clip_*.mp4")) if clip_dir.exists() else None
        build_video(
            audio_path=test_audio,
            title=meta.get("title", "Wealth to the Wise"),
            script=script_text,
            stock_clip_paths=clip_paths if clip_paths else None,
        )
    elif os.path.isfile(test_audio):
        build_video(
            audio_path=test_audio,
            title="5 Frugal Habits That Build Wealth Fast",
            script=(
                "Want to build wealth fast? Stop wasting money on things you don't need. "
                "Here are five frugal habits that separate the rich from the broke. "
                "Number one: automate your savings. Pay yourself first. "
                "Number two: cook at home. Restaurants are bleeding you dry. "
                "Number three: cancel subscriptions you don't use. "
                "Number four: buy used when possible. Your ego is not worth the debt. "
                "Number five: invest the difference. Every dollar saved is a soldier working for you."
            ),
        )
    else:
        logger.warning("No voiceover.mp3 found. Run voiceover.py first.")
