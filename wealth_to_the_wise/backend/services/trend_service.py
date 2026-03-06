# filepath: backend/services/trend_service.py
"""
Trend Radar service — detects trending topics, generates videos, queues them
for one-tap publish or autopilot.

Sources:
1. **Niche Analysis** — leverages existing niche_service.analyse_niche() to find
   high-demand, low-competition topics in the user's configured niches.
2. **Competitor Gap** — finds topics competitors cover that the user hasn't.
3. **Trending Score** — prioritises topics with high trending_score from niche snapshots.

The service is intentionally synchronous (httpx calls) — the caller wraps it
in ``asyncio.to_thread()`` when needed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("tubevo.backend.trend_service")

# ── Trend detection via GPT ──────────────────────────────────────────

_TREND_SYSTEM_PROMPT = """\
You are a YouTube trend analyst specialising in detecting viral-worthy video topics.
Given a niche, tone, audience, and a list of topics the creator has ALREADY covered,
identify 5-8 FRESH trending topics that:

1. Have HIGH current demand (people are actively searching for this NOW)
2. Have LOW-to-MEDIUM competition (not every creator has covered it yet)
3. Are SPECIFIC enough to be a single video (not a broad category)
4. Would perform well on YouTube in the next 7 days

For each topic, return:
{
  "topics": [
    {
      "topic": "<specific, click-worthy video title idea>",
      "confidence_score": <int 40-100, higher = more confident this will perform>,
      "estimated_demand": <int 1-10>,
      "competition_level": "<low|medium|high>",
      "source": "trend_analysis",
      "reasoning": "<1-2 sentences explaining WHY this is trending right now>"
    }
  ]
}

Rules:
- Do NOT suggest topics that overlap with the "already covered" list.
- Be SPECIFIC — "How To Budget" is too generic. "The 50/30/20 Budget Rule Is Dead — Here's What Replaced It" is specific.
- Base confidence on a combination of search volume, social buzz, and timeliness.
- Higher confidence = more actionable, more timely, higher chance of going viral.
- Return ONLY the JSON object, nothing else.
"""


def detect_trending_topics(
    *,
    niche: str,
    openai_api_key: str,
    tone_style: str = "confident, direct, no-fluff educator",
    target_audience: str = "general audience",
    already_covered: list[str] | None = None,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Call OpenAI to detect trending topics in a niche.

    Returns a list of dicts, each with:
      topic, confidence_score, estimated_demand, competition_level, source, reasoning

    Raises ``ValueError`` on parse failure.
    """
    covered_text = ""
    if already_covered:
        covered_list = "\n".join(f"- {t}" for t in already_covered[:20])
        covered_text = f"\n\nALREADY COVERED (do NOT repeat):\n{covered_list}"

    user_prompt = (
        f"Niche: {niche}\n"
        f"Channel tone: {tone_style}\n"
        f"Target audience: {target_audience}"
        f"{covered_text}\n\n"
        f"Detect trending topics and return the JSON object."
    )

    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.8,
            "max_tokens": 2000,
            "messages": [
                {"role": "system", "content": _TREND_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60.0,
    )

    if resp.status_code != 200:
        logger.error("OpenAI trend detection failed: %d %s", resp.status_code, resp.text[:300])
        raise ValueError(f"OpenAI API error: {resp.status_code}")

    raw_content = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip code fences if the model wraps them
    if raw_content.startswith("```"):
        raw_content = raw_content.split("\n", 1)[-1]
    if raw_content.endswith("```"):
        raw_content = raw_content.rsplit("```", 1)[0]
    raw_content = raw_content.strip()

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse trend detection JSON: %s", raw_content[:300])
        raise ValueError(f"Invalid JSON from OpenAI: {exc}") from exc

    topics = data.get("topics", [])
    if not isinstance(topics, list):
        raise ValueError("Trend detection returned invalid topics list")

    # Validate and normalise each topic
    validated = []
    for t in topics:
        if not isinstance(t, dict) or not t.get("topic"):
            continue
        validated.append({
            "topic": str(t["topic"])[:300],
            "confidence_score": max(0, min(100, int(t.get("confidence_score", 50)))),
            "estimated_demand": max(1, min(10, int(t.get("estimated_demand", 5)))),
            "competition_level": str(t.get("competition_level", "medium"))[:20],
            "source": str(t.get("source", "trend_analysis"))[:50],
            "reasoning": str(t.get("reasoning", ""))[:500],
        })

    return validated


# ── Persistence helpers ──────────────────────────────────────────────

async def save_trend_alerts(
    *,
    user_id: str,
    channel_id: str | None,
    niche: str,
    topics: list[dict],
    db_session,
    min_confidence: int = 40,
) -> list:
    """Persist detected trends as TrendAlert rows.

    Deduplicates against ALL recent alerts for the same user+topic
    (published within the last 30 days, plus anything still active).
    Returns the list of newly created TrendAlert ORM objects.
    """
    from datetime import datetime, timedelta, timezone

    from backend.models import TrendAlert, _new_uuid, _utcnow
    from sqlalchemy import or_, select

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Fetch topics from: (a) active alerts (detected/generating/ready), and
    # (b) alerts published/dismissed within the last 30 days — to prevent
    #     the same topic recycling right after it was published.
    existing_stmt = (
        select(TrendAlert.trend_topic)
        .where(
            TrendAlert.user_id == user_id,
            or_(
                TrendAlert.status.in_(["detected", "generating", "ready"]),
                TrendAlert.created_at >= thirty_days_ago,
            ),
        )
    )
    existing_rows = (await db_session.execute(existing_stmt)).scalars().all()
    existing_topics = {t.lower().strip() for t in existing_rows}

    created = []
    for t in topics:
        score = t.get("confidence_score", 50)
        if score < min_confidence:
            continue

        topic_text = t["topic"]
        if topic_text.lower().strip() in existing_topics:
            continue

        alert = TrendAlert(
            id=_new_uuid(),
            user_id=user_id,
            channel_id=channel_id,
            trend_topic=topic_text,
            trend_source=t.get("source", "trend_analysis"),
            confidence_score=score,
            estimated_demand=t.get("estimated_demand", 5),
            competition_level=t.get("competition_level", "medium"),
            niche=niche,
            reasoning=t.get("reasoning", ""),
            status="detected",
            detected_at=_utcnow(),
            created_at=_utcnow(),
        )
        db_session.add(alert)
        created.append(alert)
        existing_topics.add(topic_text.lower().strip())

    if created:
        await db_session.flush()

    return created
