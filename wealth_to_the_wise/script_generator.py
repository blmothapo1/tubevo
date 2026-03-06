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
import time

from openai import OpenAI, RateLimitError, APIError, APIConnectionError, APITimeoutError, AuthenticationError

import config
from pipeline_errors import ApiQuotaError, ApiAuthError, ExternalServiceError

logger = logging.getLogger("tubevo.script_generator")

# ── Phase 8: Retry configuration ────────────────────────────────────
_MAX_RETRIES = 5
_BASE_DELAY = 2.0        # seconds — first retry waits ~2s
_MAX_DELAY = 60.0         # cap at 60s
_RETRIABLE_EXCEPTIONS = (RateLimitError, APIError, APIConnectionError, APITimeoutError)

# ── OpenAI client (initialised once) ────────────────────────────────
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazy-init the OpenAI client so imports don't explode when the key
    isn't set yet (e.g. during tests)."""
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise ApiAuthError(
                "OPENAI_API_KEY is not set. Add it to your .env file.",
                user_hint="Please add your OpenAI API key in Settings → API Keys.",
            )
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# ── Phase 8: Retry wrapper for OpenAI calls ─────────────────────────

def _call_openai_with_retry(*, model: str, messages: list, max_tokens: int, temperature: float, api_key: str | None = None) -> str:
    """Call OpenAI chat completions with exponential-backoff retry.

    Retries on RateLimitError, APIError, APIConnectionError, APITimeoutError.
    Non-retriable errors (auth, bad request) are raised immediately.

    If *api_key* is provided, a fresh client is created for this call
    (BYOK per-user key).  Otherwise the module-level client is used.
    """
    if api_key:
        client = OpenAI(api_key=api_key)
    else:
        client = _get_client()
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise ApiAuthError(
                f"OpenAI authentication failed: {config.mask_secrets(str(exc))}",
                user_hint="Your OpenAI API key is invalid or revoked. Please update it in Settings → API Keys.",
            ) from exc
        except _RETRIABLE_EXCEPTIONS as exc:
            last_exc = exc
            # For RateLimitError, check if it's a quota-exhausted error (non-retriable)
            if isinstance(exc, RateLimitError):
                err_msg = str(exc).lower()
                if "quota" in err_msg or "billing" in err_msg or "exceeded" in err_msg:
                    raise ApiQuotaError(
                        "OpenAI API quota exhausted. Please check your billing at "
                        "https://platform.openai.com/account/billing"
                    ) from exc

            delay = min(_BASE_DELAY * (2 ** (attempt - 1)), _MAX_DELAY)
            logger.warning(
                "OpenAI API error (attempt %d/%d): %s — retrying in %.1fs",
                attempt, _MAX_RETRIES, type(exc).__name__, delay,
            )
            time.sleep(delay)

    # All retries exhausted
    raise ExternalServiceError(
        f"OpenAI API call failed after {_MAX_RETRIES} retries: {config.mask_secrets(str(last_exc))}"
    ) from last_exc


# ── Niche-specific framing rules ─────────────────────────────────────

_NICHE_FRAMING: dict[str, str] = {
    "Personal Finance": (
        "Frame content with authority and credibility. Use real numbers, percentages, "
        "and specific dollar amounts. Reference well-known financial principles. "
        "Tone: trustworthy advisor who simplifies complex money concepts."
    ),
    "Investing / Stocks": (
        "Lead with data and market context. Use case studies, historical returns, "
        "and specific ticker examples. Tone: knowledgeable analyst breaking down "
        "opportunities for everyday investors."
    ),
    "Business & Entrepreneurship": (
        "Focus on actionable frameworks and real-world examples. Reference successful "
        "companies and founders. Tone: experienced mentor sharing battle-tested strategies."
    ),
    "Self-Improvement": (
        "Use psychological frameworks and research-backed insights. Open with "
        "identity-based hooks. Tone: empathetic coach who challenges the viewer."
    ),
    "Psychology": (
        "Lead with fascinating research and counterintuitive findings. Use the "
        "'study → insight → application' pattern. Tone: curious scientist sharing discoveries."
    ),
    "Productivity": (
        "Focus on systems over tips. Reference specific tools, time-blocking methods, "
        "and measurable outcomes. Tone: efficiency obsessive sharing proven workflows."
    ),
    "Tech & AI": (
        "Lead with what's new and why it matters NOW. Use demos, comparisons, and "
        "future implications. Tone: excited insider explaining cutting-edge tech clearly."
    ),
    "True Crime": (
        "Build suspense through chronological storytelling. Use sensory details and "
        "cliffhangers between points. Tone: investigative narrator pulling you deeper."
    ),
    "Horror Stories": (
        "Use atmospheric language and pacing. Build tension slowly, then release. "
        "Tone: campfire storyteller who knows exactly when to pause."
    ),
    "Mystery & Conspiracy": (
        "Present evidence systematically, building toward a revelation. Use rhetorical "
        "questions and 'what if' framing. Tone: investigator connecting hidden dots."
    ),
    "History": (
        "Anchor in a specific moment/event and expand outward. Use vivid details and "
        "little-known facts. Tone: passionate historian making the past feel alive."
    ),
    "Science & Space": (
        "Lead with awe and scale. Use analogies to make vast concepts relatable. "
        "Tone: enthusiastic educator bridging complex science and everyday wonder."
    ),
    "Fitness & Health": (
        "Lead with myth-busting or surprising research. Use specific protocols and "
        "measurable results. Tone: evidence-based coach cutting through fitness noise."
    ),
    "Luxury & Wealth": (
        "Use aspirational storytelling and exclusive details. Reference specific brands, "
        "price points, and lifestyle contrasts. Tone: insider revealing how the elite live."
    ),
    "Geography & World Facts": (
        "Open with a mind-blowing fact or comparison. Use visual language and scale. "
        "Tone: world traveler sharing things most people never learn."
    ),
}

_GOAL_MODIFIERS: dict[str, str] = {
    "growth": (
        "GOAL: CHANNEL GROWTH\n"
        "- Front-load the most shareable, curiosity-driven hook possible.\n"
        "- Optimise the first 30 seconds for maximum retention.\n"
        "- End with a specific comment prompt to boost engagement signals.\n"
        "- Use pattern interrupts every 40-50 seconds to maintain attention.\n"
    ),
    "monetization": (
        "GOAL: MONETIZATION\n"
        "- Naturally weave in value propositions and CTAs.\n"
        "- Structure content so viewers want 'the full story' (drives watch time).\n"
        "- End with a strong CTA for subscribing + notification bell.\n"
        "- Target 8+ minutes if the topic supports it (mid-roll eligibility).\n"
    ),
    "authority": (
        "GOAL: BUILD AUTHORITY\n"
        "- Lead with unique data, original analysis, or contrarian takes.\n"
        "- Reference specific sources, studies, or personal experience.\n"
        "- Use a measured, authoritative tone — fewer exclamation marks.\n"
        "- End with a thought-provoking question, not a generic CTA.\n"
    ),
    "entertainment": (
        "GOAL: ENTERTAINMENT\n"
        "- Prioritise pacing, surprise, and emotional variety.\n"
        "- Use story arcs with tension and release.\n"
        "- Include humour, unexpected pivots, and vivid language.\n"
        "- End with a cliffhanger or callback that makes viewers want more.\n"
    ),
}


# ── Hook intensity modes (driven by adaptive engine) ─────────────────

_HOOK_MODES: dict[str, str] = {
    "aggressive": (
        "HOOK INTENSITY: AGGRESSIVE\n"
        "The viewer is about to scroll away. You have 3 seconds.\n"
        "- Open with the most emotionally charged, pattern-breaking line possible.\n"
        "- Create an IMMEDIATE open loop in sentence 1 — not sentence 3.\n"
        "- Use a 'wait, what?' reaction trigger: a shocking stat, a bold contradiction, or a cliffhanger.\n"
        "- First pattern interrupt must come before the 30-second mark, not after.\n"
        "- Front-load the most valuable insight earlier in the script.\n"
    ),
    "balanced": (
        "HOOK INTENSITY: BALANCED\n"
        "- Open with a strong hook that creates curiosity without sensationalism.\n"
        "- The open loop should land within the first 2-3 sentences.\n"
        "- Pattern interrupt around the 45-second mark.\n"
    ),
    "conservative": (
        "HOOK INTENSITY: CONSERVATIVE (DEPTH MODE)\n"
        "Retention is already strong. Optimize for depth over shock.\n"
        "- Open with a thought-provoking observation or nuanced question.\n"
        "- Take slightly more time to set up context — viewers are staying.\n"
        "- Add an extra layer of analysis or a deeper example in the body.\n"
        "- Pattern interrupt can be more subtle — a perspective shift rather than a gimmick.\n"
    ),
}

# ── Title style instructions (driven by adaptive engine) ─────────────

_TITLE_STYLE_INSTRUCTIONS: dict[str, str] = {
    "curiosity": (
        "PREFERRED TITLE STYLE: CURIOSITY\n"
        "- Lead with an information gap the viewer MUST close.\n"
        "- Use 'The [X] that [surprising outcome]' or 'Why [counterintuitive claim]' patterns.\n"
        "- The title should make someone think 'Wait, really?' before clicking.\n"
    ),
    "direct_benefit": (
        "PREFERRED TITLE STYLE: DIRECT BENEFIT\n"
        "- State the concrete outcome the viewer will get.\n"
        "- Use 'How to [achieve X] in [timeframe]' or '[Action] to [benefit]' patterns.\n"
        "- The value proposition must be immediately clear from the title alone.\n"
    ),
    "contrarian": (
        "PREFERRED TITLE STYLE: CONTRARIAN\n"
        "- Challenge a widely-held belief or popular advice.\n"
        "- Use 'Stop [common action]' or '[Popular thing] Is Actually [opposite]' patterns.\n"
        "- The title should provoke disagreement that drives clicks.\n"
    ),
    "question": (
        "PREFERRED TITLE STYLE: QUESTION\n"
        "- Pose a specific question the viewer needs answered.\n"
        "- Use 'Is [specific thing] Worth It?' or 'What Happens When [scenario]?' patterns.\n"
        "- The question must feel personally relevant, not generic.\n"
    ),
    "data_driven": (
        "PREFERRED TITLE STYLE: DATA-DRIVEN\n"
        "- Lead with a specific number, percentage, or data point.\n"
        "- Use '[Specific number] [surprising thing]' or 'I Tested [X] for [time] — Here's What Happened' patterns.\n"
        "- The data point must be surprising or impressive enough to demand attention.\n"
    ),
}


def _build_dynamic_tone(user_preferences: dict | None) -> str:
    """Build a dynamic system prompt tone based on user preferences.

    Falls back to config.CHANNEL_TONE if no preferences are available.
    """
    if not user_preferences or not user_preferences.get("niches"):
        return config.CHANNEL_TONE

    niches = user_preferences.get("niches", [])
    tone_style = user_preferences.get("tone_style", "confident, direct, no-fluff educator")
    target_audience = user_preferences.get("target_audience", "general audience")
    channel_goal = user_preferences.get("channel_goal", "growth")

    # Build persona from user's tone + niches
    niche_label = ", ".join(niches[:3])
    persona = (
        f"You are 'Tubevo', a {tone_style} creating content about {niche_label}. "
        f"Your target audience is: {target_audience}. "
        "Every sentence earns its place. No fluff, no filler."
    )

    # Add niche-specific framing for the primary niche
    primary_niche = niches[0] if niches else ""
    niche_rules = _NICHE_FRAMING.get(primary_niche, "")
    if niche_rules:
        persona += f"\n\nNICHE FRAMING:\n{niche_rules}"

    # Add goal modifier
    goal_rules = _GOAL_MODIFIERS.get(channel_goal, _GOAL_MODIFIERS["growth"])
    persona += f"\n\n{goal_rules}"

    return persona


# ── Script generation ───────────────────────────────────────────────

def generate_script(
    topic: str,
    *,
    max_tokens: int = 1200,
    temperature: float | None = None,
    avoidance_prompt: str = "",
    user_preferences: dict | None = None,
    performance_profile: dict | None = None,
    api_key: str | None = None,
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

    Adaptive additions:
    - *performance_profile*: Dict from adaptive_engine with hook_mode,
      recommended_title_style, etc.
    """
    # Determine hook mode from adaptive profile
    hook_mode = "balanced"
    if performance_profile and performance_profile.get("adaptation_active"):
        hook_mode = performance_profile.get("hook_mode", "balanced")

    from datetime import datetime, timezone as _tz
    _today = datetime.now(_tz.utc).strftime("%B %d, %Y")

    system_prompt = (
        f"Today's date is {_today}. All references, examples, and statistics "
        f"MUST be relevant to {_today}. Never reference outdated events.\n\n"
        f"{_build_dynamic_tone(user_preferences)}\n\n"
        f"{_HOOK_MODES.get(hook_mode, _HOOK_MODES['balanced'])}\n"
        "SCRIPT STRUCTURE (follow this order exactly):\n\n"
        "1. HOOK (first 2-3 sentences, ~5-10 seconds):\n"
        "   - Open with ONE of these patterns (rotate — never repeat the same type twice in a row):\n"
        "     • Bold claim: a surprising statistic or counterintuitive statement\n"
        "     • Identity call-out: 'If you [specific behavior], this will change everything'\n"
        "     • Story open: 'Last year, I [brief anecdote setup]…'\n"
        "     • Myth bust: 'Everything you've been told about [topic] is wrong.'\n"
        "   - The hook must create an open loop — promise a payoff the viewer has to stay for.\n\n"
        "2. BODY (3-5 key points, ~2 minutes):\n"
        "   - Each point: bold claim → explanation → concrete example or action step.\n"
        "   - After the 2nd point, insert a PATTERN INTERRUPT: a quick rhetorical question,\n"
        "     a surprising pivot, or a 'here's where it gets interesting' transition.\n"
        "   - Use specific numbers, names, and examples — never vague advice.\n\n"
        "3. CLOSE (last 15-20 seconds):\n"
        "   - Callback to the hook (close the open loop).\n"
        "   - One clear, specific CTA: like, subscribe, or comment with a specific prompt.\n\n"
        "FORMAT RULES:\n"
        "- Total length: ~450 words (3 minutes spoken).\n"
        "- Short, powerful sentences. One idea per sentence.\n"
        "- Speak directly to 'you' — second person, conversational.\n"
        "- Do NOT use 'Top N' or 'X Ways' framing unless the topic explicitly demands it.\n"
        "  Prefer narrative, problem-solution, or myth-busting structures instead.\n"
        "- Do NOT include stage directions, camera cues, timestamps, or section headers.\n"
        "- Do NOT start with 'Hey guys' or 'What's up everyone'.\n"
        "\n"
        "DIFFERENTIATION RULES:\n"
        "- Never produce a script that sounds like it could come from any other channel.\n"
        "- Inject at least one unique perspective, analogy, or framing per video.\n"
        "- Avoid cliché YouTube opener patterns. Earn attention in the first 3 seconds.\n"
        "- If this topic has been covered by 100 other creators, find the angle they ALL missed.\n"
    )

    # Phase 7: inject content-memory avoidance if present
    if avoidance_prompt:
        system_prompt += avoidance_prompt

    user_prompt = f"Write a video script on the following topic:\n\n{topic}"

    # Phase 7: use provided temperature or fall back to original 0.8
    effective_temp = temperature if temperature is not None else 0.8

    # Phase 8: use retry wrapper instead of bare API call
    content = _call_openai_with_retry(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=effective_temp,
        api_key=api_key,
    )

    logger.info("Script generated (temp=%.2f, avoidance=%d chars)", effective_temp, len(avoidance_prompt))
    return content.strip()


# ── Metadata generation (title / description / tags) ────────────────

def generate_metadata(
    script: str,
    topic: str,
    *,
    temperature: float | None = None,
    avoidance_prompt: str = "",
    user_preferences: dict | None = None,
    performance_profile: dict | None = None,
    api_key: str | None = None,
) -> dict:
    """Generate a YouTube title, SEO description, and tags from a
    finished script. Returns ``{"title": ..., "description": ..., "tags": [...]}``.

    Phase 7 additions:
    - *temperature*: Override for metadata temperature (default 0.6).
    - *avoidance_prompt*: Hints to avoid repeated title patterns.
    - *user_preferences*: Dynamic niche/tone for channel-aware metadata.

    Adaptive additions:
    - *performance_profile*: Dict from adaptive_engine with title style guidance.
    """
    # Build niche-aware metadata prompt
    niche_context = ""
    if user_preferences and user_preferences.get("niches"):
        niche_label = ", ".join(user_preferences["niches"][:3])
        niche_context = f"This channel covers: {niche_label}. "

    # Adaptive title style guidance
    title_style_guidance = ""
    if performance_profile and performance_profile.get("adaptation_active"):
        rec_style = performance_profile.get("recommended_title_style", "")
        if rec_style and rec_style in _TITLE_STYLE_INSTRUCTIONS:
            title_style_guidance = "\n" + _TITLE_STYLE_INSTRUCTIONS[rec_style] + "\n"

    from datetime import datetime, timezone as _tz
    _today_meta = datetime.now(_tz.utc).strftime("%B %d, %Y")

    system_prompt = (
        f"You are an expert YouTube SEO strategist. Today's date is {_today_meta}. {niche_context}\n"
        "Given a video script and its topic, return ONLY valid JSON with these keys:\n"
        '  "title"            — catchy, < 70 chars, includes a power word\n'
        '  "title_alternatives" — array of 2 alternative title options (different angles/structures)\n'
        '  "title_style"      — the style category of the primary title: one of "curiosity", "direct_benefit", "contrarian", "question", "data_driven"\n'
        '  "description"      — 2-3 short paragraphs with keywords, include a CTA and hashtags at the end\n'
        '  "tags"             — list of 8-12 relevant tags as strings\n\n'
        f"{title_style_guidance}"
        "TITLE RULES:\n"
        "- Do NOT use generic 'Top N' / 'X Ways' / 'X Things' framing for every video.\n"
        "- Mix structures: questions, bold claims, how-to, myth busts, story hooks.\n"
        "- Each of the 3 titles (title + 2 alternatives) must use a DIFFERENT structure.\n"
        "- Never start with a number unless it adds genuine value.\n"
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

    # Phase 8: use retry wrapper instead of bare API call
    raw = _call_openai_with_retry(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=600,
        temperature=effective_temp,
        api_key=api_key,
    ).strip()

    import json

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
