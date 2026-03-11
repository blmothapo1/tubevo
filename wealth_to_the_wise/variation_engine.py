"""
variation_engine.py — Smart Variation System (Phase 7)

Prevents AI fatigue by introducing controlled randomness across the
entire pipeline so that consecutive videos on similar topics don't
feel templated or repetitive.

Components:
  1. Prompt temperature variability — vary OpenAI temperature per generation
  2. Voice tone variation         — jitter ElevenLabs stability/similarity/style
  3. Music mood rotation          — rotate key/chord/mood of ambient pads
  4. Content memory               — remember past topics to avoid repeated angles

100 % additive — every function returns safe defaults if anything fails.
All callers use fallback paths, so the existing pipeline is never broken.

Usage:
    from variation_engine import (
        pick_script_temperature,
        pick_voice_params,
        pick_music_mood,
        build_avoidance_prompt,
        compute_topic_fingerprint,
    )
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field

logger = logging.getLogger("tubevo.variation_engine")


# ═══════════════════════════════════════════════════════════════════════
# 1.  PROMPT TEMPERATURE VARIABILITY
# ═══════════════════════════════════════════════════════════════════════

# Range of acceptable temperatures for script generation.
# Lower → more predictable / safe; Higher → more creative / surprising.
_SCRIPT_TEMP_MIN = 0.65
_SCRIPT_TEMP_MAX = 0.95
_SCRIPT_TEMP_DEFAULT = 0.8

# Metadata generation stays lower to keep JSON output reliable.
_META_TEMP_MIN = 0.45
_META_TEMP_MAX = 0.70
_META_TEMP_DEFAULT = 0.6


def pick_script_temperature(*, topic: str = "", seed: str | None = None) -> float:
    """Return a slightly randomised temperature for script generation.

    The temperature is seeded by the topic + current time so that:
    - The same topic at different times gets different temps
    - Two topics at the same time get different temps
    - The range stays within safe creative bounds (0.65–0.95)

    Falls back to 0.8 if anything goes wrong.
    """
    try:
        seed_str = seed or f"{topic}-{time.time()}-{random.random()}"
        rng = random.Random(seed_str)
        temp = round(rng.uniform(_SCRIPT_TEMP_MIN, _SCRIPT_TEMP_MAX), 2)
        logger.info("Variation: script temperature = %.2f (seed=%s…)", temp, seed_str[:30])
        return temp
    except Exception:
        return _SCRIPT_TEMP_DEFAULT


def pick_metadata_temperature(*, topic: str = "", seed: str | None = None) -> float:
    """Return a slightly randomised temperature for metadata generation."""
    try:
        seed_str = seed or f"meta-{topic}-{time.time()}"
        rng = random.Random(seed_str)
        temp = round(rng.uniform(_META_TEMP_MIN, _META_TEMP_MAX), 2)
        logger.info("Variation: metadata temperature = %.2f", temp)
        return temp
    except Exception:
        return _META_TEMP_DEFAULT


# ═══════════════════════════════════════════════════════════════════════
# 2.  VOICE TONE VARIATION
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class VoiceParams:
    """ElevenLabs voice settings with controlled jitter."""
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.4


# Bounds for each parameter — small jitter to keep voice recognisable
_VOICE_RANGES = {
    "stability":        (0.35, 0.65),   # default 0.5  ± 0.15
    "similarity_boost": (0.65, 0.85),   # default 0.75 ± 0.10
    "style":            (0.25, 0.55),   # default 0.4  ± 0.15
}

# Named tone presets that add flavour descriptions (purely for logging)
_TONE_PRESETS = [
    "authoritative",   # slightly lower stability → more natural
    "warm",            # higher similarity → closer to base voice, higher style
    "energetic",       # lower stability, higher style → expressive
    "calm",            # higher stability, lower style → steady
    "conversational",  # mid-range everything with slight expressiveness
]


def pick_voice_params(*, topic: str = "", seed: str | None = None) -> VoiceParams:
    """Return slightly jittered ElevenLabs voice parameters.

    Keeps the voice recognisable while preventing the same flat delivery
    across every single video.

    Returns a VoiceParams dataclass with stability, similarity_boost, style.
    Falls back to defaults (0.5, 0.75, 0.4) if anything goes wrong.
    """
    try:
        seed_str = seed or f"voice-{topic}-{time.time()}"
        rng = random.Random(seed_str)

        stability = round(rng.uniform(*_VOICE_RANGES["stability"]), 3)
        similarity = round(rng.uniform(*_VOICE_RANGES["similarity_boost"]), 3)
        style = round(rng.uniform(*_VOICE_RANGES["style"]), 3)

        tone = rng.choice(_TONE_PRESETS)
        logger.info(
            "Variation: voice tone=%s  stability=%.3f  similarity=%.3f  style=%.3f",
            tone, stability, similarity, style,
        )

        return VoiceParams(
            stability=stability,
            similarity_boost=similarity,
            style=style,
        )
    except Exception:
        return VoiceParams()


# ═══════════════════════════════════════════════════════════════════════
# 3.  MUSIC MOOD / KEY ROTATION
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MusicMood:
    """A musical mood consisting of 4 sine-wave frequencies and a label."""
    label: str
    frequencies: list[float] = field(default_factory=list)  # 4 frequencies
    tremolo_base: float = 0.12  # base tremolo speed (FFmpeg min = 0.1)


# Chord voicings (root, 3rd, 5th, octave) — all in the 100-300 Hz range
# for a warm, non-distracting ambient pad.
MUSIC_MOODS: list[MusicMood] = [
    MusicMood(
        label="C major (warm)",
        frequencies=[130.81, 164.81, 196.00, 261.63],
        tremolo_base=0.12,
    ),
    MusicMood(
        label="A minor (reflective)",
        frequencies=[110.00, 130.81, 164.81, 220.00],
        tremolo_base=0.10,
    ),
    MusicMood(
        label="G major (uplifting)",
        frequencies=[98.00, 123.47, 146.83, 196.00],
        tremolo_base=0.14,
    ),
    MusicMood(
        label="E minor (contemplative)",
        frequencies=[82.41, 98.00, 123.47, 164.81],
        tremolo_base=0.11,
    ),
    MusicMood(
        label="D major (confident)",
        frequencies=[146.83, 185.00, 220.00, 293.66],
        tremolo_base=0.13,
    ),
    MusicMood(
        label="F major (peaceful)",
        frequencies=[87.31, 110.00, 130.81, 174.61],
        tremolo_base=0.10,
    ),
    MusicMood(
        label="Bb major (mellow)",
        frequencies=[116.54, 146.83, 174.61, 233.08],
        tremolo_base=0.11,
    ),
    MusicMood(
        label="C# minor (mysterious)",
        frequencies=[138.59, 164.81, 207.65, 277.18],
        tremolo_base=0.10,
    ),
]

# The original C-major mood index (index 0) is the safe fallback.
_DEFAULT_MOOD = MUSIC_MOODS[0]


def pick_music_mood(*, topic: str = "", seed: str | None = None) -> MusicMood:
    """Pick a music mood/key for this generation.

    Rotates through all available moods so consecutive videos get
    different ambient backgrounds.  Falls back to C-major if anything fails.
    """
    try:
        seed_str = seed or f"music-{topic}-{time.time()}"
        rng = random.Random(seed_str)
        mood = rng.choice(MUSIC_MOODS)
        logger.info("Variation: music mood = %s", mood.label)
        return mood
    except Exception:
        return _DEFAULT_MOOD


# ═══════════════════════════════════════════════════════════════════════
# 4.  CONTENT MEMORY — topic fingerprints + avoidance prompts
# ═══════════════════════════════════════════════════════════════════════

def compute_topic_fingerprint(topic: str) -> str:
    """Create a short, stable fingerprint of a topic for deduplication.

    Normalises whitespace and case so "5 Frugal Habits" and
    "5 frugal habits" produce the same fingerprint.
    """
    normalised = " ".join(topic.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


def build_avoidance_prompt(past_titles: list[str], *, max_titles: int = 10) -> str:
    """Build an additive prompt fragment that tells the AI to avoid
    rehashing angles/structures already used in previous videos.

    Returns an empty string if there's no history (safe no-op).
    """
    if not past_titles:
        return ""

    # Take the most recent N titles
    recent = past_titles[-max_titles:]

    lines = [
        "\n\nIMPORTANT — AVOID REPETITION:",
        "The following titles/topics have already been covered on this channel.",
        "Do NOT reuse the same hooks, structures, numbered lists, or angles.",
        "Find a FRESH perspective, a different opening, and unique examples.",
        "",
    ]
    for i, title in enumerate(recent, 1):
        lines.append(f"  {i}. {title}")

    lines.append("")
    lines.append("Be creative. Surprise the viewer with something they haven't heard before.")

    return "\n".join(lines)


def build_metadata_avoidance(past_titles: list[str], *, max_titles: int = 10) -> str:
    """Build avoidance hints for metadata generation so titles don't repeat patterns."""
    if not past_titles:
        return ""

    recent = past_titles[-max_titles:]
    lines = [
        "\n\nAVOID these title patterns (already used):",
    ]
    for t in recent:
        lines.append(f'  - "{t}"')
    lines.append("Create a title that feels COMPLETELY different from the above.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 5.  VISUAL STYLE SEEDING (helper for scene_planner)
# ═══════════════════════════════════════════════════════════════════════

def generate_style_seed(topic: str) -> str:
    """Generate a time-based style seed so the same topic gets different
    visual styles on each generation."""
    return hashlib.md5(
        f"{topic}-{time.time()}-{random.randint(0, 99999)}".encode()
    ).hexdigest()


# ═══════════════════════════════════════════════════════════════════════
# 6.  UNIFIED VARIATION CONTEXT
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class VariationContext:
    """All variation parameters for a single pipeline run, bundled together."""
    script_temperature: float = _SCRIPT_TEMP_DEFAULT
    metadata_temperature: float = _META_TEMP_DEFAULT
    voice_params: VoiceParams = field(default_factory=VoiceParams)
    music_mood: MusicMood = field(default_factory=lambda: _DEFAULT_MOOD)
    style_seed: str = ""
    avoidance_prompt: str = ""
    metadata_avoidance: str = ""
    topic_fingerprint: str = ""


def create_variation_context(
    topic: str,
    *,
    past_titles: list[str] | None = None,
) -> VariationContext:
    """One-shot helper that builds the full variation context for a pipeline run.

    This is the main entry point for the variation system — call it once
    at the start of each pipeline run and thread the result through.
    """
    past = past_titles or []

    ctx = VariationContext(
        script_temperature=pick_script_temperature(topic=topic),
        metadata_temperature=pick_metadata_temperature(topic=topic),
        voice_params=pick_voice_params(topic=topic),
        music_mood=pick_music_mood(topic=topic),
        style_seed=generate_style_seed(topic),
        avoidance_prompt=build_avoidance_prompt(past),
        metadata_avoidance=build_metadata_avoidance(past),
        topic_fingerprint=compute_topic_fingerprint(topic),
    )

    logger.info(
        "Variation context created: temp=%.2f/%.2f  voice=%.2f/%.2f/%.2f  "
        "music=%s  fingerprint=%s  past_titles=%d",
        ctx.script_temperature, ctx.metadata_temperature,
        ctx.voice_params.stability, ctx.voice_params.similarity_boost,
        ctx.voice_params.style,
        ctx.music_mood.label, ctx.topic_fingerprint, len(past),
    )

    return ctx
