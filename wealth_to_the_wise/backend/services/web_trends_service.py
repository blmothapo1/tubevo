# filepath: backend/services/web_trends_service.py
"""
Live web trends service — fetches REAL current data from the internet
to ground AI-generated topic suggestions in reality.

Sources:
  1. **SerpAPI Google Trends** — what people are actually searching for right now
  2. **SerpAPI YouTube Search** — what's ranking on YouTube *today* in the niche
  3. **Google News (via SerpAPI)** — latest headlines in the niche

The results are passed as context into GPT prompts so the AI produces
topics grounded in March 2026 reality instead of its 2024 training data.

This module is intentionally **synchronous** (httpx calls) — callers
wrap it in ``asyncio.to_thread()`` when needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("tubevo.backend.web_trends")

_SERPAPI_BASE = "https://serpapi.com"
_TIMEOUT = 15.0


# ── Google Trends: trending searches in a niche ─────────────────────

def fetch_google_trends(
    *,
    niche: str,
    serpapi_key: str,
    geo: str = "US",
    limit: int = 10,
) -> list[dict]:
    """Fetch related rising queries from Google Trends for a niche.

    Returns a list of dicts:
      [{"query": "...", "value": <int or "Breakout">}, ...]
    """
    if not serpapi_key:
        logger.debug("No SerpAPI key — skipping Google Trends fetch")
        return []

    try:
        resp = httpx.get(
            f"{_SERPAPI_BASE}/search.json",
            params={
                "engine": "google_trends",
                "q": niche,
                "data_type": "RELATED_QUERIES",
                "geo": geo,
                "api_key": serpapi_key,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Google Trends API returned %d: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()

        results: list[dict] = []

        # Rising queries are the most valuable — these are spiking NOW
        rising = data.get("related_queries", {}).get("rising", [])
        for item in rising[:limit]:
            results.append({
                "query": item.get("query", ""),
                "value": item.get("value", 0),
                "type": "rising",
            })

        # Top queries as fallback if rising is sparse
        if len(results) < 5:
            top = data.get("related_queries", {}).get("top", [])
            for item in top[:limit - len(results)]:
                results.append({
                    "query": item.get("query", ""),
                    "value": item.get("value", 0),
                    "type": "top",
                })

        logger.info("Google Trends: found %d queries for '%s'", len(results), niche)
        return results

    except Exception as exc:
        logger.warning("Google Trends fetch failed (non-fatal): %s", exc)
        return []


# ── YouTube Search: what's ranking RIGHT NOW ─────────────────────────

def fetch_youtube_trending(
    *,
    niche: str,
    serpapi_key: str,
    limit: int = 10,
) -> list[dict]:
    """Search YouTube for recent videos in a niche, sorted by relevance.

    Returns a list of dicts:
      [{"title": "...", "channel": "...", "views": "...", "published": "...", "link": "..."}, ...]
    """
    if not serpapi_key:
        logger.debug("No SerpAPI key — skipping YouTube search")
        return []

    try:
        resp = httpx.get(
            f"{_SERPAPI_BASE}/search.json",
            params={
                "engine": "youtube",
                "search_query": f"{niche} 2026",
                "sp": "CAISBAgDEAE%3D",  # Filter: this month, sorted by relevance
                "api_key": serpapi_key,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("YouTube Search API returned %d: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()
        video_results = data.get("video_results", [])

        results: list[dict] = []
        for vid in video_results[:limit]:
            results.append({
                "title": vid.get("title", ""),
                "channel": vid.get("channel", {}).get("name", ""),
                "views": vid.get("views", ""),
                "published": vid.get("published_date", ""),
                "link": vid.get("link", ""),
            })

        logger.info("YouTube Search: found %d videos for '%s'", len(results), niche)
        return results

    except Exception as exc:
        logger.warning("YouTube search fetch failed (non-fatal): %s", exc)
        return []


# ── Google News: latest headlines ────────────────────────────────────

def fetch_google_news(
    *,
    niche: str,
    serpapi_key: str,
    limit: int = 8,
) -> list[dict]:
    """Fetch recent news headlines related to the niche.

    Returns a list of dicts:
      [{"title": "...", "source": "...", "date": "...", "snippet": "..."}, ...]
    """
    if not serpapi_key:
        logger.debug("No SerpAPI key — skipping Google News fetch")
        return []

    try:
        resp = httpx.get(
            f"{_SERPAPI_BASE}/search.json",
            params={
                "engine": "google",
                "q": niche,
                "tbm": "nws",
                "num": limit,
                "api_key": serpapi_key,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("Google News API returned %d: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()
        news_results = data.get("news_results", [])

        results: list[dict] = []
        for article in news_results[:limit]:
            results.append({
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "date": article.get("date", ""),
                "snippet": article.get("snippet", ""),
            })

        logger.info("Google News: found %d articles for '%s'", len(results), niche)
        return results

    except Exception as exc:
        logger.warning("Google News fetch failed (non-fatal): %s", exc)
        return []


# ── Combined: fetch all sources and build a context block ────────────

def fetch_live_trend_context(
    *,
    niche: str,
    serpapi_key: str,
) -> str:
    """Fetch live data from all sources and format it as a text block
    that can be injected into GPT system prompts.

    Returns an empty string if no data is available (graceful degradation).
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines: list[str] = [
        f"\n\n═══ LIVE MARKET DATA (fetched {today}) ═══",
        f"Today's date: {today}. All suggestions MUST be relevant to this date.",
        "",
    ]

    has_data = False

    # 1. Google Trends
    trends = fetch_google_trends(niche=niche, serpapi_key=serpapi_key)
    if trends:
        has_data = True
        lines.append("── Google Trends: Rising Searches ──")
        for t in trends:
            growth = f" (+{t['value']}%)" if isinstance(t["value"], int) and t["value"] > 0 else ""
            badge = " 🔥 BREAKOUT" if t.get("value") == "Breakout" else ""
            lines.append(f"  • {t['query']}{growth}{badge}")
        lines.append("")

    # 2. YouTube — what's ranking now
    yt_videos = fetch_youtube_trending(niche=niche, serpapi_key=serpapi_key)
    if yt_videos:
        has_data = True
        lines.append("── YouTube: Top Recent Videos (what's working RIGHT NOW) ──")
        for v in yt_videos[:8]:
            views = f" ({v['views']})" if v.get("views") else ""
            lines.append(f"  • \"{v['title']}\" by {v['channel']}{views}")
        lines.append("")

    # 3. Google News — latest headlines
    news = fetch_google_news(niche=niche, serpapi_key=serpapi_key)
    if news:
        has_data = True
        lines.append("── Latest News Headlines ──")
        for n in news[:6]:
            date_str = f" ({n['date']})" if n.get("date") else ""
            lines.append(f"  • {n['title']} — {n['source']}{date_str}")
        lines.append("")

    if not has_data:
        # Fallback: just inject the date so the model at least knows the year
        return (
            f"\n\nIMPORTANT: Today's date is {today}. "
            f"All topics MUST be relevant to {today}. "
            f"Do NOT suggest outdated topics from 2023 or 2024."
        )

    lines.append(
        "USE the above data to ground your suggestions in CURRENT reality. "
        "Find gaps — topics that are trending but NOT yet covered by the top creators. "
        "Do NOT just reword the titles above — find the ANGLE they missed."
    )
    lines.append("═══ END LIVE DATA ═══\n")

    return "\n".join(lines)
