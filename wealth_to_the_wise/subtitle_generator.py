"""
subtitle_generator.py — Generate SRT/ASS subtitles synced to speech timing.

Phase 5 — Subtitle System.

Features:
  - Auto-generate SRT from script text
  - Estimate timestamps based on word-rate (synced to audio duration)
  - Multiple caption styles (minimal, bold pop, cinematic, karaoke highlight)
  - Proper line wrapping (max ~40 chars per line, word-boundary aware)
  - Export both SRT (for YouTube upload) and ASS (for burn-in)

Usage:
    from subtitle_generator import generate_subtitles

    srt_path, ass_path = generate_subtitles(
        script="Your script text...",
        audio_duration=120.0,
        style="bold_pop",
    )
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("tubevo.subtitle_generator")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Video resolution (must match video_builder) ─────────────────────
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720


# ── Subtitle style presets ──────────────────────────────────────────

@dataclass
class SubtitleStyle:
    """Defines visual appearance of burned-in captions."""
    name: str
    font_family: str
    font_size: int
    primary_color: str        # ASS colour format: &HAABBGGRR
    outline_color: str
    back_color: str
    bold: bool
    italic: bool
    outline_width: float
    shadow_depth: float
    alignment: int            # ASS alignment: 2=bottom-center
    margin_v: int             # Vertical margin from edge
    margin_l: int
    margin_r: int
    border_style: int         # 1=outline+shadow, 3=opaque box
    wrap_width: int           # Max chars per line
    fade_in_ms: int = 200
    fade_out_ms: int = 150


# Pre-built style presets
SUBTITLE_STYLES: dict[str, SubtitleStyle] = {
    "minimal": SubtitleStyle(
        name="Minimal",
        font_family="Liberation Sans",
        font_size=38,
        primary_color="&H00FFFFFF",      # white
        outline_color="&H00000000",      # black outline
        back_color="&H96000000",         # semi-transparent black
        bold=False,
        italic=False,
        outline_width=1.5,
        shadow_depth=0,
        alignment=2,
        margin_v=60,
        margin_l=40,
        margin_r=40,
        border_style=1,
        wrap_width=48,
        fade_in_ms=200,
        fade_out_ms=150,
    ),
    "bold_pop": SubtitleStyle(
        name="Bold Pop",
        font_family="Liberation Sans",
        font_size=44,
        primary_color="&H00FFFFFF",      # white
        outline_color="&H00000000",      # black outline
        back_color="&H96000000",
        bold=True,
        italic=False,
        outline_width=2.5,
        shadow_depth=0,
        alignment=2,
        margin_v=70,
        margin_l=40,
        margin_r=40,
        border_style=1,
        wrap_width=42,
        fade_in_ms=150,
        fade_out_ms=100,
    ),
    "cinematic": SubtitleStyle(
        name="Cinematic",
        font_family="Liberation Sans",
        font_size=40,
        primary_color="&H00FFFFFF",
        outline_color="&H00111111",
        back_color="&HB4000000",         # darker semi-transparent
        bold=True,
        italic=False,
        outline_width=2.0,
        shadow_depth=1,
        alignment=2,
        margin_v=80,
        margin_l=60,
        margin_r=60,
        border_style=3,                  # opaque box
        wrap_width=45,
        fade_in_ms=300,
        fade_out_ms=200,
    ),
    "accent_highlight": SubtitleStyle(
        name="Accent Highlight",
        font_family="Liberation Sans",
        font_size=42,
        primary_color="&H00AAD400",      # accent teal (BGR)
        outline_color="&H00000000",
        back_color="&H96000000",
        bold=True,
        italic=False,
        outline_width=2.0,
        shadow_depth=0,
        alignment=2,
        margin_v=70,
        margin_l=40,
        margin_r=40,
        border_style=1,
        wrap_width=42,
        fade_in_ms=200,
        fade_out_ms=150,
    ),
}

DEFAULT_STYLE = "bold_pop"


# ── Text processing ─────────────────────────────────────────────────

def split_script_to_segments(script: str, max_chars: int = 42) -> list[str]:
    """Split a script into display segments suitable for on-screen captions.

    Rules:
    - Split on sentence boundaries first
    - Long sentences split on commas, colons, dashes
    - Final segments wrapped to max_chars per line with word-boundary awareness
    - No segment exceeds ~2 lines of display
    """
    # First pass: split on sentence boundaries
    raw_sentences = re.split(r'(?<=[.!?])\s+', script.strip())
    raw_sentences = [s.strip() for s in raw_sentences if s.strip()]

    segments: list[str] = []
    for sent in raw_sentences:
        if len(sent) <= max_chars * 2:
            segments.append(sent)
        else:
            # Split long sentences on natural break points
            parts = re.split(r'(?<=,)\s+|(?<=:)\s+|(?<=;)\s+|(?<=—)\s*|(?<= -)\s+', sent)
            parts = [p.strip() for p in parts if p.strip()]

            # Recombine very short fragments
            combined: list[str] = []
            buffer = ""
            for part in parts:
                if buffer and len(buffer) + len(part) + 1 <= max_chars * 2:
                    buffer += " " + part
                elif buffer:
                    combined.append(buffer)
                    buffer = part
                else:
                    buffer = part
            if buffer:
                combined.append(buffer)

            segments.extend(combined)

    return segments


def wrap_segment(text: str, max_width: int = 42) -> str:
    """Wrap a caption segment into lines for on-screen display.

    Returns text with \\N (ASS) or \\n (SRT) newlines.
    Wraps at word boundaries, keeping lines balanced.
    """
    if len(text) <= max_width:
        return text

    # Use textwrap for clean word-boundary wrapping
    lines = textwrap.wrap(text, width=max_width, break_long_words=False, break_on_hyphens=True)

    # Balance line lengths (avoid one long + one very short line)
    if len(lines) == 2:
        total = len(text)
        target = total // 2
        # Try to find a space near the midpoint
        best_split = target
        for i in range(max(0, target - 8), min(len(text), target + 8)):
            if text[i] == ' ':
                best_split = i
                break
        if abs(best_split - target) < 10:
            lines = [text[:best_split].strip(), text[best_split:].strip()]

    return "\n".join(lines)


# ── Timestamp calculation ────────────────────────────────────────────

@dataclass
class TimedSegment:
    """A caption segment with start/end timestamps."""
    text: str
    start: float  # seconds
    end: float    # seconds
    word_count: int = 0

    def __post_init__(self):
        self.word_count = max(len(self.text.split()), 1)


def compute_timestamps(
    segments: list[str],
    total_duration: float,
    *,
    min_display_time: float = 1.2,
    max_display_time: float = 6.0,
    gap_between: float = 0.05,
) -> list[TimedSegment]:
    """Compute timestamps for each caption segment proportional to word count.

    Allocates time based on word count (proportional to speaking rate),
    with minimum and maximum display times enforced.
    """
    word_counts = [max(len(s.split()), 1) for s in segments]
    total_words = sum(word_counts)

    # Account for gaps between segments
    total_gaps = gap_between * max(0, len(segments) - 1)
    available_time = total_duration - total_gaps

    timed: list[TimedSegment] = []
    current_time = 0.0

    for i, (text, wc) in enumerate(zip(segments, word_counts)):
        # Proportional duration based on word count
        raw_duration = (wc / total_words) * available_time
        duration = max(min_display_time, min(max_display_time, raw_duration))

        start = current_time
        end = start + duration

        # Don't exceed total duration
        if end > total_duration:
            end = total_duration

        timed.append(TimedSegment(text=text, start=start, end=end))

        current_time = end + gap_between

    # If we ended early, stretch the last segment
    if timed and timed[-1].end < total_duration - 0.5:
        timed[-1].end = total_duration

    return timed


# ── SRT generation ──────────────────────────────────────────────────

def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"


def generate_srt(
    timed_segments: list[TimedSegment],
    output_path: str,
    max_width: int = 42,
) -> str:
    """Generate an SRT subtitle file from timed segments.

    SRT format is used for YouTube upload (auto-attached as closed captions).
    """
    lines: list[str] = []
    for i, seg in enumerate(timed_segments, 1):
        wrapped = wrap_segment(seg.text, max_width)
        lines.append(str(i))
        lines.append(f"{_seconds_to_srt_time(seg.start)} --> {_seconds_to_srt_time(seg.end)}")
        lines.append(wrapped)
        lines.append("")  # blank line separator

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("SRT generated: %d segments → %s", len(timed_segments), output_path)
    return output_path


# ── ASS generation (for burn-in) ────────────────────────────────────

def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp: H:MM:SS.CC"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def generate_ass(
    timed_segments: list[TimedSegment],
    output_path: str,
    style: SubtitleStyle | None = None,
) -> str:
    """Generate an ASS subtitle file with styled captions for burning in.

    ASS subtitles are rendered by FFmpeg natively (via libass) with zero
    extra RAM — the filter reads the .ass file and burns text frame by frame.
    """
    if style is None:
        style = SUBTITLE_STYLES[DEFAULT_STYLE]

    bold_flag = -1 if style.bold else 0
    italic_flag = -1 if style.italic else 0

    ass_content = f"""[Script Info]
Title: Tubevo Captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_family},{style.font_size},{style.primary_color},&H000000FF,{style.outline_color},{style.back_color},{bold_flag},{italic_flag},0,0,100,100,0,0,{style.border_style},{style.outline_width},{style.shadow_depth},{style.alignment},{style.margin_l},{style.margin_r},{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for seg in timed_segments:
        wrapped = wrap_segment(seg.text, style.wrap_width)
        # Convert \n to ASS line break
        ass_text = wrapped.replace("\n", "\\N")
        # Add fade effect
        effect = f"{{\\fad({style.fade_in_ms},{style.fade_out_ms})}}"

        ass_content += (
            f"Dialogue: 0,{_seconds_to_ass_time(seg.start)},{_seconds_to_ass_time(seg.end)},"
            f"Default,,0,0,0,,{effect}{ass_text}\n"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    logger.info("ASS generated: %d segments, style=%s → %s", len(timed_segments), style.name, output_path)
    return output_path


# ── Main entry point ────────────────────────────────────────────────

def generate_subtitles(
    script: str,
    audio_duration: float,
    *,
    style_name: str = DEFAULT_STYLE,
    srt_output: str | None = None,
    ass_output: str | None = None,
    burn_captions: bool = True,
) -> tuple[str, str | None]:
    """Generate both SRT and (optionally) ASS subtitle files.

    Parameters
    ----------
    script : str
        Full narration script text.
    audio_duration : float
        Duration of the voiceover audio in seconds.
    style_name : str
        Name of the subtitle style preset (see SUBTITLE_STYLES).
    srt_output : str | None
        Path for SRT file. Defaults to output/captions.srt.
    ass_output : str | None
        Path for ASS file. Defaults to output/captions.ass.
    burn_captions : bool
        Whether to generate ASS file for burn-in (default True).

    Returns
    -------
    tuple[str, str | None]
        (srt_path, ass_path or None if burn_captions is False)
    """
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES[DEFAULT_STYLE])

    srt_output = srt_output or str(OUTPUT_DIR / "captions.srt")
    ass_output = ass_output or str(OUTPUT_DIR / "captions.ass")

    logger.info(
        "Generating subtitles: %.1fs audio, style=%s, burn=%s",
        audio_duration, style.name, burn_captions,
    )

    # Split script into display segments
    segments = split_script_to_segments(script, max_chars=style.wrap_width)
    logger.info("Split script into %d caption segments", len(segments))

    # Compute timestamps
    timed = compute_timestamps(segments, audio_duration)

    # Generate SRT (always — used for YouTube upload)
    srt_path = generate_srt(timed, srt_output, max_width=style.wrap_width)

    # Generate ASS (for burn-in, if enabled)
    ass_path = None
    if burn_captions:
        ass_path = generate_ass(timed, ass_output, style=style)

    return srt_path, ass_path


# ── Multi-format subtitle generation ────────────────────────────────

def generate_ass_for_format(
    timed_segments: list[TimedSegment],
    output_path: str,
    *,
    video_width: int,
    video_height: int,
    style: SubtitleStyle | None = None,
) -> str:
    """Generate an ASS subtitle file scaled for a specific video format.

    Adjusts PlayResX/Y, font size, margins, and wrap width based on the
    target dimensions.  For portrait (9:16) videos, captions are larger
    and margins are adjusted for the taller frame.
    """
    if style is None:
        style = SUBTITLE_STYLES[DEFAULT_STYLE]

    bold_flag = -1 if style.bold else 0
    italic_flag = -1 if style.italic else 0

    # Scale font size and margins relative to dimensions.
    # Reference: 1280x720 landscape.  For portrait (1080x1920),
    # we want larger text since the frame is narrower.
    is_portrait = video_height > video_width
    if is_portrait:
        # Portrait: bigger text, narrower wrap, centered lower
        font_scale = 1.3
        margin_v = int(video_height * 0.12)  # ~230px from bottom on 1920h
        margin_lr = int(video_width * 0.06)   # ~65px on 1080w
        wrap_width = 28  # fewer chars per line for narrow frame
    elif video_width == video_height:
        # Square: slightly bigger text
        font_scale = 1.1
        margin_v = int(video_height * 0.10)
        margin_lr = int(video_width * 0.05)
        wrap_width = 36
    else:
        # Landscape: use original settings
        font_scale = 1.0
        margin_v = style.margin_v
        margin_lr = style.margin_l
        wrap_width = style.wrap_width

    scaled_font_size = int(style.font_size * font_scale)
    scaled_outline = style.outline_width * font_scale

    ass_content = f"""[Script Info]
Title: Tubevo Captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_family},{scaled_font_size},{style.primary_color},&H000000FF,{style.outline_color},{style.back_color},{bold_flag},{italic_flag},0,0,100,100,0,0,{style.border_style},{scaled_outline},{style.shadow_depth},{style.alignment},{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for seg in timed_segments:
        wrapped = wrap_segment(seg.text, wrap_width)
        ass_text = wrapped.replace("\n", "\\N")
        effect = f"{{\\fad({style.fade_in_ms},{style.fade_out_ms})}}"

        ass_content += (
            f"Dialogue: 0,{_seconds_to_ass_time(seg.start)},{_seconds_to_ass_time(seg.end)},"
            f"Default,,0,0,0,,{effect}{ass_text}\n"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    logger.info(
        "ASS (format-aware) generated: %d segments, %dx%d, font=%d → %s",
        len(timed_segments), video_width, video_height, scaled_font_size, output_path,
    )
    return output_path


def generate_subtitles_for_format(
    script: str,
    audio_duration: float,
    *,
    video_width: int,
    video_height: int,
    style_name: str = DEFAULT_STYLE,
    srt_output: str | None = None,
    ass_output: str | None = None,
) -> tuple[str, str | None]:
    """Generate subtitles scaled for a specific video format (portrait/square).

    Parameters
    ----------
    script : str
        Full narration script text.
    audio_duration : float
        Duration of the voiceover audio in seconds.
    video_width : int
        Target video width in pixels.
    video_height : int
        Target video height in pixels.
    style_name : str
        Subtitle style preset name.
    srt_output : str | None
        Path for SRT file.
    ass_output : str | None
        Path for ASS file.

    Returns
    -------
    tuple[str, str | None]
        (srt_path, ass_path)
    """
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES[DEFAULT_STYLE])

    srt_output = srt_output or str(OUTPUT_DIR / "captions_fmt.srt")
    ass_output = ass_output or str(OUTPUT_DIR / "captions_fmt.ass")

    # Adjust wrap width for narrower frames
    is_portrait = video_height > video_width
    wrap_width = 28 if is_portrait else (36 if video_width == video_height else style.wrap_width)

    logger.info(
        "Generating format-aware subtitles: %.1fs audio, %dx%d, style=%s",
        audio_duration, video_width, video_height, style.name,
    )

    segments = split_script_to_segments(script, max_chars=wrap_width)
    timed = compute_timestamps(segments, audio_duration)

    srt_path = generate_srt(timed, srt_output, max_width=wrap_width)
    ass_path = generate_ass_for_format(
        timed, ass_output,
        video_width=video_width,
        video_height=video_height,
        style=style,
    )

    return srt_path, ass_path


def get_available_styles() -> list[dict]:
    """Return available subtitle style presets for the frontend."""
    return [
        {
            "key": key,
            "name": style.name,
            "font_size": style.font_size,
            "bold": style.bold,
            "border_style": "Box" if style.border_style == 3 else "Outline",
        }
        for key, style in SUBTITLE_STYLES.items()
    ]


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_script = (
        "Want to build wealth fast? Stop wasting money on things you don't need. "
        "Here are five frugal habits that separate the rich from the broke. "
        "Number one: automate your savings. Pay yourself first. "
        "Number two: cook at home. Restaurants are bleeding you dry. "
        "Number three: cancel subscriptions you don't use. "
        "Number four: buy used when possible. Your ego is not worth the debt. "
        "Number five: invest the difference. Every dollar saved is a soldier working for you."
    )
    srt, ass = generate_subtitles(test_script, audio_duration=60.0, style_name="bold_pop")
    print(f"SRT: {srt}")
    print(f"ASS: {ass}")

    # Print all available styles
    for s in get_available_styles():
        print(f"  Style: {s['key']} → {s['name']}")
