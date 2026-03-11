# filepath: backend/utils.py
"""
Shared utilities and constants for the backend package.

Provides safe wrappers around functions that live in the top-level
pipeline modules so that ``backend/`` code never needs a fragile
``sys.path`` hack or bare ``from config import …`` call.

Also contains canonical constants (like plan limits) so they live in
one place and every module can import from here without circular-dependency
risk.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ── Plan-based monthly video limits (single source of truth) ─────────
# Every module that needs these should ``from backend.utils import PLAN_MONTHLY_LIMITS``.
PLAN_MONTHLY_LIMITS: dict[str, int] = {
    "free": 1,
    "starter": 10,
    "pro": 50,
    "agency": 999_999,   # effectively unlimited
}

# ── Plan-based team seat limits (Phase 4) ────────────────────────────
PLAN_TEAM_SEAT_LIMITS: dict[str, int] = {
    "free": 0,         # no team feature
    "starter": 3,
    "pro": 10,
    "agency": 25,
}

# ── Plan-based max teams per user (Phase 4) ──────────────────────────
PLAN_MAX_TEAMS: dict[str, int] = {
    "free": 0,
    "starter": 1,
    "pro": 3,
    "agency": 10,
}

# ── Referral system constants (Phase 5) ──────────────────────────────
REFERRAL_COMMISSION_PCT = 20          # 20% recurring commission
REFERRAL_COMMISSION_MONTHS = 12       # pay commissions for first 12 months
PLAN_MONTHLY_PRICE_CENTS: dict[str, int] = {
    "free": 0,
    "starter": 2900,    # $29/mo
    "pro": 7900,         # $79/mo
    "agency": 19900,     # $199/mo
}


# ── Plan-based quality profiles (single source of truth) ─────────────
# Each tier gets progressively better AI models, voice quality, video
# resolution, and more creative control.  This ensures a free user
# and a $199/mo Agency user have noticeably different output quality.
#
# Fields:
#   gpt_model           — OpenAI model for script & metadata generation
#   max_script_tokens   — Max tokens for script generation (longer = more detailed)
#   voice_model         — ElevenLabs TTS model
#   video_resolution    — (width, height) tuple
#   video_fps           — Frames per second
#   video_crf           — FFmpeg CRF (lower = higher quality, bigger file)
#   audio_bitrate       — AAC audio bitrate
#   video_bitrate       — Max video bitrate cap
#   target_scenes       — Number of scene plan segments (more = richer visuals)
#   subtitle_style      — Default subtitle style
#   watermark           — Whether to burn a "Made with Tubevo" watermark
#   multi_format        — Whether portrait/square exports are available
#   bulk_generate       — Whether bulk generation is available

PLAN_QUALITY_PROFILES: dict[str, dict] = {
    "free": {
        "gpt_model": "gpt-4o-mini",
        "max_script_tokens": 800,
        "voice_model": "eleven_multilingual_v2",
        "video_resolution": (1280, 720),
        "video_fps": 24,
        "video_crf": "26",
        "audio_bitrate": "96k",
        "video_bitrate": "2500k",
        "target_scenes": 6,
        "subtitle_style": "default",
        "watermark": True,
        "multi_format": False,
        "bulk_generate": False,
        "visual_tier": "free",
        "ai_illustrations": False,      # stock footage only
        "ai_image_quality": "standard",
    },
    "starter": {
        "gpt_model": "gpt-4o",
        "max_script_tokens": 1200,
        "voice_model": "eleven_multilingual_v2",
        "video_resolution": (1920, 1080),
        "video_fps": 30,
        "video_crf": "22",
        "audio_bitrate": "128k",
        "video_bitrate": "4000k",
        "target_scenes": 10,
        "subtitle_style": "bold_pop",
        "watermark": False,
        "multi_format": False,
        "bulk_generate": False,
        "visual_tier": "starter",
        "ai_illustrations": False,      # stock footage only
        "ai_image_quality": "standard",
    },
    "pro": {
        "gpt_model": "gpt-4o",
        "max_script_tokens": 1500,
        "voice_model": "eleven_multilingual_v2",
        "video_resolution": (1920, 1080),
        "video_fps": 30,
        "video_crf": "20",
        "audio_bitrate": "192k",
        "video_bitrate": "5000k",
        "target_scenes": 14,
        "subtitle_style": "bold_pop",
        "watermark": False,
        "multi_format": True,
        "bulk_generate": False,
        "visual_tier": "pro",
        "ai_illustrations": True,       # ✨ AI-generated scene art
        "ai_image_quality": "standard",  # $0.04/image × 14 ≈ $0.56/video
    },
    "agency": {
        "gpt_model": "gpt-4o",
        "max_script_tokens": 2000,
        "voice_model": "eleven_multilingual_v2",
        "video_resolution": (1920, 1080),
        "video_fps": 30,
        "video_crf": "18",
        "audio_bitrate": "192k",
        "video_bitrate": "6000k",
        "target_scenes": 18,
        "subtitle_style": "bold_pop",
        "watermark": False,
        "multi_format": True,
        "bulk_generate": True,
        "visual_tier": "agency",
        "ai_illustrations": True,       # ✨ AI-generated scene art
        "ai_image_quality": "hd",        # $0.08/image × 18 ≈ $1.44/video (HD quality)
    },
}


def get_quality_profile(plan: str) -> dict:
    """Return the quality profile for a given plan, defaulting to 'free'."""
    return PLAN_QUALITY_PROFILES.get(plan, PLAN_QUALITY_PROFILES["free"])


# ── API-key masking ──────────────────────────────────────────────────
# We try to import the canonical ``mask_secrets`` from the top-level
# ``config.py``.  If the import fails (e.g. in tests that don't have
# the project root on sys.path), we fall back to a lightweight local
# implementation so the error-handling path never crashes itself.

_mask_fn = None  # type: ignore[assignment]

try:
    _project_root = str(Path(__file__).resolve().parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from config import mask_secrets as _config_mask
    _mask_fn = _config_mask
except Exception:
    pass


# Lightweight fallback regex — covers the most common key prefixes.
_FALLBACK_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|sk-proj-[A-Za-z0-9_-]{10,}|xi-[A-Za-z0-9_-]{10,}|AIza[A-Za-z0-9_-]{30,})"
)


def mask_secrets(text: str) -> str:
    """Redact known API-key patterns from *text*.

    Delegates to the top-level ``config.mask_secrets`` if available,
    otherwise falls back to a simple regex substitution.
    """
    if not text:
        return text
    if _mask_fn is not None:
        return _mask_fn(text)

    def _redact(m: re.Match) -> str:
        v = m.group(0)
        return v[:6] + "***" if len(v) > 6 else v[:2] + "***"

    return _FALLBACK_PATTERN.sub(_redact, text)
