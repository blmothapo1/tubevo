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

# Encoding
ENCODING_PRESET = "fast"       # fast for Railway CPU limits
VIDEO_BITRATE = "4000k"        # 720p needs less bitrate
AUDIO_BITRATE = "128k"

# Cross-platform font detection
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
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
    logger.info("Running %s …", description)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.error("%s stderr: %s", description, result.stderr[-2000:] if result.stderr else "(none)")
        raise RuntimeError(f"{description} failed (exit {result.returncode}): {result.stderr[-500:]}")


def _run_ffprobe(path: str) -> dict:
    """Probe a media file and return the JSON output."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}")
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


# ── Step 1: Prepare stock footage background ────────────────────────

def _prepare_background(
    clip_paths: list[str],
    target_duration: float,
    tmp_dir: str,
) -> str:
    """Scale, trim, and concatenate stock clips into a single background.mp4.

    Uses FFmpeg concat demuxer — processes clips one at a time, never loads
    them all into RAM simultaneously.
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
    segment_files: list[str] = []
    for i, (path, use_dur) in enumerate(segments):
        seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp4")
        _run_ffmpeg([
            "-i", path,
            "-t", f"{use_dur:.2f}",
            "-vf", (
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps={FPS},format=yuv420p"
            ),
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            seg_path,
        ], f"scale/trim segment {i}")
        segment_files.append(seg_path)

    if len(segment_files) == 1:
        shutil.move(segment_files[0], output_path)
        return output_path

    # Write concat list
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
        return _prepare_background([], narration_duration, tmp_dir)

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

        if total_clip_dur >= scene_budget:
            for path, dur in valid:
                if scene_remaining <= 0:
                    break
                share = max(1.5, (dur / total_clip_dur) * scene_budget)
                share = min(share, scene_remaining, dur)
                seg_path = os.path.join(tmp_dir, f"seg_{seg_idx:03d}.mp4")
                _run_ffmpeg([
                    "-i", path,
                    "-t", f"{share:.2f}",
                    "-vf", (
                        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"fps={FPS},format=yuv420p"
                    ),
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
                _run_ffmpeg([
                    "-i", path,
                    "-t", f"{use_dur:.2f}",
                    "-vf", (
                        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"fps={FPS},format=yuv420p"
                    ),
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
        return _prepare_background(all_clips, narration_duration, tmp_dir)

    if len(segment_files) == 1:
        shutil.move(segment_files[0], output_path)
        return output_path

    # Concat all scene segments
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

def _create_title_card(title: str, tmp_dir: str, duration: float = TITLE_CARD_DURATION) -> str:
    """Render a title card as a short video clip using FFmpeg drawtext."""
    output_path = os.path.join(tmp_dir, "title_card.mp4")

    # Write title to a temp file so drawtext can handle multi-line text
    title_text_file = os.path.join(tmp_dir, "title_text.txt")
    wrapped_title = textwrap.fill(title, width=35)
    with open(title_text_file, "w", encoding="utf-8") as f:
        f.write(wrapped_title)

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

def _create_outro_card(tmp_dir: str, duration: float = OUTRO_CARD_DURATION) -> str:
    """Render the subscribe/CTA outro card."""
    output_path = os.path.join(tmp_dir, "outro_card.mp4")
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
) -> str:
    """Compose background + dark overlay + subtitles + branding + progress bar.

    All done in a single FFmpeg filtergraph pass — constant memory usage.
    """
    output_path = os.path.join(tmp_dir, "main_section.mp4")
    font_escaped = FONT.replace("\\", "/").replace(":", "\\:")

    # Escape the ASS path for FFmpeg filter (colons and backslashes)
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

    _run_ffmpeg([
        "-i", background_path,
        "-i", audio_path,
        "-vf", vf,
        "-t", f"{narration_duration:.2f}",
        "-c:v", "libx264", "-preset", ENCODING_PRESET, "-b:v", VIDEO_BITRATE,
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_path,
    ], "composite main section")

    return output_path


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

    _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy",
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
        "-c:v", "libx264", "-preset", "slow", "-b:v", target_bitrate,
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-pix_fmt", "yuv420p",
        compressed_path,
    ], "compress oversized video")

    new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
    logger.info("Compressed: %.1f MB → %.1f MB", size_mb, new_size_mb)

    os.replace(compressed_path, video_path)
    return video_path


# ── Main entry point ────────────────────────────────────────────────

def build_video(
    audio_path: str,
    title: str,
    script: str,
    *,
    output_path: str | None = None,
    stock_clip_paths: list[str] | None = None,
    scene_clip_data: list[dict] | None = None,
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
    """
    if output_path is None:
        slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
        slug = re.sub(r'[\s_]+', '_', slug)[:80]
        output_path = str(OUTPUT_DIR / f"{slug}.mp4")

    logger.info("Building video (FFmpeg-native, %dx%d @ %d fps) …", VIDEO_WIDTH, VIDEO_HEIGHT, FPS)

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
            tmp_dir=tmp_dir,
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
    tmp_dir: str,
) -> str:
    """Inner build function — all work happens here."""

    # ── 1. Audio duration ────────────────────────────────────────────
    narration_duration = _get_audio_duration(audio_path)
    logger.info("Audio duration: %.1fs", narration_duration)

    total_duration = TITLE_CARD_DURATION + narration_duration + OUTRO_CARD_DURATION

    # ── 2. Download / prepare stock footage ──────────────────────────
    if scene_clip_data is not None:
        # Scene-aware mode: clips already downloaded per-scene
        total_clips = sum(len(sd.get("clips", [])) for sd in scene_clip_data)
        logger.info("Using scene-aware clips: %d clips across %d scenes", total_clips, len(scene_clip_data))
        background_path = _prepare_background_from_scenes(scene_clip_data, narration_duration, tmp_dir)
    elif stock_clip_paths is not None:
        # Legacy mode: flat list of clip paths provided
        logger.info("Preparing background from %d clips (legacy) …", len(stock_clip_paths))
        background_path = _prepare_background(stock_clip_paths, narration_duration, tmp_dir)
    else:
        # Auto-download (legacy fallback)
        logger.info("Downloading %d stock footage clips …", NUM_STOCK_CLIPS)
        from stock_footage import download_clips_for_topic
        stock_clip_paths = download_clips_for_topic(title, num_clips=NUM_STOCK_CLIPS)
        logger.info("Preparing background from %d clips …", len(stock_clip_paths))
        background_path = _prepare_background(stock_clip_paths, narration_duration, tmp_dir)

    logger.info("Background ready: %s", background_path)

    # ── 4. Generate ASS subtitles ────────────────────────────────────
    sentences = _split_script_to_sentences(script)
    logger.info("Generating %d caption segments as ASS subtitles", len(sentences))
    ass_path = os.path.join(tmp_dir, "captions.ass")
    _generate_ass_subtitles(sentences, narration_duration, ass_path)

    # ── 5. Composite main section ────────────────────────────────────
    logger.info("Compositing main section (background + overlay + captions + branding) …")
    main_path = _composite_main_section(
        background_path, audio_path, ass_path, narration_duration, tmp_dir,
    )
    logger.info("Main section ready: %s", main_path)

    # ── 6. Title card ────────────────────────────────────────────────
    logger.info("Rendering title card (%.1fs) …", TITLE_CARD_DURATION)
    title_card_path = _create_title_card(title, tmp_dir)
    logger.info("Title card ready")

    # ── 7. Outro card ────────────────────────────────────────────────
    logger.info("Rendering outro card (%.1fs) …", OUTRO_CARD_DURATION)
    outro_card_path = _create_outro_card(tmp_dir)
    logger.info("Outro card ready")

    # ── 8. Final assembly ────────────────────────────────────────────
    logger.info("Assembling final video (%.0fs total) …", total_duration)
    _assemble_final(title_card_path, main_path, outro_card_path, output_path, tmp_dir)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info("Video saved → %s (%.1f MB)", output_path, size_mb)

    # ── 9. File-size enforcement ─────────────────────────────────────
    output_path = _enforce_size_limit(output_path)

    return output_path


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
