"""
visual_effects.py — Premium Visual Effects Engine (Tiered by Plan)

Generates FFmpeg filter chains that elevate video quality from basic
stock-footage-over-voiceover to genuinely cinematic output.

All effects are pure FFmpeg filters — zero extra dependencies, zero
extra RAM beyond what FFmpeg already uses.

Plan tiers:
  • free     — dark overlay + progress bar (existing baseline)
  • starter  — + cross-dissolve transitions + subtle color grade + fade title
  • pro      — + Ken Burns (zoompan) + cinematic color grade + vignette + grain
  • agency   — + all pro effects + letterboxing + animated lower-third

Usage:
    from visual_effects import VisualProfile, get_visual_profile

    profile = get_visual_profile("pro")
    # Access filter strings, transition settings, title card configs, etc.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("tubevo.visual_effects")


# ══════════════════════════════════════════════════════════════════════
# 1.  VISUAL EFFECT TIERS
# ══════════════════════════════════════════════════════════════════════

class VisualTier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    AGENCY = "agency"


@dataclass
class ColorGrade:
    """Cinematic color grading via FFmpeg eq/colorbalance filters."""
    # eq filter values
    brightness: float = 0.0       # -1.0 to 1.0
    contrast: float = 1.0         # 0.0 to 2.0
    saturation: float = 1.0       # 0.0 to 3.0
    gamma: float = 1.0            # 0.1 to 10.0
    # colorbalance (shadows / midtones / highlights)
    rs: float = 0.0   # red shadows
    gs: float = 0.0   # green shadows
    bs: float = 0.0   # blue shadows
    rm: float = 0.0   # red midtones
    gm: float = 0.0   # green midtones
    bm: float = 0.0   # blue midtones
    rh: float = 0.0   # red highlights
    gh: float = 0.0   # green highlights
    bh: float = 0.0   # blue highlights

    def to_filter(self) -> str:
        """Return FFmpeg eq + colorbalance filter string."""
        parts: list[str] = []

        # Only add eq if something differs from defaults
        eq_parts: list[str] = []
        if abs(self.brightness) > 0.001:
            eq_parts.append(f"brightness={self.brightness:.3f}")
        if abs(self.contrast - 1.0) > 0.001:
            eq_parts.append(f"contrast={self.contrast:.3f}")
        if abs(self.saturation - 1.0) > 0.001:
            eq_parts.append(f"saturation={self.saturation:.3f}")
        if abs(self.gamma - 1.0) > 0.001:
            eq_parts.append(f"gamma={self.gamma:.3f}")
        if eq_parts:
            parts.append("eq=" + ":".join(eq_parts))

        # Only add colorbalance if any channel is non-zero
        cb_parts: list[str] = []
        for attr, key in [
            ("rs", "rs"), ("gs", "gs"), ("bs", "bs"),
            ("rm", "rm"), ("gm", "gm"), ("bm", "bm"),
            ("rh", "rh"), ("gh", "gh"), ("bh", "bh"),
        ]:
            val = getattr(self, attr)
            if abs(val) > 0.001:
                cb_parts.append(f"{key}={val:.3f}")
        if cb_parts:
            parts.append("colorbalance=" + ":".join(cb_parts))

        return ",".join(parts) if parts else ""


# ── Pre-built color grade presets ────────────────────────────────────

COLOR_GRADES: dict[str, ColorGrade] = {
    "none": ColorGrade(),

    # Subtle warm lift — slightly boosts warmth, lifts shadows
    "warm_subtle": ColorGrade(
        brightness=0.02,
        contrast=1.05,
        saturation=1.08,
        rs=0.03, gs=0.01, bs=-0.02,    # warm shadows
        rh=0.02, gh=0.01, bh=-0.01,    # warm highlights
    ),

    # Cinematic teal-orange — Hollywood blockbuster look
    "cinematic": ColorGrade(
        contrast=1.10,
        saturation=1.15,
        gamma=0.95,
        rs=-0.02, gs=-0.01, bs=0.06,   # teal shadows
        rm=0.04, gm=0.01, bm=-0.03,    # warm midtones
        rh=0.05, gh=0.02, bh=-0.04,    # orange highlights
    ),

    # Moody dark — desaturated, high contrast, lifted blacks
    "moody": ColorGrade(
        brightness=0.01,
        contrast=1.15,
        saturation=0.85,
        gamma=0.90,
        rs=0.02, gs=0.00, bs=0.04,     # cool shadows
        rm=0.00, gm=-0.01, bm=0.02,    # slightly cool mids
    ),

    # Clean modern — bright, crisp, slightly desaturated
    "clean_modern": ColorGrade(
        brightness=0.03,
        contrast=1.08,
        saturation=0.95,
        gamma=1.05,
        rh=0.01, gh=0.01, bh=0.01,     # lifted highlights
    ),

    # Finance/authority — deep blues, high contrast, rich
    "finance": ColorGrade(
        contrast=1.12,
        saturation=1.05,
        gamma=0.93,
        rs=-0.01, gs=-0.01, bs=0.05,   # blue shadows
        rm=0.01, gm=0.00, bm=0.01,     # neutral mids
        rh=0.03, gh=0.02, bh=-0.01,    # warm highlights
    ),
}


@dataclass
class KenBurnsConfig:
    """Ken Burns (zoompan) settings for stock footage clips."""
    enabled: bool = False
    # Zoom range: 1.0 = no zoom, 1.15 = 15% zoom
    zoom_start: float = 1.0
    zoom_end: float = 1.15
    # Pan direction randomization
    pan_directions: list[str] = field(default_factory=lambda: [
        "left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top",
        "center_zoom_in", "center_zoom_out",
    ])

    def get_zoompan_filter(
        self,
        width: int,
        height: int,
        fps: int,
        duration: float,
        direction: str | None = None,
    ) -> str:
        """Generate FFmpeg zoompan filter string for a single clip.

        The zoompan filter works on individual frames, so we compute
        the zoom increment per frame to achieve smooth motion.
        """
        if not self.enabled:
            return ""

        total_frames = int(duration * fps)
        if total_frames < 2:
            return ""

        # Choose direction
        if direction is None:
            direction = random.choice(self.pan_directions)

        # Zoompan renders at a higher internal resolution, then scales down.
        # z = zoom factor per frame, d = total frames
        # We use 'on_frame' expressions for smooth animation.
        z_start = self.zoom_start
        z_end = self.zoom_end

        # Common base: zoom linearly from z_start to z_end
        # z='zoom+0.0015' ramps zoom. We use a per-frame increment.
        z_increment = (z_end - z_start) / max(total_frames, 1)

        if direction == "center_zoom_in":
            return (
                f"zoompan=z='min({z_start}+{z_increment:.6f}*on,{z_end})':"
                f"d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps={fps}"
            )
        elif direction == "center_zoom_out":
            return (
                f"zoompan=z='max({z_end}-{z_increment:.6f}*on,{z_start})':"
                f"d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps={fps}"
            )
        elif direction == "left_to_right":
            # Pan from left edge to right edge while zoomed in
            return (
                f"zoompan=z='{z_end}':"
                f"d={total_frames}:"
                f"x='min(on*{width / max(total_frames, 1):.4f},iw-iw/zoom)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps={fps}"
            )
        elif direction == "right_to_left":
            return (
                f"zoompan=z='{z_end}':"
                f"d={total_frames}:"
                f"x='max(iw-iw/zoom-on*{width / max(total_frames, 1):.4f},0)':"
                f"y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps={fps}"
            )
        elif direction == "top_to_bottom":
            return (
                f"zoompan=z='{z_end}':"
                f"d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':"
                f"y='min(on*{height / max(total_frames, 1):.4f},ih-ih/zoom)':"
                f"s={width}x{height}:fps={fps}"
            )
        elif direction == "bottom_to_top":
            return (
                f"zoompan=z='{z_end}':"
                f"d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':"
                f"y='max(ih-ih/zoom-on*{height / max(total_frames, 1):.4f},0)':"
                f"s={width}x{height}:fps={fps}"
            )
        else:
            # Default: gentle center zoom in
            return (
                f"zoompan=z='min({z_start}+{z_increment:.6f}*on,{z_end})':"
                f"d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps={fps}"
            )


@dataclass
class TransitionConfig:
    """Scene transition settings."""
    enabled: bool = False
    # Cross-dissolve duration in seconds
    dissolve_duration: float = 0.5
    # Fade-in at video start
    fade_in_duration: float = 0.8
    # Fade-out at video end
    fade_out_duration: float = 0.6


@dataclass
class FilmEffects:
    """Post-processing film effects."""
    # Vignette: darkens edges for cinematic focus
    vignette_enabled: bool = False
    vignette_angle: float = 0.4       # PI/5 ≈ subtle, PI/2 = heavy
    # Film grain
    grain_enabled: bool = False
    grain_strength: int = 15          # 0-100, lower is subtler
    # Letterboxing (cinematic black bars)
    letterbox_enabled: bool = False
    letterbox_ratio: float = 2.35     # 2.35:1 = anamorphic cinema

    def to_filter(self, width: int, height: int) -> str:
        """Return FFmpeg filter string for film effects."""
        parts: list[str] = []

        if self.vignette_enabled:
            parts.append(f"vignette=angle={self.vignette_angle}")

        if self.grain_enabled:
            # Use noise filter for film grain effect
            # Lightweight: no extra files, no extra memory
            parts.append(
                f"noise=alls={self.grain_strength}:allf=t"
            )

        if self.letterbox_enabled:
            # Add cinematic black bars (pillarbox/letterbox)
            target_h = int(width / self.letterbox_ratio)
            if target_h < height:
                bar_h = (height - target_h) // 2
                # Draw black bars top and bottom
                parts.append(
                    f"drawbox=x=0:y=0:w={width}:h={bar_h}:color=black:t=fill,"
                    f"drawbox=x=0:y={height - bar_h}:w={width}:h={bar_h}:color=black:t=fill"
                )

        return ",".join(parts) if parts else ""


@dataclass
class TitleCardStyle:
    """Title card visual configuration."""
    # Background gradient (start_color → end_color, top to bottom)
    bg_color: str = "0x0A0A0A"
    # Text animation
    fade_in_text: bool = True
    text_fade_duration: float = 0.8
    # Accent line under brand name
    accent_line: bool = False
    accent_line_width: int = 60
    # Particle / shimmer effect (via noise overlay at low opacity)
    shimmer: bool = False
    # Subtitle under main title
    show_subtitle: bool = False
    subtitle_text: str = "WEALTH · MINDSET · FREEDOM"


@dataclass
class VisualProfile:
    """Complete visual configuration for a plan tier."""
    tier: VisualTier
    color_grade: ColorGrade
    ken_burns: KenBurnsConfig
    transitions: TransitionConfig
    film_effects: FilmEffects
    title_style: TitleCardStyle
    # Dark overlay opacity (higher = darker background = more readable text)
    dark_overlay_opacity: float = 0.35
    # Animated lower-third topic label
    lower_third_enabled: bool = False
    # Scene-specific color grade variation
    vary_grade_per_scene: bool = False


# ══════════════════════════════════════════════════════════════════════
# 2.  PROFILE PRESETS PER PLAN
# ══════════════════════════════════════════════════════════════════════

VISUAL_PROFILES: dict[str, VisualProfile] = {
    "free": VisualProfile(
        tier=VisualTier.FREE,
        color_grade=COLOR_GRADES["none"],
        ken_burns=KenBurnsConfig(enabled=False),
        transitions=TransitionConfig(enabled=False),
        film_effects=FilmEffects(),
        title_style=TitleCardStyle(),
        dark_overlay_opacity=0.35,
    ),

    "starter": VisualProfile(
        tier=VisualTier.STARTER,
        color_grade=COLOR_GRADES["warm_subtle"],
        ken_burns=KenBurnsConfig(enabled=False),
        transitions=TransitionConfig(
            enabled=True,
            dissolve_duration=0.4,
            fade_in_duration=0.6,
            fade_out_duration=0.4,
        ),
        film_effects=FilmEffects(),
        title_style=TitleCardStyle(
            fade_in_text=True,
            text_fade_duration=0.6,
        ),
        dark_overlay_opacity=0.30,
    ),

    "pro": VisualProfile(
        tier=VisualTier.PRO,
        color_grade=COLOR_GRADES["cinematic"],
        ken_burns=KenBurnsConfig(
            enabled=True,
            zoom_start=1.0,
            zoom_end=1.12,
        ),
        transitions=TransitionConfig(
            enabled=True,
            dissolve_duration=0.5,
            fade_in_duration=0.8,
            fade_out_duration=0.5,
        ),
        film_effects=FilmEffects(
            vignette_enabled=True,
            vignette_angle=0.4,
            grain_enabled=True,
            grain_strength=12,
        ),
        title_style=TitleCardStyle(
            fade_in_text=True,
            text_fade_duration=0.8,
            accent_line=True,
            accent_line_width=80,
            shimmer=True,
        ),
        dark_overlay_opacity=0.28,
        lower_third_enabled=True,
        vary_grade_per_scene=True,
    ),

    "agency": VisualProfile(
        tier=VisualTier.AGENCY,
        color_grade=COLOR_GRADES["cinematic"],
        ken_burns=KenBurnsConfig(
            enabled=True,
            zoom_start=1.0,
            zoom_end=1.15,
        ),
        transitions=TransitionConfig(
            enabled=True,
            dissolve_duration=0.6,
            fade_in_duration=1.0,
            fade_out_duration=0.6,
        ),
        film_effects=FilmEffects(
            vignette_enabled=True,
            vignette_angle=0.35,
            grain_enabled=True,
            grain_strength=10,
            letterbox_enabled=True,
            letterbox_ratio=2.35,
        ),
        title_style=TitleCardStyle(
            fade_in_text=True,
            text_fade_duration=1.0,
            accent_line=True,
            accent_line_width=100,
            shimmer=True,
            show_subtitle=True,
            subtitle_text="WEALTH · MINDSET · FREEDOM",
        ),
        dark_overlay_opacity=0.25,
        lower_third_enabled=True,
        vary_grade_per_scene=True,
    ),
}


def get_visual_profile(plan: str) -> VisualProfile:
    """Return the visual profile for a given plan tier."""
    return VISUAL_PROFILES.get(plan, VISUAL_PROFILES["free"])


# ══════════════════════════════════════════════════════════════════════
# 3.  COLOR GRADE VARIATION PER SCENE
# ══════════════════════════════════════════════════════════════════════

# Scene-type → preferred color grade name
SCENE_GRADE_MAP: dict[str, str] = {
    "intro": "cinematic",
    "conclusion": "moody",
    "default": "cinematic",
}


def pick_scene_color_grade(
    scene_label: str,
    scene_index: int,
    total_scenes: int,
    *,
    base_grade: str = "cinematic",
    seed: str = "",
) -> ColorGrade:
    """Choose a color grade for a specific scene.

    Creates subtle variation across scenes so the video doesn't feel
    flat/monotone while maintaining overall cohesion.
    """
    rng = random.Random(f"{seed}-{scene_index}")

    # Pick base grade
    if scene_label == "intro":
        grade = COLOR_GRADES.get("cinematic", COLOR_GRADES["none"])
    elif scene_label == "conclusion":
        grade = COLOR_GRADES.get("moody", COLOR_GRADES["none"])
    else:
        # Body scenes: alternate between cinematic variants
        options = ["cinematic", "finance", "clean_modern"]
        chosen = rng.choice(options)
        grade = COLOR_GRADES.get(chosen, COLOR_GRADES["none"])

    # Add slight per-scene jitter to prevent monotony
    jitter = rng.uniform(-0.02, 0.02)

    return ColorGrade(
        brightness=grade.brightness + jitter,
        contrast=grade.contrast + jitter * 0.5,
        saturation=grade.saturation + jitter,
        gamma=grade.gamma,
        rs=grade.rs, gs=grade.gs, bs=grade.bs,
        rm=grade.rm, gm=grade.gm, bm=grade.bm,
        rh=grade.rh, gh=grade.gh, bh=grade.bh,
    )


# ══════════════════════════════════════════════════════════════════════
# 4.  COMPOSITE FILTER CHAIN BUILDER
# ══════════════════════════════════════════════════════════════════════

def build_composite_filter(
    profile: VisualProfile,
    narration_duration: float,
    ass_path: str,
    font_path: str,
    width: int,
    height: int,
    *,
    watermark: bool = False,
    topic_label: str | None = None,
) -> str:
    """Build the complete FFmpeg -vf filter chain for the main composite.

    This replaces the hardcoded filter string in _composite_main_section()
    with a dynamic chain that adapts to the plan's visual profile.
    """
    font_escaped = font_path.replace("\\", "/").replace(":", "\\:")
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    bar_h = 4

    parts: list[str] = []

    # ── 1. Dark overlay (darkening via colorchannelmixer) ────────────
    darken = 1.0 - profile.dark_overlay_opacity
    parts.append(f"colorchannelmixer=rr={darken}:gg={darken}:bb={darken}")

    # ── 2. Color grading ─────────────────────────────────────────────
    grade_filter = profile.color_grade.to_filter()
    if grade_filter:
        parts.append(grade_filter)

    # ── 3. Film effects (vignette, grain) ────────────────────────────
    film_filter = profile.film_effects.to_filter(width, height)
    if film_filter:
        parts.append(film_filter)

    # ── 4. Fade in/out ───────────────────────────────────────────────
    if profile.transitions.enabled:
        fade_in = profile.transitions.fade_in_duration
        fade_out = profile.transitions.fade_out_duration
        fade_out_start = max(0, narration_duration - fade_out)
        parts.append(
            f"fade=t=in:st=0:d={fade_in:.2f},"
            f"fade=t=out:st={fade_out_start:.2f}:d={fade_out:.2f}"
        )

    # ── 5. ASS subtitles ─────────────────────────────────────────────
    parts.append(f"ass='{ass_escaped}'")

    # ── 6. Branding (TUBEVO) ─────────────────────────────────────────
    parts.append(
        f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize=24:"
        f"fontcolor=0x00D4AA@0.85:x=40:y=28"
    )

    # ── 7. Lower-third topic label (Pro/Agency) ─────────────────────
    if profile.lower_third_enabled and topic_label:
        # Appear at 2s, disappear at 6s — subtle animated lower-third
        safe_label = topic_label.replace("'", "").replace(":", "")[:60]
        parts.append(
            f"drawtext=fontfile='{font_escaped}':"
            f"text='{safe_label}':"
            f"fontsize=18:fontcolor=0x00D4AA@0.7:"
            f"x=40:y={height - 60}:"
            f"enable='between(t,2,6)':"
            f"alpha='if(lt(t,2.5),min((t-2)*2,1),if(gt(t,5.5),max(1-(t-5.5)*2,0),1))'"
        )

    # ── 8. Progress bar ──────────────────────────────────────────────
    parts.append(
        f"drawbox=x=0:y=ih-{bar_h}:"
        f"w='floor(iw*(t/{narration_duration:.2f}))':"
        f"h={bar_h}:color=0x00D4AA:t=fill"
    )

    # ── 9. Free-tier watermark ───────────────────────────────────────
    if watermark:
        parts.append(
            f"drawtext=fontfile='{font_escaped}':"
            f"text='Made with Tubevo':fontsize=20:"
            f"fontcolor=white@0.35:x=w-tw-20:y=h-th-20"
        )

    return ",".join(parts)


def build_title_card_filter(
    profile: VisualProfile,
    title: str,
    title_text_file: str,
    font_path: str,
    width: int,
    height: int,
    duration: float,
) -> str:
    """Build FFmpeg -vf filter for the title card.

    Adds text animation, accent line, and shimmer effects based on tier.
    """
    font_escaped = font_path.replace("\\", "/").replace(":", "\\:")
    title_file_escaped = title_text_file.replace("\\", "/").replace(":", "\\:")
    style = profile.title_style

    parts: list[str] = ["format=yuv420p"]

    # ── Shimmer effect (subtle animated noise overlay at low opacity) ─
    if style.shimmer:
        # Use geq to create a subtle moving gradient/shimmer
        parts.append(
            "noise=alls=3:allf=t"
        )

    # ── Brand name "TUBEVO" ──────────────────────────────────────────
    brand_y = "(h/2)-100"
    brand_filter = (
        f"drawtext=fontfile='{font_escaped}':text='TUBEVO':fontsize=26:"
        f"fontcolor=0x00D4AA:x=(w-text_w)/2:y={brand_y}"
    )
    if style.fade_in_text:
        # Fade text in: alpha ramps from 0 to 1 over fade duration
        brand_filter += (
            f":alpha='min(t/{style.text_fade_duration:.2f},1)'"
        )
    parts.append(brand_filter)

    # ── Accent line under brand ──────────────────────────────────────
    if style.accent_line:
        line_y = f"(h/2)-70"
        line_x = f"(w-{style.accent_line_width})/2"
        parts.append(
            f"drawbox=x={line_x}:y={line_y}:"
            f"w={style.accent_line_width}:h=2:"
            f"color=0x00D4AA:t=fill"
        )

    # ── Main title text ──────────────────────────────────────────────
    title_y = "(h/2)+10" if not style.show_subtitle else "(h/2)-10"
    title_filter = (
        f"drawtext=fontfile='{font_escaped}':"
        f"textfile='{title_file_escaped}':"
        f"fontsize=40:fontcolor=white:"
        f"x=(w-text_w)/2:y={title_y}:line_spacing=8"
    )
    if style.fade_in_text:
        # Title fades in slightly after brand (staggered)
        delay = style.text_fade_duration * 0.4
        fade_dur = style.text_fade_duration
        title_filter += (
            f":alpha='min(max(t-{delay:.2f},0)/{fade_dur:.2f},1)'"
        )
    parts.append(title_filter)

    # ── Subtitle text (Agency) ───────────────────────────────────────
    if style.show_subtitle and style.subtitle_text:
        sub_y = "(h/2)+70"
        sub_filter = (
            f"drawtext=fontfile='{font_escaped}':"
            f"text='{style.subtitle_text}':"
            f"fontsize=16:fontcolor=0x888888:"
            f"x=(w-text_w)/2:y={sub_y}"
        )
        if style.fade_in_text:
            delay = style.text_fade_duration * 0.7
            fade_dur = style.text_fade_duration
            sub_filter += (
                f":alpha='min(max(t-{delay:.2f},0)/{fade_dur:.2f},1)'"
            )
        parts.append(sub_filter)

    # ── Overall fade-in from black ───────────────────────────────────
    if style.fade_in_text:
        parts.append(f"fade=t=in:st=0:d={style.text_fade_duration:.2f}")

    return ",".join(parts)


def build_outro_card_filter(
    profile: VisualProfile,
    font_path: str,
    width: int,
    height: int,
    duration: float,
) -> str:
    """Build FFmpeg -vf filter for the outro card."""
    font_escaped = font_path.replace("\\", "/").replace(":", "\\:")
    style = profile.title_style

    parts: list[str] = ["format=yuv420p"]

    # Shimmer
    if style.shimmer:
        parts.append("noise=alls=3:allf=t")

    # "SUBSCRIBE FOR MORE"
    sub_size = 48
    sub_filter = (
        f"drawtext=fontfile='{font_escaped}':"
        f"text='SUBSCRIBE FOR MORE':fontsize={sub_size}:"
        f"fontcolor=0x00D4AA:x=(w-text_w)/2:y=(h/2)-60"
    )
    if style.fade_in_text:
        sub_filter += f":alpha='min(t/{style.text_fade_duration:.2f},1)'"
    parts.append(sub_filter)

    # "Like · Comment · Share"
    cta_filter = (
        f"drawtext=fontfile='{font_escaped}':"
        f"text='Like · Comment · Share':fontsize=28:"
        f"fontcolor=white:x=(w-text_w)/2:y=(h/2)+20"
    )
    if style.fade_in_text:
        delay = style.text_fade_duration * 0.3
        cta_filter += (
            f":alpha='min(max(t-{delay:.2f},0)/{style.text_fade_duration:.2f},1)'"
        )
    parts.append(cta_filter)

    # Accent line
    if style.accent_line:
        line_y = "(h/2)-20"
        line_x = f"(w-{style.accent_line_width})/2"
        parts.append(
            f"drawbox=x={line_x}:y={line_y}:"
            f"w={style.accent_line_width}:h=2:"
            f"color=0x00D4AA@0.5:t=fill"
        )

    # "TUBEVO" watermark
    parts.append(
        f"drawtext=fontfile='{font_escaped}':"
        f"text='TUBEVO':fontsize=20:"
        f"fontcolor=0x888888:x=(w-text_w)/2:y=(h/2)+80"
    )

    # Fade in from black + fade out to black
    if style.fade_in_text:
        fade_out_start = max(0, duration - 0.8)
        parts.append(
            f"fade=t=in:st=0:d={style.text_fade_duration:.2f},"
            f"fade=t=out:st={fade_out_start:.2f}:d=0.8"
        )

    return ",".join(parts)


# ══════════════════════════════════════════════════════════════════════
# 5.  HELPER: Decide Ken Burns direction per segment
# ══════════════════════════════════════════════════════════════════════

_KB_DIRECTIONS = [
    "center_zoom_in", "center_zoom_out",
    "left_to_right", "right_to_left",
    "top_to_bottom", "bottom_to_top",
]


def pick_ken_burns_direction(segment_index: int, seed: str = "") -> str:
    """Deterministically pick a Ken Burns direction for variety."""
    rng = random.Random(f"kb-{seed}-{segment_index}")
    return rng.choice(_KB_DIRECTIONS)
