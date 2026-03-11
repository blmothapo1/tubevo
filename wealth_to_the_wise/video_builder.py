"""
video_builder.py — Assemble a cinematic video from stock footage + voiceover.

**Memory-optimised for Railway containers (512 MB–1 GB RAM).**

Strategy: use FFmpeg CLI subprocesses for all heavy video processing.
FFmpeg processes frames in a streaming fashion (~50-100 MB RAM) whereas
moviepy loads entire clips as numpy arrays (easily 2-4 GB for 1080p).

Pipeline:
  1. Probe audio duration with ffprobe
  2. Prepare stock clips (trim, scale, concat) via FFmpeg CLI → background.mp4
  3. Render title card and outro card as short clips via FFmpeg drawtext
  4. Generate ASS subtitle file for captions (ffmpeg renders these natively)
  5. Final composite: background + dark overlay + subtitles + branding via FFmpeg CLI
  6. Concatenate: title → main → outro via FFmpeg concat demuxer

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

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visual_effects import VisualProfile

from pipeline_errors import RenderError

logger = logging.getLogger("tubevo.video_builder")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Video settings ───────────────────────────────────────────────────
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
FPS = 24

# ── Styling ──────────────────────────────────────────────────────────
ACCENT_COLOR = "#00D4AA"
CAPTION_FONT_SIZE = 42
BRAND_FONT_SIZE = 24

# Dark overlay opacity (0.0 – 1.0) for text readability
DARK_OVERLAY_OPACITY = 0.35

# Title card / outro durations
TITLE_CARD_DURATION = 3.5
OUTRO_CARD_DURATION = 4.0

# Number of stock clips to download (legacy mode — scene planner may override)
NUM_STOCK_CLIPS = 10

# Encoding — tuned for Railway's 512 MB–1 GB RAM containers.
# "ultrafast" uses dramatically less memory than "fast" because it skips
# expensive motion-estimation reference frames that balloon RAM.
# CRF 20 produces quality comparable to 4000k CBR at 720p.
ENCODING_PRESET = "ultrafast"
ENCODING_CRF = "20"            # constant-quality (lower = better, 18-23 is good)
VIDEO_BITRATE = "3500k"        # only used as fallback / maxrate cap
AUDIO_BITRATE = "128k"
# Limit FFmpeg thread pool so it doesn't spawn as many threads as CPU
# cores (Railway shares vCPUs).  1 thread minimises peak RSS for 512 MB.
FFMPEG_THREADS = "1"

# Cross-platform font detection
# Phase 5: last generated SRT path (set by _build_video_inner, read by pipeline)
last_srt_path: str | None = None

def _find_font(bold: bool = True) -> str:
    """Return the best available font path for FFmpeg drawtext."""
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return "Liberation-Sans-Bold" if bold else "Liberation-Sans"

FONT = _find_font(bold=True)
FONT_BODY = _find_font(bold=False)

# Font name for ASS subtitles (just the family name)
def _font_family() -> str:
    if "Liberation" in FONT:
        return "Liberation Sans"
    if "DejaVu" in FONT:
        return "DejaVu Sans"
    return "Arial"

FONT_FAMILY = _font_family()


# ── Helpers ──────────────────────────────────────────────────────────

def _run_ffmpeg(args: list[str], description: str = "ffmpeg") -> None:
    """Run an FFmpeg command, raise on failure."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
           "-nostdin",
           "-threads", FFMPEG_THREADS] + args
    logger.info("Running %s …", description)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.error("%s stderr: %s", description, result.stderr[-2000:] if result.stderr else "(none)")
        raise RenderError(f"{description} failed (exit {result.returncode}): {result.stderr[-500:]}")


def _run_ffprobe(path: str) -> dict:
    """Probe a media file and return the JSON output."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RenderError(f"ffprobe failed for {path}")
    return json.loads(result.stdout)


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    info = _run_ffprobe(audio_path)
    return float(info["format"]["duration"])


def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    info = _run_ffprobe(video_path)
    return float(info["format"]["duration"])


def _split_script_to_sentences(script: str) -> list[str]:
    """Split a script into individual sentences for caption display."""
    raw = re.split(r'(?<=[.!?])\s+', script.strip())
    sentences = [s.strip() for s in raw if s.strip()]

    final: list[str] = []
    for sent in sentences:
        if len(sent) > 100:
            parts = re.split(r'(?<=,)\s+|(?<=:)\s+|(?<=—)\s*|(?<=-)\s+', sent)
            parts = [p.strip() for p in parts if p.strip()]
            final.extend(parts)
        else:
            final.append(sent)
    return final


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    # FFmpeg drawtext needs these characters escaped
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\''")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


# ── FFmpeg filter detection ──────────────────────────────────────────
_ffmpeg_filter_cache: dict[str, bool] = {}


def _has_ffmpeg_filter(name: str) -> bool:
    """Check if an FFmpeg filter is available (cached)."""
    if name in _ffmpeg_filter_cache:
        return _ffmpeg_filter_cache[name]
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=10,
        )
        available = f" {name} " in result.stdout or f" {name}\n" in result.stdout
        _ffmpeg_filter_cache[name] = available
        return available
    except Exception:
        _ffmpeg_filter_cache[name] = False
        return False


# ── Cross-dissolve concat via xfade ─────────────────────────────────

def _concat_with_xfade(
    segment_files: list[str],
    output_path: str,
    xfade_duration: float,
    target_duration: float,
    tmp_dir: str,
    *,
    allowed_transitions: list[str] | None = None,
) -> str:
    """Concatenate segments with varied transitions via xfade filter.

    Uses a chain of xfade filters: each pair of consecutive clips gets
    a randomly chosen transition type (dissolve, fade-to-black, slide,
    wipe, etc.) for visual variety.

    Memory-safe because FFmpeg processes frames sequentially.
    Falls back to hard concat if xfade isn't available or if the chain
    is too long (>8 segments = too many inputs for a single filterchain).
    """
    if not _has_ffmpeg_filter("xfade") or len(segment_files) < 2:
        # Fallback: hard concat
        concat_list = os.path.join(tmp_dir, "concat_bg_fallback.txt")
        with open(concat_list, "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-t", f"{target_duration:.2f}",
            output_path,
        ], "concat background (xfade fallback)")
        return output_path

    # Build xfade filter chain.
    # For N segments, we need N-1 xfade operations.
    # Each xfade shortens total duration by xfade_duration.
    # xfade syntax: [v0][v1]xfade=transition=TYPE:duration=D:offset=O[vout]
    n = len(segment_files)
    xd = min(xfade_duration, 1.0)  # Cap dissolve at 1s for safety

    # Get durations of each segment
    seg_durs: list[float] = []
    for sf in segment_files:
        try:
            seg_durs.append(_get_video_duration(sf))
        except Exception:
            seg_durs.append(3.0)  # Fallback estimate

    # Build input args
    input_args: list[str] = []
    for sf in segment_files:
        input_args.extend(["-i", sf])

    # Build filter chain with varied transition types
    filter_parts: list[str] = []
    # Track cumulative offset (each xfade happens at the end of the accumulated output)
    cumulative_dur = seg_durs[0]

    # Import transition picker for variety
    try:
        from visual_effects import pick_transition_type as _pick_tr
    except ImportError:
        _pick_tr = None  # type: ignore[assignment]

    transition_types_used: list[str] = []

    for i in range(n - 1):
        if i == 0:
            in_a = "[0:v]"
        else:
            in_a = f"[vfade{i}]"

        in_b = f"[{i + 1}:v]"
        offset = max(0.1, cumulative_dur - xd)

        if i < n - 2:
            out_label = f"[vfade{i + 1}]"
        else:
            out_label = "[vout]"

        # Pick a varied transition type
        if _pick_tr is not None:
            tr_type = _pick_tr(
                i, seed=str(target_duration),
                allowed=allowed_transitions,
            )
        else:
            tr_type = "fade"

        transition_types_used.append(tr_type)

        filter_parts.append(
            f"{in_a}{in_b}xfade=transition={tr_type}:duration={xd:.2f}:offset={offset:.2f}{out_label}"
        )
        # Next segment's cumulative duration: previous output + next seg - overlap
        cumulative_dur = offset + xd + (seg_durs[i + 1] if i + 1 < n else 0) - xd
        # Simplified: cumulative = offset + seg_durs[i+1]
        if i + 1 < n:
            cumulative_dur = offset + seg_durs[i + 1]

    filter_chain = ";".join(filter_parts)

    try:
        _run_ffmpeg(
            input_args + [
                "-filter_complex", filter_chain,
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-t", f"{target_duration:.2f}",
                output_path,
            ],
            "concat with varied transitions",
        )
        logger.info(
            "Varied transitions: %d segments, %.1fs duration, types=%s",
            n, xd, transition_types_used,
        )
    except Exception as xf_err:
        # Fallback to hard concat if xfade fails
        logger.warning("xfade concat failed — falling back to hard concat: %s", xf_err)
        concat_list = os.path.join(tmp_dir, "concat_bg_fallback.txt")
        with open(concat_list, "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-t", f"{target_duration:.2f}",
            output_path,
        ], "concat background (xfade failed, hard concat)")

    return output_path


# ── Step 1: Prepare stock footage background ────────────────────────

def _prepare_background(
    clip_paths: list[str],
    target_duration: float,
    tmp_dir: str,
    *,
    visual_profile: VisualProfile | None = None,
) -> str:
    """Scale, trim, and concatenate stock clips into a single background.mp4.

    Uses FFmpeg concat demuxer — processes clips one at a time, never loads
    them all into RAM simultaneously.

    If *visual_profile* is provided and has Ken Burns enabled, each clip
    segment gets a slow zoom/pan effect for cinematic motion.
    """
    output_path = os.path.join(tmp_dir, "background.mp4")

    if not clip_paths:
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"color=c=0x0F0F0F:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={target_duration}:r={FPS}",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-t", str(target_duration),
            output_path,
        ], "generate blank background")
        return output_path

    # Probe each clip's duration
    valid_clips: list[tuple[str, float]] = []
    for path in clip_paths:
        try:
            dur = _get_video_duration(path)
            if dur > 0.5:
                valid_clips.append((path, dur))
        except Exception as e:
            logger.warning("Could not probe clip %s: %s", path, e)

    if not valid_clips:
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"color=c=0x0F0F0F:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={target_duration}:r={FPS}",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-t", str(target_duration),
            output_path,
        ], "generate blank background (no valid clips)")
        return output_path

    total_raw_dur = sum(d for _, d in valid_clips)

    # Figure out how long to use from each clip
    segments: list[tuple[str, float]] = []
    remaining = target_duration

    if total_raw_dur >= target_duration:
        for path, dur in valid_clips:
            if remaining <= 0:
                break
            share = max(2.0, (dur / total_raw_dur) * target_duration)
            share = min(share, remaining, dur)
            segments.append((path, share))
            remaining -= share
    else:
        idx = 0
        while remaining > 0.5:
            path, dur = valid_clips[idx % len(valid_clips)]
            use_dur = min(dur, remaining)
            if use_dur < 1.0:
                break
            segments.append((path, use_dur))
            remaining -= use_dur
            idx += 1

    # Scale and trim each segment, then concat
    # Motion variety: pick a style per segment (Ken Burns, static, slow zoom, drift)
    _motion_enabled = (
        visual_profile is not None
        and visual_profile.ken_burns.enabled
    )
    segment_files: list[str] = []
    for i, (path, use_dur) in enumerate(segments):
        seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp4")

        # Build the video filter chain for this segment
        vf_parts: list[str] = [
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
            f"fps={FPS}",
            "format=yuv420p",
        ]

        if _motion_enabled:
            try:
                from visual_effects import pick_motion_style, get_motion_filter
                assert visual_profile is not None  # type guard
                style = pick_motion_style(i, seed=str(target_duration))
                motion_filter = get_motion_filter(
                    style, i, VIDEO_WIDTH, VIDEO_HEIGHT, FPS, use_dur,
                    ken_burns_config=visual_profile.ken_burns,
                    seed=str(target_duration),
                )
                if motion_filter:
                    # zoompan-based filters must come after scale+pad
                    vf_parts = [
                        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
                        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
                        "format=yuv420p",
                        motion_filter,
                    ]
                    logger.debug("Motion segment %d: %s", i, style.value)
                else:
                    logger.debug("Static segment %d (no motion filter)", i)
            except Exception as motion_err:
                logger.warning("Motion style failed for segment %d — skipping: %s", i, motion_err)

        _run_ffmpeg([
            "-i", path,
            "-t", f"{use_dur:.2f}",
            "-vf", ",".join(vf_parts),
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            seg_path,
        ], f"scale/trim segment {i}")
        segment_files.append(seg_path)

    if len(segment_files) == 1:
        shutil.move(segment_files[0], output_path)
        return output_path

    # ── Cross-dissolve transitions (Starter+ tiers) ─────────────────
    # xfade filter creates smooth dissolves between clips.
    # For free tier or >8 segments (memory guard), fall back to hard concat.
    _use_xfade = (
        visual_profile is not None
        and visual_profile.transitions.enabled
        and len(segment_files) <= 8
    )

    if _use_xfade and visual_profile is not None:
        xfade_dur = visual_profile.transitions.dissolve_duration
        output_path = _concat_with_xfade(
            segment_files, output_path, xfade_dur, target_duration, tmp_dir,
            allowed_transitions=visual_profile.transitions.transition_types,
        )
    else:
        # Write concat list (hard cuts — free tier)
        concat_list = os.path.join(tmp_dir, "concat_bg.txt")
        with open(concat_list, "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")

        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-t", f"{target_duration:.2f}",
            output_path,
        ], "concat background segments")

    # Clean up segment files
    for seg in segment_files:
        try:
            os.remove(seg)
        except OSError:
            pass

    return output_path


# ── Step 1b: Scene-aware background (NEW) ────────────────────────────

def _prepare_background_from_scenes(
    scene_clip_data: list[dict],
    narration_duration: float,
    tmp_dir: str,
    *,
    visual_profile: VisualProfile | None = None,
) -> str:
    """Build background.mp4 by stitching scene-specific clips in order.

    Each entry in *scene_clip_data* is:
        {"label": "intro", "clips": ["clip_0.mp4", ...], "duration": 12.5}

    Clips within each scene are distributed across that scene's duration.
    This ensures visual variety that matches the narration structure.

    Falls back to ``_prepare_background`` if scene data is empty.
    """
    all_clips = []
    for sd in scene_clip_data:
        all_clips.extend(sd.get("clips", []))

    if not all_clips:
        logger.warning("No scene clips — falling back to blank background")
        return _prepare_background([], narration_duration, tmp_dir, visual_profile=visual_profile)

    output_path = os.path.join(tmp_dir, "background.mp4")

    # Compute per-scene time budgets proportional to declared duration
    total_declared = sum(sd.get("duration", 0) for sd in scene_clip_data)
    if total_declared <= 0:
        # Equal distribution if no durations provided
        total_declared = narration_duration
        per_scene_frac = 1.0 / max(1, len(scene_clip_data))
    else:
        per_scene_frac = None  # will compute per-scene

    segment_files: list[str] = []
    seg_idx = 0
    remaining_total = narration_duration

    for sd in scene_clip_data:
        clips = sd.get("clips", [])
        if not clips:
            continue

        if per_scene_frac is not None:
            scene_budget = narration_duration * per_scene_frac
        else:
            scene_budget = (sd["duration"] / total_declared) * narration_duration

        # Don't exceed remaining time
        scene_budget = min(scene_budget, remaining_total)
        if scene_budget < 0.5:
            continue

        # Probe clip durations
        valid: list[tuple[str, float]] = []
        for cp in clips:
            try:
                dur = _get_video_duration(cp)
                if dur > 0.5:
                    valid.append((cp, dur))
            except Exception as e:
                logger.warning("Could not probe clip %s: %s", cp, e)

        if not valid:
            continue

        # Distribute scene_budget across the scene's clips
        total_clip_dur = sum(d for _, d in valid)
        scene_remaining = scene_budget

        # Motion variety enabled?
        _motion_on = (
            visual_profile is not None
            and visual_profile.ken_burns.enabled
        )

        if total_clip_dur >= scene_budget:
            for path, dur in valid:
                if scene_remaining <= 0:
                    break
                share = max(1.5, (dur / total_clip_dur) * scene_budget)
                share = min(share, scene_remaining, dur)
                seg_path = os.path.join(tmp_dir, f"seg_{seg_idx:03d}.mp4")

                vf_parts = [
                    f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
                    f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
                    f"fps={FPS}",
                    "format=yuv420p",
                ]
                if _motion_on:
                    try:
                        from visual_effects import pick_motion_style, get_motion_filter
                        assert visual_profile is not None  # type guard
                        style = pick_motion_style(seg_idx, seed=sd.get("label", ""))
                        m_f = get_motion_filter(
                            style, seg_idx, VIDEO_WIDTH, VIDEO_HEIGHT, FPS, share,
                            ken_burns_config=visual_profile.ken_burns,
                            seed=sd.get("label", ""),
                        )
                        if m_f:
                            vf_parts = [
                                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
                                f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
                                "format=yuv420p",
                                m_f,
                            ]
                    except Exception:
                        pass

                _run_ffmpeg([
                    "-i", path,
                    "-t", f"{share:.2f}",
                    "-vf", ",".join(vf_parts),
                    "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    seg_path,
                ], f"scale/trim scene segment {seg_idx}")
                segment_files.append(seg_path)
                scene_remaining -= share
                seg_idx += 1
        else:
            # Loop clips to fill the scene budget
            clip_idx = 0
            while scene_remaining > 0.5 and valid:
                path, dur = valid[clip_idx % len(valid)]
                use_dur = min(dur, scene_remaining)
                if use_dur < 1.0:
                    break
                seg_path = os.path.join(tmp_dir, f"seg_{seg_idx:03d}.mp4")

                vf_parts = [
                    f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
                    f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
                    f"fps={FPS}",
                    "format=yuv420p",
                ]
                if _motion_on:
                    try:
                        from visual_effects import pick_motion_style, get_motion_filter
                        assert visual_profile is not None  # type guard
                        style = pick_motion_style(seg_idx, seed=sd.get("label", ""))
                        m_f = get_motion_filter(
                            style, seg_idx, VIDEO_WIDTH, VIDEO_HEIGHT, FPS, use_dur,
                            ken_burns_config=visual_profile.ken_burns,
                            seed=sd.get("label", ""),
                        )
                        if m_f:
                            vf_parts = [
                                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
                                f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black",
                                "format=yuv420p",
                                m_f,
                            ]
                    except Exception:
                        pass

                _run_ffmpeg([
                    "-i", path,
                    "-t", f"{use_dur:.2f}",
                    "-vf", ",".join(vf_parts),
                    "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    seg_path,
                ], f"scale/trim scene segment {seg_idx}")
                segment_files.append(seg_path)
                scene_remaining -= use_dur
                seg_idx += 1
                clip_idx += 1

        remaining_total -= (scene_budget - scene_remaining)

    if not segment_files:
        return _prepare_background(all_clips, narration_duration, tmp_dir, visual_profile=visual_profile)

    if len(segment_files) == 1:
        shutil.move(segment_files[0], output_path)
        return output_path

    # ── Cross-dissolve transitions (Starter+ tiers) ─────────────────
    _use_xfade = (
        visual_profile is not None
        and visual_profile.transitions.enabled
        and len(segment_files) <= 8
    )

    if _use_xfade and visual_profile is not None:
        xfade_dur = visual_profile.transitions.dissolve_duration
        output_path = _concat_with_xfade(
            segment_files, output_path, xfade_dur, narration_duration, tmp_dir,
            allowed_transitions=visual_profile.transitions.transition_types,
        )
    else:
        # Concat all scene segments (hard cuts)
        concat_list = os.path.join(tmp_dir, "concat_bg.txt")
        with open(concat_list, "w") as f:
            for seg in segment_files:
                f.write(f"file '{seg}'\n")

        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-t", f"{narration_duration:.2f}",
            output_path,
        ], "concat scene-aware background segments")

    # Clean up segment files
    for seg in segment_files:
        try:
            os.remove(seg)
        except OSError:
            pass

    logger.info("Scene-aware background: %d segments, %.1fs", len(segment_files), narration_duration)
    return output_path


# ── Step 2: Generate ASS subtitle file ──────────────────────────────

def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format: H:MM:SS.CC"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _generate_ass_subtitles(
    sentences: list[str],
    total_duration: float,
    output_path: str,
) -> str:
    """Generate an ASS subtitle file with styled captions.

    ASS subtitles are rendered by FFmpeg natively (via libass) with zero
    extra RAM — the filter reads the .ass file and burns text frame by frame.
    """
    word_counts = [max(len(s.split()), 1) for s in sentences]
    total_words = sum(word_counts)

    ass_content = f"""[Script Info]
Title: Tubevo Captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_FAMILY},{CAPTION_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,2,0,2,40,40,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    current_time = 0.0
    for i, sentence in enumerate(sentences):
        duration = (word_counts[i] / total_words) * total_duration
        start = current_time
        end = current_time + duration

        wrapped = textwrap.fill(sentence, width=50).replace("\n", "\\N")
        effect = r"{\fad(300,200)}"

        ass_content += (
            f"Dialogue: 0,{_seconds_to_ass_time(start)},{_seconds_to_ass_time(end)},"
            f"Default,,0,0,0,,{effect}{wrapped}\n"
        )
        current_time += duration

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    return output_path


# ── Step 3: Title card via FFmpeg ────────────────────────────────────

def _create_title_card(
    title: str,
    tmp_dir: str,
    duration: float = TITLE_CARD_DURATION,
    *,
    visual_profile: VisualProfile | None = None,
) -> str:
    """Render a title card as a short video clip using FFmpeg drawtext.

    If *visual_profile* is provided, uses animated text reveals,
    accent lines, shimmer effects, and subtitle text based on tier.
    """
    output_path = os.path.join(tmp_dir, "title_card.mp4")

    # Write title to a temp file so drawtext can handle multi-line text
    title_text_file = os.path.join(tmp_dir, "title_text.txt")
    wrapped_title = textwrap.fill(title, width=35)
    with open(title_text_file, "w", encoding="utf-8") as f:
        f.write(wrapped_title)

    # Premium title card filter
    if visual_profile is not None:
        try:
            from visual_effects import build_title_card_filter
            vf = build_title_card_filter(
                visual_profile, title, title_text_file, FONT,
                VIDEO_WIDTH, VIDEO_HEIGHT, duration,
            )
            _run_ffmpeg([
                "-f", "lavfi",
                "-i", f"color=c=0x0A0A0A:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r={FPS}",
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                output_path,
            ], "render premium title card")
            return output_path
        except Exception as tc_err:
            logger.warning("Premium title card failed — using baseline: %s", tc_err)

    # Baseline title card (free tier / fallback)
    font_escaped = FONT.replace("\\", "/").replace(":", "\\:")
    title_file_escaped = title_text_file.replace("\\", "/").replace(":", "\\:")

    _run_ffmpeg([
        "-f", "lavfi",
        "-i", f"color=c=0x0A0A0A:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r={FPS}",
        "-vf", (
            f"format=yuv420p,"
            f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize=24:"
            f"fontcolor=0x00D4AA:x=(w-text_w)/2:y=(h/2)-90,"
            f"drawtext=fontfile='{font_escaped}':textfile='{title_file_escaped}':fontsize=40:"
            f"fontcolor=white:x=(w-text_w)/2:y=(h/2)+10:line_spacing=8"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        output_path,
    ], "render title card")

    return output_path


# ── Step 4: Outro card via FFmpeg ────────────────────────────────────

def _create_outro_card(
    tmp_dir: str,
    duration: float = OUTRO_CARD_DURATION,
    *,
    visual_profile: VisualProfile | None = None,
) -> str:
    """Render the subscribe/CTA outro card.

    If *visual_profile* is provided, uses animated text, accent lines,
    and fade in/out effects based on tier.
    """
    output_path = os.path.join(tmp_dir, "outro_card.mp4")

    # Premium outro card filter
    if visual_profile is not None:
        try:
            from visual_effects import build_outro_card_filter
            vf = build_outro_card_filter(
                visual_profile, FONT,
                VIDEO_WIDTH, VIDEO_HEIGHT, duration,
            )
            _run_ffmpeg([
                "-f", "lavfi",
                "-i", f"color=c=0x0A0A0A:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r={FPS}",
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                output_path,
            ], "render premium outro card")
            return output_path
        except Exception as oc_err:
            logger.warning("Premium outro card failed — using baseline: %s", oc_err)

    # Baseline outro card (free tier / fallback)
    font_escaped = FONT.replace("\\", "/").replace(":", "\\:")

    _run_ffmpeg([
        "-f", "lavfi",
        "-i", f"color=c=0x0A0A0A:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r={FPS}",
        "-vf", (
            f"format=yuv420p,"
            f"drawtext=fontfile='{font_escaped}':text='SUBSCRIBE FOR MORE':fontsize=48:"
            f"fontcolor=0x00D4AA:x=(w-text_w)/2:y=(h/2)-60,"
            f"drawtext=fontfile='{font_escaped}':text='Like · Comment · Share':fontsize=28:"
            f"fontcolor=white:x=(w-text_w)/2:y=(h/2)+20,"
            f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize=20:"
            f"fontcolor=0x888888:x=(w-text_w)/2:y=(h/2)+80"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        output_path,
    ], "render outro card")

    return output_path


# ── Step 5: Composite main section ──────────────────────────────────

def _composite_main_section(
    background_path: str,
    audio_path: str,
    ass_path: str,
    narration_duration: float,
    tmp_dir: str,
    *,
    watermark: bool = False,
    visual_profile: VisualProfile | None = None,
    topic_label: str | None = None,
) -> str:
    """Compose background + dark overlay + subtitles + branding + progress bar.

    All done in a single FFmpeg filtergraph pass — constant memory usage.

    If *visual_profile* is provided, uses the premium visual effects engine
    for color grading, vignette, grain, letterboxing, animated lower-third, etc.
    """
    output_path = os.path.join(tmp_dir, "main_section.mp4")

    # Build filter chain — premium or baseline
    if visual_profile is not None:
        try:
            from visual_effects import build_composite_filter
            vf = build_composite_filter(
                visual_profile,
                narration_duration,
                ass_path,
                FONT,
                VIDEO_WIDTH,
                VIDEO_HEIGHT,
                watermark=watermark,
                topic_label=topic_label,
            )
            logger.info("Using premium composite filter (%s tier)", visual_profile.tier.value)
        except Exception as vf_err:
            logger.warning("Premium composite filter failed — using baseline: %s", vf_err)
            vf = _baseline_composite_filter(ass_path, narration_duration, watermark)
    else:
        vf = _baseline_composite_filter(ass_path, narration_duration, watermark)

    _run_ffmpeg([
        "-i", background_path,
        "-i", audio_path,
        "-vf", vf,
        "-t", f"{narration_duration:.2f}",
        "-c:v", "libx264", "-preset", ENCODING_PRESET,
        "-crf", ENCODING_CRF, "-maxrate", VIDEO_BITRATE, "-bufsize", "2000k",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ac", "2", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-max_muxing_queue_size", "512",
        "-shortest",
        output_path,
    ], "composite main section")

    return output_path


def _baseline_composite_filter(
    ass_path: str,
    narration_duration: float,
    watermark: bool,
) -> str:
    """Original baseline composite filter (free tier / fallback)."""
    font_escaped = FONT.replace("\\", "/").replace(":", "\\:")
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    bar_h = 4
    darken = 1.0 - DARK_OVERLAY_OPACITY

    vf = (
        f"colorchannelmixer=rr={darken}:gg={darken}:bb={darken},"
        f"ass='{ass_escaped}',"
        f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize={BRAND_FONT_SIZE}:"
        f"fontcolor=0x00D4AA:x=40:y=28,"
        f"drawbox=x=0:y=ih-{bar_h}:w='floor(iw*(t/{narration_duration:.2f}))':h={bar_h}:"
        f"color=0x00D4AA:t=fill"
    )

    if watermark:
        vf += (
            f",drawtext=fontfile='{font_escaped}':"
            f"text='Made with Tubevo':fontsize=20:"
            f"fontcolor=white@0.35:x=w-tw-20:y=h-th-20"
        )

    return vf


# ── Step 6: Final assembly ──────────────────────────────────────────

def _assemble_final(
    title_card_path: str,
    main_section_path: str,
    outro_card_path: str,
    output_path: str,
    tmp_dir: str,
) -> str:
    """Concatenate title → main → outro using FFmpeg concat demuxer."""
    # Add silent audio to title and outro so concat works with the main section
    title_with_audio = os.path.join(tmp_dir, "title_with_audio.mp4")
    outro_with_audio = os.path.join(tmp_dir, "outro_with_audio.mp4")

    title_dur = _get_video_duration(title_card_path)
    _run_ffmpeg([
        "-i", title_card_path,
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={title_dur}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-shortest",
        title_with_audio,
    ], "add silent audio to title card")

    outro_dur = _get_video_duration(outro_card_path)
    _run_ffmpeg([
        "-i", outro_card_path,
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={outro_dur}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-shortest",
        outro_with_audio,
    ], "add silent audio to outro card")

    concat_list = os.path.join(tmp_dir, "concat_final.txt")
    with open(concat_list, "w") as f:
        f.write(f"file '{title_with_audio}'\n")
        f.write(f"file '{main_section_path}'\n")
        f.write(f"file '{outro_with_audio}'\n")

    # Re-encode rather than stream-copy to avoid glitch artefacts at
    # concat segment boundaries (different encoder settings, frame padding).
    _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c:v", "libx264", "-preset", ENCODING_PRESET,
        "-crf", ENCODING_CRF, "-maxrate", VIDEO_BITRATE, "-bufsize", "2000k",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ac", "2", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-max_muxing_queue_size", "512",
        "-movflags", "+faststart",
        output_path,
    ], "assemble final video")

    return output_path


# ── File-size enforcement ────────────────────────────────────────────

def _enforce_size_limit(video_path: str) -> str:
    """Re-encode at a lower bitrate if the file is too large.

    Uses FFmpeg CLI (not moviepy) — constant memory usage.
    """
    import config as _cfg

    max_mb = _cfg.MAX_VIDEO_SIZE_MB
    size_mb = os.path.getsize(video_path) / (1024 * 1024)

    if size_mb <= max_mb:
        logger.info("File size %.1f MB within %d MB limit ✓", size_mb, max_mb)
        return video_path

    logger.info("File size %.1f MB exceeds %d MB — re-encoding …", size_mb, max_mb)

    duration = _get_video_duration(video_path)
    target_bytes = max_mb * 1024 * 1024 * 0.95
    audio_bps = 128_000
    target_video_bps = max(500_000, int((target_bytes * 8 / duration) - audio_bps))
    target_bitrate = f"{target_video_bps // 1000}k"

    compressed_path = video_path.replace(".mp4", "_compressed.mp4")

    _run_ffmpeg([
        "-i", video_path,
        "-c:v", "libx264", "-preset", ENCODING_PRESET, "-b:v", target_bitrate,
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ac", "2", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        compressed_path,
    ], "compress oversized video")

    new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
    logger.info("Compressed: %.1f MB → %.1f MB", size_mb, new_size_mb)

    os.replace(compressed_path, video_path)
    return video_path


# ── Output video validation ──────────────────────────────────────────

def _validate_output_video(
    video_path: str,
    expected_width: int | None = None,
    expected_height: int | None = None,
    min_duration: float = 5.0,
) -> None:
    """Sanity-check the final rendered video.

    Raises ``RenderError`` if the output file is missing, empty,
    unreadable by ffprobe, too short, or has the wrong resolution.
    """
    # ── Existence / size ──
    if not os.path.isfile(video_path):
        raise RenderError(f"Output video not found: {video_path}")
    file_size = os.path.getsize(video_path)
    if file_size == 0:
        raise RenderError(f"Output video is 0 bytes: {video_path}")

    # ── Probe with ffprobe ──
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,codec_name",
        "-show_entries", "format=duration",
        "-of", "json",
        video_path,
    ]
    try:
        probe = subprocess.run(
            probe_cmd, capture_output=True, text=True, timeout=30,
        )
        info = json.loads(probe.stdout)
    except Exception as exc:
        raise RenderError(f"ffprobe failed on {video_path}: {exc}") from exc

    # ── Duration ──
    streams = info.get("streams", [{}])
    fmt = info.get("format", {})
    duration_str = (
        streams[0].get("duration")
        if streams and streams[0].get("duration")
        else fmt.get("duration")
    )
    if duration_str is not None:
        duration = float(duration_str)
        if duration < min_duration:
            raise RenderError(
                f"Output video too short: {duration:.1f}s (min {min_duration:.1f}s)"
            )
        logger.info("Validation: duration %.1fs ✓", duration)
    else:
        logger.warning("Validation: could not determine video duration — skipping check")

    # ── Resolution ──
    if streams and expected_width and expected_height:
        actual_w = streams[0].get("width")
        actual_h = streams[0].get("height")
        if actual_w and actual_h:
            if int(actual_w) != expected_width or int(actual_h) != expected_height:
                logger.warning(
                    "Validation: resolution mismatch — expected %dx%d, got %sx%s",
                    expected_width, expected_height, actual_w, actual_h,
                )
            else:
                logger.info("Validation: resolution %dx%d ✓", expected_width, expected_height)

    # ── Codec sanity ──
    if streams:
        codec = streams[0].get("codec_name", "unknown")
        logger.info("Validation: video codec %s, file size %.1f MB ✓",
                     codec, file_size / (1024 * 1024))


# ── Main entry point ────────────────────────────────────────────────

def build_video(
    audio_path: str,
    title: str,
    script: str,
    *,
    output_path: str | None = None,
    stock_clip_paths: list[str] | None = None,
    scene_clip_data: list[dict] | None = None,
    subtitle_style: str | None = None,
    burn_captions: bool = True,
    video_width: int | None = None,
    video_height: int | None = None,
    video_fps: int | None = None,
    video_crf: str | None = None,
    video_bitrate: str | None = None,
    audio_bitrate: str | None = None,
    watermark: bool = False,
    openai_api_key: str | None = None,
    visual_tier: str | None = None,
    topic_label: str | None = None,
) -> str:
    """Build a cinematic video from stock footage + voiceover + captions.

    **Memory-efficient**: all heavy lifting is done by FFmpeg subprocesses.
    Peak RAM usage is ~100-200 MB regardless of video length.

    Parameters
    ----------
    audio_path : str
        Path to the voiceover MP3/WAV.
    title : str
        Video title (used to search for relevant stock footage).
    script : str
        The full script text (split into caption sentences).
    output_path : str | None
        Where to save. Defaults to ``output/<slug>.mp4``.
    stock_clip_paths : list[str] | None
        Paths to stock footage clips (legacy flat list). If None,
        auto-downloads via Pexels unless *scene_clip_data* is provided.
    scene_clip_data : list[dict] | None
        Scene-aware clip data from ``stock_footage.download_clips_for_scenes()``.
        Each dict has keys: label, clips, duration.
        If provided, takes precedence over *stock_clip_paths*.
    subtitle_style : str | None
        Phase 5 subtitle style preset name (e.g. "bold_pop", "minimal").
        None = use default ("bold_pop"). Falls back to legacy if import fails.
    burn_captions : bool
        Whether to burn captions into the video (default True).
    video_width / video_height / video_fps / video_crf / video_bitrate / audio_bitrate
        Plan-based quality overrides.  When *None*, module-level defaults are used.
    watermark : bool
        If True, burn a "Made with Tubevo" watermark (free tier).
    openai_api_key : str | None
        OpenAI key for Whisper-based subtitle alignment.
    visual_tier : str | None
        Plan tier for premium visual effects ("free", "starter", "pro", "agency").
        None defaults to "free" (baseline visuals).
    topic_label : str | None
        Short topic label for lower-third overlay (Pro/Agency tiers).
    """
    # Resolve quality overrides (fall back to module-level constants)
    _w = video_width or VIDEO_WIDTH
    _h = video_height or VIDEO_HEIGHT
    _fps = video_fps or FPS
    _crf = video_crf or ENCODING_CRF
    _vbr = video_bitrate or VIDEO_BITRATE
    _abr = audio_bitrate or AUDIO_BITRATE

    # ── Railway memory guard: cap at 720p to prevent OOM kills ───────
    # Railway containers typically have 512 MB–1 GB RAM.  Encoding
    # 1080p video with subtitle rendering + filters exceeds 512 MB.
    # Detect production via ENV var (set by Railway service config)
    # or RAILWAY_ENVIRONMENT (auto-set by Railway).
    _env = (os.environ.get("ENV", "") or os.environ.get("RAILWAY_ENVIRONMENT", "")).lower()
    _is_production = _env == "production" or bool(os.environ.get("RAILWAY_PROJECT_ID"))
    _max_res = int(os.environ.get("TUBEVO_MAX_VIDEO_HEIGHT", "720" if _is_production else "1080"))
    if _h > _max_res:
        _scale = _max_res / _h
        _w = int(_w * _scale) & ~1  # ensure even number
        _h = _max_res
        logger.info("Resolution capped to %dx%d (production memory limit)", _w, _h)

    if output_path is None:
        slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
        slug = re.sub(r'[\s_]+', '_', slug)[:80]
        output_path = str(OUTPUT_DIR / f"{slug}.mp4")

    logger.info("Building video (FFmpeg-native, %dx%d @ %d fps, crf=%s) …", _w, _h, _fps, _crf)

    tmp_dir = tempfile.mkdtemp(prefix="tubevo_build_")
    logger.info("Working directory: %s", tmp_dir)

    try:
        return _build_video_inner(
            audio_path=audio_path,
            title=title,
            script=script,
            output_path=output_path,
            stock_clip_paths=stock_clip_paths,
            scene_clip_data=scene_clip_data,
            subtitle_style=subtitle_style,
            burn_captions=burn_captions,
            tmp_dir=tmp_dir,
            video_width=_w,
            video_height=_h,
            video_fps=_fps,
            video_crf=_crf,
            video_bitrate=_vbr,
            audio_bitrate=_abr,
            watermark=watermark,
            openai_api_key=openai_api_key,
            visual_tier=visual_tier,
            topic_label=topic_label,
        )
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.info("Cleaned up temp directory")
        except Exception:
            pass


def _build_video_inner(
    *,
    audio_path: str,
    title: str,
    script: str,
    output_path: str,
    stock_clip_paths: list[str] | None,
    scene_clip_data: list[dict] | None,
    subtitle_style: str | None,
    burn_captions: bool,
    tmp_dir: str,
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    video_fps: int = FPS,
    video_crf: str = ENCODING_CRF,
    video_bitrate: str = VIDEO_BITRATE,
    audio_bitrate: str = AUDIO_BITRATE,
    watermark: bool = False,
    openai_api_key: str | None = None,
    visual_tier: str | None = None,
    topic_label: str | None = None,
) -> str:
    """Inner build function — all work happens here."""

    # Override module-level constants so helper functions pick up
    # plan-based quality settings without refactoring every signature.
    global VIDEO_WIDTH, VIDEO_HEIGHT, FPS, ENCODING_CRF, VIDEO_BITRATE, AUDIO_BITRATE
    _orig = (VIDEO_WIDTH, VIDEO_HEIGHT, FPS, ENCODING_CRF, VIDEO_BITRATE, AUDIO_BITRATE)
    VIDEO_WIDTH, VIDEO_HEIGHT, FPS = video_width, video_height, video_fps
    ENCODING_CRF, VIDEO_BITRATE, AUDIO_BITRATE = video_crf, video_bitrate, audio_bitrate

    try:
        return _build_video_core(
            audio_path=audio_path,
            title=title,
            script=script,
            output_path=output_path,
            stock_clip_paths=stock_clip_paths,
            scene_clip_data=scene_clip_data,
            subtitle_style=subtitle_style,
            burn_captions=burn_captions,
            tmp_dir=tmp_dir,
            watermark=watermark,
            openai_api_key=openai_api_key,
            visual_tier=visual_tier,
            topic_label=topic_label,
        )
    finally:
        VIDEO_WIDTH, VIDEO_HEIGHT, FPS, ENCODING_CRF, VIDEO_BITRATE, AUDIO_BITRATE = _orig


def _build_video_core(
    *,
    audio_path: str,
    title: str,
    script: str,
    output_path: str,
    stock_clip_paths: list[str] | None,
    scene_clip_data: list[dict] | None,
    subtitle_style: str | None,
    burn_captions: bool,
    tmp_dir: str,
    watermark: bool = False,
    openai_api_key: str | None = None,
    visual_tier: str | None = None,
    topic_label: str | None = None,
) -> str:
    """Core build logic — called with module constants already overridden."""

    # ── 0. Load visual profile ───────────────────────────────────────
    try:
        from visual_effects import get_visual_profile, build_composite_filter, build_title_card_filter, build_outro_card_filter
        _vprofile = get_visual_profile(visual_tier or "free")
        _use_premium_visuals = True
        logger.info("Visual tier: %s (Ken Burns=%s, transitions=%s, grade=%s)",
                     _vprofile.tier.value,
                     _vprofile.ken_burns.enabled,
                     _vprofile.transitions.enabled,
                     _vprofile.color_grade.to_filter()[:40] or "none")
    except Exception as ve_err:
        logger.warning("Could not load visual_effects — using baseline visuals: %s", ve_err)
        _vprofile = None
        _use_premium_visuals = False

    # ── 1. Audio duration ────────────────────────────────────────────
    narration_duration = _get_audio_duration(audio_path)
    logger.info("Audio duration: %.1fs", narration_duration)

    total_duration = TITLE_CARD_DURATION + narration_duration + OUTRO_CARD_DURATION

    # ── 2. Download / prepare stock footage ──────────────────────────
    if scene_clip_data is not None:
        # Scene-aware mode: clips already downloaded per-scene
        total_clips = sum(len(sd.get("clips", [])) for sd in scene_clip_data)
        logger.info("Using scene-aware clips: %d clips across %d scenes", total_clips, len(scene_clip_data))
        background_path = _prepare_background_from_scenes(
            scene_clip_data, narration_duration, tmp_dir,
            visual_profile=_vprofile if _use_premium_visuals else None,
        )
    elif stock_clip_paths is not None:
        # Legacy mode: flat list of clip paths provided
        logger.info("Preparing background from %d clips (legacy) …", len(stock_clip_paths))
        background_path = _prepare_background(
            stock_clip_paths, narration_duration, tmp_dir,
            visual_profile=_vprofile if _use_premium_visuals else None,
        )
    else:
        # Auto-download (legacy fallback)
        logger.info("Downloading %d stock footage clips …", NUM_STOCK_CLIPS)
        from stock_footage import download_clips_for_topic
        stock_clip_paths = download_clips_for_topic(title, num_clips=NUM_STOCK_CLIPS)
        logger.info("Preparing background from %d clips …", len(stock_clip_paths))
        background_path = _prepare_background(
            stock_clip_paths, narration_duration, tmp_dir,
            visual_profile=_vprofile if _use_premium_visuals else None,
        )

    logger.info("Background ready: %s", background_path)

    # ── 4. Generate ASS subtitles ────────────────────────────────────
    # Phase 5: Use subtitle_generator for styled captions + SRT export.
    # Falls back to legacy _generate_ass_subtitles() if import fails.
    ass_path = os.path.join(tmp_dir, "captions.ass")
    srt_path = None

    try:
        from subtitle_generator import generate_subtitles
        _srt_out = os.path.join(tmp_dir, "captions.srt")
        _style_name = subtitle_style or "bold_pop"
        srt_path, _ass_path = generate_subtitles(
            script,
            audio_duration=narration_duration,
            style_name=_style_name,
            srt_output=_srt_out,
            ass_output=ass_path,
            burn_captions=burn_captions,
            video_width=VIDEO_WIDTH,
            video_height=VIDEO_HEIGHT,
            audio_path=audio_path,
            openai_api_key=openai_api_key,
        )
        if _ass_path:
            ass_path = _ass_path
        logger.info("Phase 5 subtitles: style=%s, SRT=%s, ASS=%s", _style_name, srt_path, ass_path)

        # Copy SRT to output/ so pipeline can pick it up
        import shutil as _shutil
        srt_output_path = str(OUTPUT_DIR / "captions.srt")
        _shutil.copy2(srt_path, srt_output_path)
        srt_path = srt_output_path
    except Exception as sub_err:
        logger.warning("Phase 5 subtitle_generator failed — using legacy fallback: %s", sub_err)
        sentences = _split_script_to_sentences(script)
        logger.info("Generating %d caption segments as ASS subtitles (legacy)", len(sentences))
        _generate_ass_subtitles(sentences, narration_duration, ass_path)

    # ── 5. Composite main section ────────────────────────────────────
    logger.info("Compositing main section (background + overlay + captions + branding) …")
    # Phase 5: If burn_captions is False, create an empty ASS file so the
    # composite function still works (zero subtitle events = nothing rendered).
    if not burn_captions:
        empty_ass = os.path.join(tmp_dir, "captions_empty.ass")
        with open(empty_ass, "w", encoding="utf-8") as _ef:
            _ef.write("[Script Info]\nTitle: Empty\nScriptType: v4.00+\n"
                       f"PlayResX: {VIDEO_WIDTH}\nPlayResY: {VIDEO_HEIGHT}\n\n"
                       "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                       "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
                       "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                       f"Style: Default,Liberation Sans,38,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,"
                       "-1,0,0,0,100,100,0,0,1,2,0,2,40,40,80,1\n\n"
                       "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        ass_path = empty_ass
        logger.info("Burn captions disabled — using empty ASS file")

    main_path = _composite_main_section(
        background_path, audio_path, ass_path, narration_duration, tmp_dir,
        watermark=watermark,
        visual_profile=_vprofile if _use_premium_visuals else None,
        topic_label=topic_label,
    )
    logger.info("Main section ready: %s", main_path)

    # ── 6. Title card ────────────────────────────────────────────────
    logger.info("Rendering title card (%.1fs) …", TITLE_CARD_DURATION)
    title_card_path = _create_title_card(
        title, tmp_dir,
        visual_profile=_vprofile if _use_premium_visuals else None,
    )
    logger.info("Title card ready")

    # ── 7. Outro card ────────────────────────────────────────────────
    logger.info("Rendering outro card (%.1fs) …", OUTRO_CARD_DURATION)
    outro_card_path = _create_outro_card(
        tmp_dir,
        visual_profile=_vprofile if _use_premium_visuals else None,
    )
    logger.info("Outro card ready")

    # ── 8. Final assembly ────────────────────────────────────────────
    logger.info("Assembling final video (%.0fs total) …", total_duration)
    _assemble_final(title_card_path, main_path, outro_card_path, output_path, tmp_dir)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("Video saved → %s (%.1f MB)", output_path, size_mb)

    # ── 9. File-size enforcement ─────────────────────────────────────
    output_path = _enforce_size_limit(output_path)

    # ── 10. Output validation (non-fatal — warn but don't crash) ────
    try:
        _validate_output_video(
            output_path,
            expected_width=VIDEO_WIDTH,
            expected_height=VIDEO_HEIGHT,
        )
    except Exception as val_err:
        logger.warning("Output validation flagged an issue (non-fatal): %s", val_err)

    # Phase 5: Store SRT path for pipeline access
    global last_srt_path
    last_srt_path = srt_path

    return output_path


# ══════════════════════════════════════════════════════════════════════
# MULTI-FORMAT EXPORT — convert a finished landscape video to
# portrait (9:16 for Shorts/Reels/TikTok) or square (1:1 for IG Feed).
#
# Strategy: single FFmpeg pass — crop + scale + re-burn captions.
# No duplicate API calls, no re-download.  ~30-60s per reformat.
# ══════════════════════════════════════════════════════════════════════

# Format presets: (width, height, label)
FORMAT_PRESETS: dict[str, dict] = {
    "landscape": {
        "width": 1280,
        "height": 720,
        "label": "YouTube (16:9)",
        "aspect": "16:9",
    },
    "portrait": {
        "width": 1080,
        "height": 1920,
        "label": "Shorts / Reels / TikTok (9:16)",
        "aspect": "9:16",
    },
    "square": {
        "width": 1080,
        "height": 1080,
        "label": "Instagram Feed (1:1)",
        "aspect": "1:1",
    },
}


def reformat_video(
    source_video_path: str,
    target_format: str,
    *,
    output_path: str | None = None,
    script: str | None = None,
    title: str | None = None,
    subtitle_style: str | None = None,
    burn_captions: bool = True,
) -> str:
    """Reformat a finished landscape video to a different aspect ratio.

    This is a **post-build** operation — it takes an existing video and
    creates a new variant optimised for the target platform.

    For portrait (9:16):
      - Center-crops the landscape frame to extract the middle vertical slice
      - Re-renders title card and outro at portrait dimensions
      - Optionally re-burns captions sized for the portrait frame

    For square (1:1):
      - Center-crops to square from the landscape frame
      - Re-renders title/outro cards at square dimensions

    Parameters
    ----------
    source_video_path : str
        Path to the original landscape MP4.
    target_format : str
        One of: "portrait", "square" (or "landscape" — returns the source).
    output_path : str | None
        Where to save. Auto-generated if None.
    script : str | None
        Full script text — needed to re-burn captions at correct size.
    title : str | None
        Video title — used for the reformatted title card.
    subtitle_style : str | None
        Caption style preset name (e.g. "bold_pop").
    burn_captions : bool
        Whether to burn captions into the reformatted video.

    Returns
    -------
    str
        Path to the reformatted video file.
    """
    if target_format not in FORMAT_PRESETS:
        raise ValueError(f"Unknown format '{target_format}'. Choose from: {list(FORMAT_PRESETS.keys())}")

    if target_format == "landscape":
        logger.info("Format is already landscape — returning source")
        return source_video_path

    if not os.path.isfile(source_video_path):
        raise RenderError(f"Source video not found: {source_video_path}")

    preset = FORMAT_PRESETS[target_format]
    tw, th = preset["width"], preset["height"]

    if output_path is None:
        base, ext = os.path.splitext(source_video_path)
        output_path = f"{base}_{target_format}{ext}"

    logger.info("Reformatting → %s (%dx%d) …", target_format, tw, th)

    tmp_dir = tempfile.mkdtemp(prefix=f"tubevo_reformat_{target_format}_")

    try:
        return _reformat_inner(
            source_video_path=source_video_path,
            target_format=target_format,
            tw=tw, th=th,
            output_path=output_path,
            script=script,
            title=title,
            subtitle_style=subtitle_style,
            burn_captions=burn_captions,
            tmp_dir=tmp_dir,
        )
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def _reformat_inner(
    *,
    source_video_path: str,
    target_format: str,
    tw: int,
    th: int,
    output_path: str,
    script: str | None,
    title: str | None,
    subtitle_style: str | None,
    burn_captions: bool,
    tmp_dir: str,
) -> str:
    """Inner reformat — extract main section, crop video, re-burn captions.

    Gracefully degrades if FFmpeg filters (drawtext, ass) are unavailable
    (e.g. macOS Homebrew build without --enable-libfreetype / --enable-libass).
    On Railway/Docker the full filter set is always available.
    """

    has_drawtext = _has_ffmpeg_filter("drawtext")
    has_ass = _has_ffmpeg_filter("ass")

    # ── 1. Probe source video ────────────────────────────────────────
    source_dur = _get_video_duration(source_video_path)
    logger.info("Source video: %.1fs  (drawtext=%s, ass=%s)", source_dur, has_drawtext, has_ass)

    # The landscape video has title card + main + outro structure.
    # We rebuild title/outro at the new dimensions and crop the main section.
    main_start = TITLE_CARD_DURATION
    main_end = source_dur - OUTRO_CARD_DURATION
    main_dur = max(1.0, main_end - main_start)

    # ── 2. Calculate crop geometry ───────────────────────────────────
    src_w, src_h = VIDEO_WIDTH, VIDEO_HEIGHT  # 1280 x 720
    target_aspect = tw / th

    if target_aspect < (src_w / src_h):
        # Target is taller (portrait/square) — crop width
        crop_h = src_h
        crop_w = int(src_h * target_aspect)
    else:
        # Target is wider — crop height
        crop_w = src_w
        crop_h = int(src_w / target_aspect)

    # Force even dimensions (required by libx264)
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    crop_x = (src_w - crop_w) // 2
    crop_y = (src_h - crop_h) // 2

    # ── 3. Build main section (crop + scale + overlays) ──────────────
    composited_main_path = os.path.join(tmp_dir, "main_composited.mp4")

    # Build the video filter chain — only include available filters
    darken = 1.0 - DARK_OVERLAY_OPACITY
    vf_parts: list[str] = [
        f"colorchannelmixer=rr={darken}:gg={darken}:bb={darken}",
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
        f"scale={tw}:{th}",
        f"fps={FPS}",
        "format=yuv420p",
    ]

    # Re-burn captions if available
    if burn_captions and script and has_ass:
        try:
            from subtitle_generator import generate_subtitles_for_format
            _srt_out = os.path.join(tmp_dir, "captions.srt")
            _ass_out = os.path.join(tmp_dir, "captions.ass")
            _style_name = subtitle_style or "bold_pop"
            _, _ass_path = generate_subtitles_for_format(
                script,
                audio_duration=main_dur,
                video_width=tw,
                video_height=th,
                style_name=_style_name,
                srt_output=_srt_out,
                ass_output=_ass_out,
            )
            if _ass_path:
                # Escape path for FFmpeg filter: replace \ with / and : with \:
                ass_escaped = _ass_path.replace("\\", "/").replace(":", "\\:")
                vf_parts.append(f"ass='{ass_escaped}'")
                logger.info("Will re-burn captions for %s at %dx%d", target_format, tw, th)
        except Exception as sub_err:
            logger.warning("Could not generate captions for %s: %s", target_format, sub_err)
    elif burn_captions and script and not has_ass:
        logger.info("ASS filter not available — skipping caption burn (OK for local dev)")

    # Branding watermark (only if drawtext available)
    if has_drawtext:
        font_escaped = FONT.replace("\\", "/").replace(":", "\\:")
        if target_format == "portrait":
            brand_x = "(w-text_w)/2"
            brand_y = "60"
            brand_size = 20
        else:
            brand_x = "40"
            brand_y = "28"
            brand_size = BRAND_FONT_SIZE

        vf_parts.append(
            f"drawtext=fontfile='{font_escaped}':text='TUBEVO':"
            f"fontsize={brand_size}:fontcolor=0x00D4AA:x={brand_x}:y={brand_y}"
        )

    # Progress bar at bottom (drawbox is widely available)
    bar_h = 4
    vf_parts.append(
        f"drawbox=x=0:y=ih-{bar_h}:w='floor(iw*(t/{main_dur:.2f}))':h={bar_h}:"
        f"color=0x00D4AA:t=fill"
    )

    vf_chain = ",".join(vf_parts)

    _run_ffmpeg([
        "-ss", f"{main_start:.2f}",
        "-i", source_video_path,
        "-t", f"{main_dur:.2f}",
        "-vf", vf_chain,
        "-c:v", "libx264", "-preset", ENCODING_PRESET,
        "-crf", ENCODING_CRF, "-maxrate", VIDEO_BITRATE, "-bufsize", "2000k",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ac", "2", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-max_muxing_queue_size", "512",
        composited_main_path,
    ], f"composite {target_format} main section")

    # ── 4. Title card at new dimensions ──────────────────────────────
    title_text = title or "TUBEVO"
    title_card_path = _create_title_card_for_format(title_text, tw, th, tmp_dir)

    # ── 5. Outro card at new dimensions ──────────────────────────────
    outro_card_path = _create_outro_card_for_format(tw, th, tmp_dir)

    # ── 6. Final assembly ────────────────────────────────────────────
    logger.info("Assembling reformatted video (%.0fs) …", main_dur + TITLE_CARD_DURATION + OUTRO_CARD_DURATION)
    _assemble_final_for_format(
        title_card_path, composited_main_path, outro_card_path,
        output_path, tw, th, tmp_dir,
    )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("Reformatted video saved → %s (%.1f MB, %dx%d)", output_path, size_mb, tw, th)

    # Size enforcement
    output_path = _enforce_size_limit(output_path)
    return output_path


def _create_title_card_for_format(
    title: str, width: int, height: int, tmp_dir: str,
    duration: float = TITLE_CARD_DURATION,
) -> str:
    """Render a title card at the given dimensions.

    Falls back to a plain dark card if drawtext is unavailable.
    """
    output_path = os.path.join(tmp_dir, "title_card_fmt.mp4")

    if not _has_ffmpeg_filter("drawtext"):
        # Fallback: plain dark card without text
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"color=c=0x0A0A0A:s={width}x{height}:d={duration}:r={FPS}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path,
        ], f"render plain title card ({width}x{height})")
        return output_path

    title_text_file = os.path.join(tmp_dir, "title_text_fmt.txt")
    # Narrower wrap for portrait
    wrap_w = 20 if width < height else 35
    wrapped_title = textwrap.fill(title, width=wrap_w)
    with open(title_text_file, "w", encoding="utf-8") as f:
        f.write(wrapped_title)

    font_escaped = FONT.replace("\\", "/").replace(":", "\\:")
    title_file_escaped = title_text_file.replace("\\", "/").replace(":", "\\:")

    # Scale font sizes relative to dimensions
    base_title_size = 40 if width >= height else 36
    base_brand_size = 24 if width >= height else 20
    brand_y = "(h/2)-120" if width < height else "(h/2)-90"
    title_y = "(h/2)+10" if width >= height else "(h/2)-20"

    _run_ffmpeg([
        "-f", "lavfi",
        "-i", f"color=c=0x0A0A0A:s={width}x{height}:d={duration}:r={FPS}",
        "-vf", (
            f"format=yuv420p,"
            f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize={base_brand_size}:"
            f"fontcolor=0x00D4AA:x=(w-text_w)/2:y={brand_y},"
            f"drawtext=fontfile='{font_escaped}':textfile='{title_file_escaped}':"
            f"fontsize={base_title_size}:fontcolor=white:x=(w-text_w)/2:y={title_y}:line_spacing=8"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        output_path,
    ], f"render title card ({width}x{height})")

    return output_path


def _create_outro_card_for_format(
    width: int, height: int, tmp_dir: str,
    duration: float = OUTRO_CARD_DURATION,
) -> str:
    """Render the outro card at the given dimensions.

    Falls back to a plain dark card if drawtext is unavailable.
    """
    output_path = os.path.join(tmp_dir, "outro_card_fmt.mp4")

    if not _has_ffmpeg_filter("drawtext"):
        _run_ffmpeg([
            "-f", "lavfi",
            "-i", f"color=c=0x0A0A0A:s={width}x{height}:d={duration}:r={FPS}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path,
        ], f"render plain outro card ({width}x{height})")
        return output_path

    font_escaped = FONT.replace("\\", "/").replace(":", "\\:")

    sub_size = 48 if width >= height else 40
    cta_size = 28 if width >= height else 22
    brand_size = 20 if width >= height else 16

    _run_ffmpeg([
        "-f", "lavfi",
        "-i", f"color=c=0x0A0A0A:s={width}x{height}:d={duration}:r={FPS}",
        "-vf", (
            f"format=yuv420p,"
            f"drawtext=fontfile='{font_escaped}':text='SUBSCRIBE FOR MORE':fontsize={sub_size}:"
            f"fontcolor=0x00D4AA:x=(w-text_w)/2:y=(h/2)-60,"
            f"drawtext=fontfile='{font_escaped}':text='Like · Comment · Share':fontsize={cta_size}:"
            f"fontcolor=white:x=(w-text_w)/2:y=(h/2)+20,"
            f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize={brand_size}:"
            f"fontcolor=0x888888:x=(w-text_w)/2:y=(h/2)+80"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        output_path,
    ], f"render outro card ({width}x{height})")

    return output_path


def _assemble_final_for_format(
    title_card_path: str,
    main_section_path: str,
    outro_card_path: str,
    output_path: str,
    width: int,
    height: int,
    tmp_dir: str,
) -> str:
    """Concatenate title → main → outro, ensuring all segments match dimensions."""
    title_with_audio = os.path.join(tmp_dir, "title_with_audio_fmt.mp4")
    outro_with_audio = os.path.join(tmp_dir, "outro_with_audio_fmt.mp4")

    title_dur = _get_video_duration(title_card_path)
    _run_ffmpeg([
        "-i", title_card_path,
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={title_dur}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-shortest",
        title_with_audio,
    ], "add silent audio to title card (reformat)")

    outro_dur = _get_video_duration(outro_card_path)
    _run_ffmpeg([
        "-i", outro_card_path,
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={outro_dur}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-shortest",
        outro_with_audio,
    ], "add silent audio to outro card (reformat)")

    concat_list = os.path.join(tmp_dir, "concat_reformat.txt")
    with open(concat_list, "w") as f:
        f.write(f"file '{title_with_audio}'\n")
        f.write(f"file '{main_section_path}'\n")
        f.write(f"file '{outro_with_audio}'\n")

    _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c:v", "libx264", "-preset", ENCODING_PRESET,
        "-crf", ENCODING_CRF, "-maxrate", VIDEO_BITRATE, "-bufsize", "2000k",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ac", "2", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        "-max_muxing_queue_size", "512",
        "-movflags", "+faststart",
        output_path,
    ], f"assemble final ({width}x{height})")

    return output_path


def get_available_formats() -> list[dict]:
    """Return available export format presets for the frontend."""
    return [
        {
            "key": key,
            "label": preset["label"],
            "width": preset["width"],
            "height": preset["height"],
            "aspect": preset["aspect"],
        }
        for key, preset in FORMAT_PRESETS.items()
    ]


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_audio = str(OUTPUT_DIR / "voiceover.mp3")
    script_path = OUTPUT_DIR / "latest_script.txt"
    meta_path = OUTPUT_DIR / "latest_metadata.json"

    if os.path.isfile(test_audio) and script_path.exists() and meta_path.exists():
        script_text = script_path.read_text(encoding="utf-8")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        clip_dir = OUTPUT_DIR / "clips"
        clip_paths = sorted(str(p) for p in clip_dir.glob("clip_*.mp4")) if clip_dir.exists() else None
        build_video(
            audio_path=test_audio,
            title=meta.get("title", "Tubevo"),
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
