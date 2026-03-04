"""
voiceover.py — Generate voiceover audio from a script using ElevenLabs TTS.

Usage:
    from voiceover import generate_voiceover

    audio_path = generate_voiceover("Your script text here...")
    # → "output/voiceover.mp3"

Setup:
    1. Get an API key from https://elevenlabs.io
    2. Add to your .env:  ELEVENLABS_API_KEY=your-key-here
    3. Optionally set ELEVENLABS_VOICE_ID for a specific voice.
"""

from __future__ import annotations

import logging
import os
import time
import requests
from pathlib import Path

import config
from pipeline_errors import ApiQuotaError, ApiAuthError, ExternalServiceError

logger = logging.getLogger("tubevo.voiceover")

# ── Defaults ─────────────────────────────────────────────────────────
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# Voice ID for ElevenLabs TTS. Set via .env: ELEVENLABS_VOICE_ID=your-voice-id
# Fallback: ElevenLabs "Adam" voice — a clear, professional male narrator.
_FALLBACK_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "") or _FALLBACK_VOICE_ID
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Phase 8: Retry configuration ────────────────────────────────────
_MAX_RETRIES = 5
_BASE_DELAY = 3.0        # seconds — first retry waits ~3s
_MAX_DELAY = 60.0         # cap at 60s
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def generate_voiceover(
    script: str,
    *,
    output_path: str | None = None,
    voice_id: str | None = None,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.4,
    speed: float | None = None,
    api_key: str | None = None,
) -> str:
    """Convert *script* text to speech via ElevenLabs and save as MP3.

    Parameters
    ----------
    speed : float | None
        Speech speed multiplier (0.7–1.2). None = ElevenLabs default (~1.0).
        Useful for pacing narration: 0.85 for slow/cinematic, 1.1 for punchy.
    api_key : str | None
        ElevenLabs API key. When provided, this key is used instead of the
        module-level ELEVENLABS_API_KEY — safe for concurrent per-user calls.

    Returns the path to the saved audio file.
    """
    effective_key = api_key or ELEVENLABS_API_KEY
    if not effective_key:
        raise ApiAuthError(
            "ELEVENLABS_API_KEY is not set. Add it to your .env file.\n"
            "Get a key at https://elevenlabs.io",
            user_hint="Please add your ElevenLabs API key in Settings → API Keys.",
        )

    voice_id = voice_id or DEFAULT_VOICE_ID or _FALLBACK_VOICE_ID
    output_path = output_path or str(OUTPUT_DIR / "voiceover.mp3")

    url = f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": effective_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": script,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True,
        },
    }

    # ── Phase 4: Speech speed adjustment ─────────────────────────
    # ElevenLabs v1 API accepts an optional top-level "speed" field
    # (float, 0.7–1.2). Only include it when explicitly set so that
    # older API tiers that don't support it aren't affected.
    if speed is not None:
        clamped = max(0.7, min(1.2, float(speed)))
        payload["speed"] = clamped
        logger.info("Speech speed set to %.2f", clamped)

    logger.info("Generating voiceover (%d chars) …", len(script))

    # ── Phase 8: Retry loop with exponential backoff ─────────────
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=120)

            if response.status_code == 200:
                # Success — write file and return
                with open(output_path, "wb") as f:
                    f.write(response.content)
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info("Voiceover saved → %s  (%.1f MB)", output_path, size_mb)
                return output_path

            # Check if this is a retriable status code
            if response.status_code in _RETRIABLE_STATUS_CODES:
                # For 429, check if it's a hard quota limit vs. transient rate limit
                if response.status_code == 429:
                    err_body = response.text.lower()
                    if any(kw in err_body for kw in ("quota", "limit exceeded", "characters", "credits")):
                        raise ApiQuotaError(
                            "ElevenLabs quota exhausted. Your plan's character or "
                            "credit limit has been reached. Check your usage at "
                            "https://elevenlabs.io/subscription"
                        )

                delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
                logger.warning(
                    "ElevenLabs API error %d (attempt %d/%d) — retrying in %.1fs",
                    response.status_code, attempt, _MAX_RETRIES, delay,
                )
                last_exc = RuntimeError(
                    f"ElevenLabs API error {response.status_code}: "
                    f"{config.mask_secrets(response.text[:500])}"
                )
                time.sleep(delay)
                continue

            # Non-retriable HTTP error — fail immediately with masked message
            error_text = config.mask_secrets(response.text[:500])
            if response.status_code in (401, 403):
                raise ApiAuthError(
                    f"ElevenLabs API auth error {response.status_code}: {error_text}",
                    user_hint="Your ElevenLabs API key appears invalid. Please update it in Settings → API Keys.",
                )
            raise ExternalServiceError(
                f"ElevenLabs API error {response.status_code}: {error_text}"
            )

        except requests.exceptions.RequestException as exc:
            # Network-level errors (timeout, connection reset, DNS failure)
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                break
            delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
            logger.warning(
                "ElevenLabs network error (attempt %d/%d): %s — retrying in %.1fs",
                attempt, _MAX_RETRIES, type(exc).__name__, delay,
            )
            time.sleep(delay)

    # All retries exhausted
    raise ExternalServiceError(
        f"ElevenLabs API call failed after {_MAX_RETRIES} retries: "
        f"{config.mask_secrets(str(last_exc))}"
    ) from last_exc


def list_voices() -> list[dict]:
    """List available ElevenLabs voices (useful for picking a voice_id)."""
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set.")

    resp = requests.get(
        f"{ELEVENLABS_API_URL}/voices",
        headers={"xi-api-key": ELEVENLABS_API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    voices = resp.json().get("voices", [])
    return [{"name": v["name"], "voice_id": v["voice_id"]} for v in voices]


# ── CLI test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_script = (
        "Want to build wealth fast? Stop wasting money. "
        "Start being frugal. Here are five habits that will change your life."
    )
    path = generate_voiceover(test_script)
    logger.info("Done: %s", path)
