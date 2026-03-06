# filepath: backend/services/niche_service.py
"""
Niche Intelligence service (Feature 2).

Uses OpenAI GPT to analyse a YouTube niche and produce:
  - A ``NicheSnapshot`` with saturation / trending / search volume scores
  - A list of ``NicheTopic`` suggestions ranked by estimated demand

This module is intentionally **synchronous** (httpx calls are sync)
because it may be run from both async endpoints and background workers.
The caller wraps it in ``asyncio.to_thread()`` when needed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("tubevo.backend.niche_service")

# ── Prompt engineering ───────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a YouTube market-research analyst specialising in niche evaluation.
Today's date is {today}. All analysis MUST reflect current {today} market conditions — \
never reference outdated data from previous years.

Given a niche name and LIVE MARKET DATA, you MUST return a JSON object \
(no markdown, no code fences) with:

{{
  "saturation_score": <int 1-100, higher = more saturated>,
  "trending_score": <int 1-100, higher = more trending right now>,
  "search_volume_est": <int, rough monthly YouTube search volume estimate>,
  "competitor_count": <int, estimated number of active channels in this niche>,
  "topics": [
    {{
      "topic": "<specific video title idea>",
      "estimated_demand": <int 1-10, higher = more demand>,
      "competition_level": "<low|medium|high>",
      "source": "gpt_analysis"
    }}
  ]
}}

Return EXACTLY 8-12 topic suggestions. Be specific with titles — not generic.
Ground your analysis in the live market data provided.
Return ONLY the JSON object, nothing else.
"""


def _build_user_prompt(niche: str, tone_style: str, target_audience: str, live_context: str = "") -> str:
    return (
        f"Niche: {niche}\n"
        f"Channel tone: {tone_style}\n"
        f"Target audience: {target_audience}\n"
        f"{live_context}\n\n"
        f"Analyse this niche and return the JSON object."
    )


# ── Core analysis function ───────────────────────────────────────────

def analyse_niche(
    *,
    niche: str,
    openai_api_key: str,
    tone_style: str = "confident, direct, no-fluff educator",
    target_audience: str = "general audience",
    model: str = "gpt-4o-mini",
    serpapi_key: str = "",
) -> dict:
    """Call OpenAI to produce a niche analysis.

    When ``serpapi_key`` is provided, fetches live data from Google Trends,
    YouTube, and Google News to ground the analysis in current reality.

    Returns a dict with keys:
      saturation_score, trending_score, search_volume_est,
      competitor_count, topics (list of dicts)

    Raises ``ValueError`` if the response cannot be parsed.
    """
    from backend.services.web_trends_service import fetch_live_trend_context

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # Fetch live web data for grounding
    live_context = fetch_live_trend_context(niche=niche, serpapi_key=serpapi_key)

    user_prompt = _build_user_prompt(niche, tone_style, target_audience, live_context)

    # Format system prompt with today's date
    system_prompt = _SYSTEM_PROMPT.format(today=today)

    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.7,
            "max_tokens": 2000,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60.0,
    )

    if resp.status_code != 200:
        logger.error("OpenAI niche analysis failed: %d %s", resp.status_code, resp.text[:300])
        raise ValueError(f"OpenAI API error: {resp.status_code}")

    raw_content = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip code fences if the model wraps them anyway
    if raw_content.startswith("```"):
        raw_content = raw_content.split("\n", 1)[-1]
    if raw_content.endswith("```"):
        raw_content = raw_content.rsplit("```", 1)[0]
    raw_content = raw_content.strip()

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse niche analysis JSON: %s", raw_content[:300])
        raise ValueError(f"Invalid JSON from OpenAI: {exc}") from exc

    # Validate required fields
    required = ("saturation_score", "trending_score", "search_volume_est", "competitor_count", "topics")
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required field in niche analysis: {key}")

    if not isinstance(data["topics"], list) or len(data["topics"]) == 0:
        raise ValueError("Niche analysis returned no topics")

    return data


# ── Persistence helpers (called from router / worker) ────────────────

async def save_niche_snapshot(
    *,
    channel_id: str,
    niche: str,
    analysis: dict,
    db_session,
) -> tuple:
    """Persist a NicheSnapshot + NicheTopics to the database.

    Returns ``(snapshot, topics_list)`` ORM objects.
    """
    from backend.models import NicheSnapshot, NicheTopic, _new_uuid, _utcnow

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    snapshot = NicheSnapshot(
        id=_new_uuid(),
        channel_id=channel_id,
        niche=niche,
        snapshot_date=today,
        saturation_score=int(analysis.get("saturation_score", 0)),
        trending_score=int(analysis.get("trending_score", 0)),
        search_volume_est=int(analysis.get("search_volume_est", 0)),
        competitor_count=int(analysis.get("competitor_count", 0)),
        data_json=json.dumps(analysis),
        created_at=_utcnow(),
    )
    db_session.add(snapshot)
    await db_session.flush()  # get snapshot.id for FK

    topics = []
    for t in analysis.get("topics", []):
        topic = NicheTopic(
            id=_new_uuid(),
            snapshot_id=snapshot.id,
            topic=str(t.get("topic", ""))[:300],
            estimated_demand=int(t.get("estimated_demand", 5)),
            competition_level=str(t.get("competition_level", "medium"))[:20],
            source=str(t.get("source", "gpt_analysis"))[:30],
            created_at=_utcnow(),
        )
        db_session.add(topic)
        topics.append(topic)

    await db_session.flush()
    return snapshot, topics
