"""
script_generator.py — Generate tight, punchy 3-minute video scripts
using the OpenAI Chat Completions API.

Usage:
    from script_generator import generate_script, generate_metadata

    script   = generate_script("5 Frugal Habits That Build Wealth Fast")
    metadata = generate_metadata(script, topic)
"""

from __future__ import annotations

import logging

from openai import OpenAI

import config

logger = logging.getLogger("tubevo.script_generator")

# ── OpenAI client (initialised once) ────────────────────────────────
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazy-init the OpenAI client so imports don't explode when the key
    isn't set yet (e.g. during tests)."""
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# ── Script generation ───────────────────────────────────────────────

def generate_script(
    topic: str,
    *,
    max_tokens: int = 1200,
    temperature: float | None = None,
    avoidance_prompt: str = "",
) -> str:
    """Return a ~3-minute video script for the given *topic*.

    The script follows the Tubevo style:
    • Hook (5-10 s)
    • 3–5 key points with actionable advice
    • Strong CTA close

    Phase 7 additions:
    - *temperature*: Override for OpenAI temperature (default 0.8).
      Use ``variation_engine.pick_script_temperature()`` for per-run jitter.
    - *avoidance_prompt*: Extra prompt fragment from content memory that
      tells the model to avoid previously-used angles/hooks.
    """
    system_prompt = (
        f"{config.CHANNEL_TONE}\n\n"
        "FORMAT RULES:\n"
        "- Write a script meant to be spoken aloud in roughly 3 minutes (~450 words).\n"
        "- Open with a punchy hook that grabs attention in the first 5 seconds.\n"
        "- Use short, powerful sentences. One idea per sentence.\n"
        "- Break the body into 3-5 numbered key points with concrete, actionable advice.\n"
        "- End with a strong call-to-action: like, subscribe, comment.\n"
        "- Do NOT include stage directions, camera cues, or timestamps.\n"
        "- Speak directly to 'you' — second person, conversational.\n"
    )

    # Phase 7: inject content-memory avoidance if present
    if avoidance_prompt:
        system_prompt += avoidance_prompt

    user_prompt = f"Write a video script on the following topic:\n\n{topic}"

    # Phase 7: use provided temperature or fall back to original 0.8
    effective_temp = temperature if temperature is not None else 0.8

    response = _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=effective_temp,
    )

    content = response.choices[0].message.content or ""
    logger.info("Script generated (temp=%.2f, avoidance=%d chars)", effective_temp, len(avoidance_prompt))
    return content.strip()


# ── Metadata generation (title / description / tags) ────────────────

def generate_metadata(
    script: str,
    topic: str,
    *,
    temperature: float | None = None,
    avoidance_prompt: str = "",
) -> dict:
    """Generate a YouTube title, SEO description, and tags from a
    finished script. Returns ``{"title": ..., "description": ..., "tags": [...]}``.

    Phase 7 additions:
    - *temperature*: Override for metadata temperature (default 0.6).
    - *avoidance_prompt*: Hints to avoid repeated title patterns.
    """
    system_prompt = (
        "You are an expert YouTube SEO strategist for a personal-finance channel.\n"
        "Given a video script and its topic, return ONLY valid JSON with these keys:\n"
        '  "title"       — catchy, < 70 chars, includes a power word\n'
        '  "description" — 2-3 short paragraphs with keywords, include a CTA and hashtags at the end\n'
        '  "tags"        — list of 8-12 relevant tags as strings\n'
        "Do NOT include markdown fences. Return raw JSON only."
    )

    # Phase 7: inject metadata avoidance if present
    if avoidance_prompt:
        system_prompt += avoidance_prompt

    user_prompt = (
        f"TOPIC: {topic}\n\n"
        f"SCRIPT:\n{script}"
    )

    # Phase 7: use provided temperature or fall back to original 0.6
    effective_temp = temperature if temperature is not None else 0.6

    response = _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=600,
        temperature=effective_temp,
    )

    import json

    raw = (response.choices[0].message.content or "").strip()
    # Strip markdown fences if the model wraps them anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    metadata: dict = json.loads(raw)

    # Merge default tags from config
    extra_tags = [t for t in config.DEFAULT_TAGS if t not in metadata.get("tags", [])]
    metadata["tags"] = metadata.get("tags", []) + extra_tags

    return metadata


# ── Quick CLI test ──────────────────────────────────────────────────
if __name__ == "__main__":
    import json as _json

    test_topic = "5 Frugal Habits That Build Wealth Fast"
    logger.info("Generating script …")
    s = generate_script(test_topic)
    print(s)
    logger.info("Generating metadata …")
    m = generate_metadata(s, test_topic)
    print(_json.dumps(m, indent=2))
