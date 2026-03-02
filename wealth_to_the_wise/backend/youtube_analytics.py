# filepath: backend/youtube_analytics.py
"""
YouTube Analytics ingestion module.

Fetches real performance data from YouTube for published videos so the
adaptive learning loop uses actual engagement signals instead of defaults.

Two API surfaces are used:
1. **YouTube Data API v3** — ``videos.list(statistics)`` for views, likes,
   comments.  Reliable, always available with ``youtube.readonly``.
2. **YouTube Analytics API** — ``reports.query`` for impressions, CTR, and
   average view duration percentage.  Requires the
   ``yt-analytics.readonly`` scope — if missing, we skip gracefully.

All failures are non-fatal: the module returns ``{}`` on any error so the
caller can safely ignore analytics failures without impacting generation,
rendering, or uploading.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("tubevo.backend.youtube_analytics")

# ── Retry configuration ──────────────────────────────────────────────

_MAX_RETRIES = 5
_BASE_DELAY = 2.0   # seconds
_MAX_DELAY = 60.0
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ── Required scopes ──────────────────────────────────────────────────

_SCOPE_DATA_API = "https://www.googleapis.com/auth/youtube.readonly"
_SCOPE_ANALYTICS = "https://www.googleapis.com/auth/yt-analytics.readonly"


# ── Helpers ──────────────────────────────────────────────────────────

def _build_credentials(
    access_token: str,
    refresh_token: str | None,
    client_id: str,
    client_secret: str,
    scopes: list[str] | None = None,
) -> Credentials:
    """Build a ``google.oauth2.credentials.Credentials`` object and
    refresh it if expired."""
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or [_SCOPE_DATA_API],
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            logger.info("Refreshed Google credentials for analytics")
        except Exception as e:
            logger.warning("Failed to refresh credentials for analytics: %s", e)
            raise
    return creds


def _retry_api_call(callable_fn, *, description: str = "API call"):
    """Execute a Google API call with exponential backoff on retriable errors.

    Returns the response dict on success, or ``None`` on exhausted retries.
    """
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return callable_fn()
        except HttpError as exc:
            last_exc = exc
            status_code = exc.resp.status if hasattr(exc, "resp") else 0

            if status_code not in _RETRIABLE_STATUS_CODES:
                logger.warning(
                    "%s failed with non-retriable HTTP %s: %s",
                    description, status_code, exc,
                )
                return None

            delay = min(_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1), _MAX_DELAY)
            logger.warning(
                "%s HTTP %s (attempt %d/%d) — retrying in %.1fs",
                description, status_code, attempt, _MAX_RETRIES, delay,
            )
            time.sleep(delay)
        except Exception as exc:
            logger.warning("%s unexpected error: %s", description, exc)
            return None

    logger.error("%s failed after %d retries: %s", description, _MAX_RETRIES, last_exc)
    return None


def _has_scope(granted_scopes: str | None, required_scope: str) -> bool:
    """Check if a required scope is present in the space-separated granted scopes string."""
    if not granted_scopes:
        return False
    return required_scope in granted_scopes.split()


# ── Public API ───────────────────────────────────────────────────────

def fetch_video_metrics(
    *,
    youtube_video_id: str,
    channel_id: str | None,
    access_token: str,
    refresh_token: str | None,
    client_id: str,
    client_secret: str,
    granted_scopes: str | None = None,
    published_at: datetime | None = None,
) -> dict:
    """Fetch YouTube metrics for a single video.

    Returns a dict with available metrics::

        {
            "views_48h": int,
            "likes_48h": int,
            "comments_48h": int,
            "ctr_pct": str | None,          # e.g. "4.2"
            "avg_view_duration_pct": str | None,  # e.g. "42.5"
            "engagement_score": int,         # 0-100 composite
        }

    Returns ``{}`` on any unrecoverable failure.
    """
    try:
        return _fetch_metrics_inner(
            youtube_video_id=youtube_video_id,
            channel_id=channel_id,
            access_token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            granted_scopes=granted_scopes,
            published_at=published_at,
        )
    except Exception as exc:
        logger.warning(
            "fetch_video_metrics failed for %s (non-fatal): %s",
            youtube_video_id, exc,
        )
        return {}


def _fetch_metrics_inner(
    *,
    youtube_video_id: str,
    channel_id: str | None,
    access_token: str,
    refresh_token: str | None,
    client_id: str,
    client_secret: str,
    granted_scopes: str | None,
    published_at: datetime | None,
) -> dict:
    """Inner implementation — may raise on credential issues."""

    metrics: dict = {}

    # ── Phase A: YouTube Data API v3 — statistics ────────────────────
    # Always available with youtube.readonly scope
    if not _has_scope(granted_scopes, _SCOPE_DATA_API):
        logger.info(
            "Skipping Data API for %s — youtube.readonly scope not granted",
            youtube_video_id,
        )
    else:
        try:
            creds = _build_credentials(
                access_token=access_token,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                scopes=[_SCOPE_DATA_API],
            )
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            response = _retry_api_call(
                lambda: youtube.videos().list(
                    part="statistics,contentDetails",
                    id=youtube_video_id,
                ).execute(),
                description=f"Data API videos.list({youtube_video_id})",
            )

            if response and response.get("items"):
                stats = response["items"][0].get("statistics", {})
                metrics["views_48h"] = int(stats.get("viewCount", 0))
                metrics["likes_48h"] = int(stats.get("likeCount", 0))
                metrics["comments_48h"] = int(stats.get("commentCount", 0))

                logger.info(
                    "Data API for %s: views=%s likes=%s comments=%s",
                    youtube_video_id,
                    metrics["views_48h"],
                    metrics["likes_48h"],
                    metrics["comments_48h"],
                )
            else:
                logger.warning("Data API returned no items for %s", youtube_video_id)

        except Exception as exc:
            logger.warning("Data API fetch failed for %s: %s", youtube_video_id, exc)

    # ── Phase B: YouTube Analytics API — CTR + retention ─────────────
    # Requires yt-analytics.readonly scope — skip gracefully if missing
    if not _has_scope(granted_scopes, _SCOPE_ANALYTICS):
        logger.info(
            "Skipping Analytics API for %s — yt-analytics.readonly scope not granted "
            "(user needs to reconnect YouTube with updated scopes)",
            youtube_video_id,
        )
    elif not channel_id:
        logger.info(
            "Skipping Analytics API for %s — no channel_id available",
            youtube_video_id,
        )
    else:
        try:
            creds = _build_credentials(
                access_token=access_token,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                scopes=[_SCOPE_ANALYTICS],
            )
            yt_analytics = build(
                "youtubeAnalytics", "v2",
                credentials=creds,
                cache_discovery=False,
            )

            # Date range: published_at to published_at + 2 days (48h window)
            # YouTube Analytics API uses date strings (YYYY-MM-DD)
            if published_at:
                start_date = published_at.strftime("%Y-%m-%d")
                from datetime import timedelta
                end_date = (published_at + timedelta(days=2)).strftime("%Y-%m-%d")
            else:
                # Fallback: last 3 days from now
                from datetime import timedelta
                now = datetime.now(timezone.utc)
                start_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
                end_date = now.strftime("%Y-%m-%d")

            response = _retry_api_call(
                lambda: yt_analytics.reports().query(
                    ids=f"channel=={channel_id}",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
                    dimensions="video",
                    filters=f"video=={youtube_video_id}",
                ).execute(),
                description=f"Analytics API report({youtube_video_id})",
            )

            if response and response.get("rows"):
                row = response["rows"][0]
                # Column order matches metrics in the query:
                # [videoId, views, estimatedMinutesWatched, averageViewDuration, averageViewPercentage]
                column_headers = [h["name"] for h in response.get("columnHeaders", [])]

                analytics_data = dict(zip(column_headers, row))

                avg_view_pct = analytics_data.get("averageViewPercentage")
                if avg_view_pct is not None:
                    metrics["avg_view_duration_pct"] = f"{float(avg_view_pct):.1f}"
                    logger.info(
                        "Analytics API for %s: avg_view_pct=%.1f%%",
                        youtube_video_id, float(avg_view_pct),
                    )

            # Second query for impressions + CTR (separate metrics group)
            ctr_response = _retry_api_call(
                lambda: yt_analytics.reports().query(
                    ids=f"channel=={channel_id}",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="impressions,impressionClickThroughRate",
                    dimensions="video",
                    filters=f"video=={youtube_video_id}",
                ).execute(),
                description=f"Analytics API CTR({youtube_video_id})",
            )

            if ctr_response and ctr_response.get("rows"):
                ctr_row = ctr_response["rows"][0]
                ctr_headers = [h["name"] for h in ctr_response.get("columnHeaders", [])]
                ctr_data = dict(zip(ctr_headers, ctr_row))

                impression_ctr = ctr_data.get("impressionClickThroughRate")
                if impression_ctr is not None:
                    metrics["ctr_pct"] = f"{float(impression_ctr):.1f}"
                    logger.info(
                        "Analytics API for %s: CTR=%.1f%%",
                        youtube_video_id, float(impression_ctr),
                    )

        except Exception as exc:
            logger.warning("Analytics API fetch failed for %s (non-fatal): %s", youtube_video_id, exc)

    # ── Phase C: Compute engagement score ────────────────────────────
    if metrics:
        metrics["engagement_score"] = compute_engagement_score(metrics)
        logger.info(
            "Engagement score for %s: %d",
            youtube_video_id, metrics["engagement_score"],
        )

    return metrics


def compute_engagement_score(metrics: dict) -> int:
    """Compute a 0-100 composite engagement score from raw metrics.

    Formula (weighted components):
    - Views:    20% — log-scaled (1 view = 0, 10k views = 100)
    - Likes:    15% — likes-to-views ratio (0% = 0, 8%+ = 100)
    - Comments: 10% — comments-to-views ratio (0% = 0, 2%+ = 100)
    - CTR:      25% — impression click-through rate (0% = 0, 10%+ = 100)
    - Retention: 30% — average view duration percentage (0% = 0, 70%+ = 100)

    Missing metrics contribute 50 (neutral) to avoid penalizing incomplete data.
    """
    import math

    views = metrics.get("views_48h", 0)
    likes = metrics.get("likes_48h", 0)
    comments = metrics.get("comments_48h", 0)

    # Views component (log scale: 0 → 0, 100 → 40, 1000 → 60, 10000 → 80, 100000 → 100)
    if views > 0:
        views_score = min(100, (math.log10(views) / math.log10(100_000)) * 100)
    else:
        views_score = 0

    # Like ratio component
    if views > 0:
        like_ratio = (likes / views) * 100  # percentage
        likes_score = min(100, (like_ratio / 8.0) * 100)
    else:
        likes_score = 50  # neutral

    # Comment ratio component
    if views > 0:
        comment_ratio = (comments / views) * 100
        comments_score = min(100, (comment_ratio / 2.0) * 100)
    else:
        comments_score = 50  # neutral

    # CTR component
    ctr_raw = metrics.get("ctr_pct")
    if ctr_raw is not None:
        try:
            ctr = float(ctr_raw)
            ctr_score = min(100, (ctr / 10.0) * 100)
        except (ValueError, TypeError):
            ctr_score = 50  # neutral
    else:
        ctr_score = 50  # neutral — data not available

    # Retention component
    retention_raw = metrics.get("avg_view_duration_pct")
    if retention_raw is not None:
        try:
            retention = float(retention_raw)
            retention_score = min(100, (retention / 70.0) * 100)
        except (ValueError, TypeError):
            retention_score = 50
    else:
        retention_score = 50  # neutral — data not available

    # Weighted composite
    score = (
        views_score * 0.20
        + likes_score * 0.15
        + comments_score * 0.10
        + ctr_score * 0.25
        + retention_score * 0.30
    )

    return max(0, min(100, round(score)))


# ── Inline tests ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running youtube_analytics inline tests…")

    # Test 1: engagement score with full data
    full = {
        "views_48h": 5000,
        "likes_48h": 250,    # 5% ratio
        "comments_48h": 50,  # 1% ratio
        "ctr_pct": "6.0",
        "avg_view_duration_pct": "45.0",
    }
    score = compute_engagement_score(full)
    print(f"  Test 1 — full data: score={score}")
    assert 40 <= score <= 80, f"Expected 40-80 but got {score}"

    # Test 2: empty metrics → neutral
    empty = {}
    score_empty = compute_engagement_score(empty)
    print(f"  Test 2 — empty data: score={score_empty}")
    assert 20 <= score_empty <= 60, f"Expected 20-60 but got {score_empty}"

    # Test 3: viral video
    viral = {
        "views_48h": 500_000,
        "likes_48h": 40_000,  # 8% ratio
        "comments_48h": 10_000,  # 2% ratio
        "ctr_pct": "12.0",
        "avg_view_duration_pct": "65.0",
    }
    score_viral = compute_engagement_score(viral)
    print(f"  Test 3 — viral: score={score_viral}")
    assert score_viral >= 85, f"Expected >=85 but got {score_viral}"

    # Test 4: scope check
    assert _has_scope("https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly", _SCOPE_ANALYTICS)
    assert not _has_scope("https://www.googleapis.com/auth/youtube.readonly", _SCOPE_ANALYTICS)
    assert not _has_scope(None, _SCOPE_ANALYTICS)
    assert not _has_scope("", _SCOPE_ANALYTICS)
    print("  Test 4 — scope checks passed")

    # Test 5: missing CTR/retention → neutral score contribution
    partial = {
        "views_48h": 1000,
        "likes_48h": 50,
        "comments_48h": 10,
    }
    score_partial = compute_engagement_score(partial)
    print(f"  Test 5 — partial data (no CTR/retention): score={score_partial}")
    assert 30 <= score_partial <= 70, f"Expected 30-70 but got {score_partial}"

    print("✅ All 5 youtube_analytics tests passed")
