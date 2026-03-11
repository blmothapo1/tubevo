# filepath: backend/routers/insights.py
"""
Performance Insights API — aggregated analytics for the Insights dashboard.

Endpoints:
    GET /api/insights/overview       — hero stats (total views, avg engagement, etc.)
    GET /api/insights/timeline       — time-series data for charts
    GET /api/insights/top-videos     — ranked by engagement score
    GET /api/insights/style-analysis — which creative choices perform best
    GET /api/insights/recommendations— adaptive engine suggestions
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import ContentPerformance, User, VideoRecord

logger = logging.getLogger("tubevo.backend.routers.insights")

router = APIRouter(prefix="/api/insights", tags=["insights"])


# ── Schemas ──────────────────────────────────────────────────────────

class InsightOverview(BaseModel):
    total_videos: int = 0
    posted_videos: int = 0
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    avg_engagement_score: float = 0.0
    best_engagement_score: int = 0
    avg_ctr: float | None = None
    avg_retention: float | None = None
    videos_with_metrics: int = 0


class TimelinePoint(BaseModel):
    date: str  # YYYY-MM-DD
    views: int = 0
    likes: int = 0
    comments: int = 0
    videos_posted: int = 0
    avg_engagement: float = 0.0


class TopVideo(BaseModel):
    id: str
    title: str
    topic: str
    status: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    ctr: float | None = None
    retention: float | None = None
    engagement_score: int = 0
    created_at: str
    youtube_url: str | None = None
    thumbnail_path: str | None = None


class StyleStat(BaseModel):
    name: str
    count: int = 0
    avg_engagement: float = 0.0
    total_views: int = 0
    best_score: int = 0


class StyleAnalysis(BaseModel):
    title_styles: list[StyleStat] = []
    thumbnail_styles: list[StyleStat] = []
    hook_modes: list[StyleStat] = []


class Recommendation(BaseModel):
    category: str  # "title_style" | "thumbnail" | "hook" | "general"
    label: str
    detail: str
    confidence: str  # "high" | "medium" | "low"


# ── GET /api/insights/overview ───────────────────────────────────────

@router.get("/overview", response_model=InsightOverview)
async def insights_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(90, ge=7, le=365, description="Lookback window in days"),
):
    """Aggregate performance stats for the hero cards."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # ── Video counts ─────────────────────────────────────────────────
    total_q = select(func.count()).select_from(VideoRecord).where(
        VideoRecord.user_id == current_user.id,
        VideoRecord.created_at >= cutoff,
    )
    total_videos = (await db.execute(total_q)).scalar() or 0

    posted_q = total_q.where(VideoRecord.status == "posted")
    posted_videos = (await db.execute(posted_q)).scalar() or 0

    # ── Content performance aggregates ───────────────────────────────
    perf_base = select(ContentPerformance).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.metrics_fetched_at.isnot(None),
    )

    agg_q = select(
        func.count().label("cnt"),
        func.coalesce(func.sum(ContentPerformance.views_48h), 0).label("total_views"),
        func.coalesce(func.sum(ContentPerformance.likes_48h), 0).label("total_likes"),
        func.coalesce(func.sum(ContentPerformance.comments_48h), 0).label("total_comments"),
        func.coalesce(func.avg(ContentPerformance.engagement_score), 0).label("avg_eng"),
        func.coalesce(func.max(ContentPerformance.engagement_score), 0).label("best_eng"),
    ).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.metrics_fetched_at.isnot(None),
    )

    row = (await db.execute(agg_q)).one()

    # Average CTR and retention (only over rows that have values)
    ctr_q = select(func.avg(func.cast(ContentPerformance.ctr_pct, func.REAL))).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.ctr_pct.isnot(None),
    )
    avg_ctr = (await db.execute(ctr_q)).scalar()

    ret_q = select(func.avg(func.cast(ContentPerformance.avg_view_duration_pct, func.REAL))).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.avg_view_duration_pct.isnot(None),
    )
    avg_retention = (await db.execute(ret_q)).scalar()

    return InsightOverview(
        total_videos=total_videos,
        posted_videos=posted_videos,
        total_views=int(row.total_views),
        total_likes=int(row.total_likes),
        total_comments=int(row.total_comments),
        avg_engagement_score=round(float(row.avg_eng), 1),
        best_engagement_score=int(row.best_eng),
        avg_ctr=round(float(avg_ctr), 1) if avg_ctr is not None else None,
        avg_retention=round(float(avg_retention), 1) if avg_retention is not None else None,
        videos_with_metrics=int(row.cnt),
    )


# ── GET /api/insights/timeline ───────────────────────────────────────

@router.get("/timeline")
async def insights_timeline(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=7, le=365, description="Lookback window in days"),
):
    """Daily time-series of views, likes, comments for charting."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get all content performance records in window
    q = select(ContentPerformance).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.metrics_fetched_at.isnot(None),
    ).order_by(ContentPerformance.created_at)

    result = await db.execute(q)
    records = result.scalars().all()

    # Also get video creation dates for "videos posted" count
    vq = select(VideoRecord.created_at).where(
        VideoRecord.user_id == current_user.id,
        VideoRecord.status == "posted",
        VideoRecord.created_at >= cutoff,
    )
    posted_result = await db.execute(vq)
    posted_dates = [r[0] for r in posted_result.all()]

    # Bucket by date
    from collections import defaultdict
    buckets: dict[str, dict] = defaultdict(lambda: {
        "views": 0, "likes": 0, "comments": 0,
        "videos_posted": 0, "engagement_scores": [],
    })

    for rec in records:
        day_key = rec.created_at.strftime("%Y-%m-%d")
        buckets[day_key]["views"] += rec.views_48h
        buckets[day_key]["likes"] += rec.likes_48h
        buckets[day_key]["comments"] += rec.comments_48h
        buckets[day_key]["engagement_scores"].append(rec.engagement_score)

    for dt in posted_dates:
        day_key = dt.strftime("%Y-%m-%d")
        buckets[day_key]["videos_posted"] += 1

    # Fill gaps (days with no data get zero)
    timeline: list[dict] = []
    current = cutoff.date()
    today = datetime.now(timezone.utc).date()
    while current <= today:
        key = current.isoformat()
        b = buckets.get(key, {"views": 0, "likes": 0, "comments": 0, "videos_posted": 0, "engagement_scores": []})
        scores = b["engagement_scores"] if isinstance(b.get("engagement_scores"), list) else []
        avg_eng = round(sum(scores) / len(scores), 1) if scores else 0.0
        timeline.append({
            "date": key,
            "views": b["views"],
            "likes": b["likes"],
            "comments": b["comments"],
            "videos_posted": b["videos_posted"],
            "avg_engagement": avg_eng,
        })
        current += timedelta(days=1)

    return {"timeline": timeline, "days": days}


# ── GET /api/insights/top-videos ─────────────────────────────────────

@router.get("/top-videos")
async def insights_top_videos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
    sort_by: str = Query("engagement_score", description="Sort field"),
):
    """Return top-performing videos ranked by engagement score."""
    q = (
        select(ContentPerformance, VideoRecord)
        .join(VideoRecord, ContentPerformance.video_record_id == VideoRecord.id)
        .where(
            ContentPerformance.user_id == current_user.id,
            ContentPerformance.metrics_fetched_at.isnot(None),
        )
        .order_by(desc(ContentPerformance.engagement_score))
        .limit(limit)
    )

    result = await db.execute(q)
    rows = result.all()

    videos = []
    for perf, video in rows:
        ctr_val = None
        ret_val = None
        try:
            if perf.ctr_pct:
                ctr_val = float(perf.ctr_pct)
        except (ValueError, TypeError):
            pass
        try:
            if perf.avg_view_duration_pct:
                ret_val = float(perf.avg_view_duration_pct)
        except (ValueError, TypeError):
            pass

        videos.append(TopVideo(
            id=video.id,
            title=video.title,
            topic=video.topic,
            status=video.status,
            views=perf.views_48h,
            likes=perf.likes_48h,
            comments=perf.comments_48h,
            ctr=ctr_val,
            retention=ret_val,
            engagement_score=perf.engagement_score,
            created_at=video.created_at.isoformat() if video.created_at else "",
            youtube_url=video.youtube_url,
            thumbnail_path=video.thumbnail_path,
        ))

    return {"videos": videos, "total": len(videos)}


# ── GET /api/insights/style-analysis ─────────────────────────────────

@router.get("/style-analysis", response_model=StyleAnalysis)
async def insights_style_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(90, ge=7, le=365),
):
    """Break down performance by title style, thumbnail concept, and hook mode."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = select(ContentPerformance).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.metrics_fetched_at.isnot(None),
    )
    result = await db.execute(q)
    records = result.scalars().all()

    # Aggregate by dimension
    from collections import defaultdict

    def _aggregate(records, key_fn):
        groups = defaultdict(lambda: {"count": 0, "total_eng": 0, "total_views": 0, "best": 0})
        for rec in records:
            key = key_fn(rec)
            if not key:
                continue
            g = groups[key]
            g["count"] += 1
            g["total_eng"] += rec.engagement_score
            g["total_views"] += rec.views_48h
            g["best"] = max(g["best"], rec.engagement_score)
        return [
            StyleStat(
                name=name,
                count=g["count"],
                avg_engagement=round(g["total_eng"] / g["count"], 1) if g["count"] else 0,
                total_views=g["total_views"],
                best_score=g["best"],
            )
            for name, g in sorted(groups.items(), key=lambda x: -x[1]["total_eng"] / max(x[1]["count"], 1))
        ]

    title_styles = _aggregate(records, lambda r: r.title_style_used)
    thumbnail_styles = _aggregate(records, lambda r: r.thumbnail_concept_used)
    hook_modes = _aggregate(records, lambda r: r.hook_mode_used)

    return StyleAnalysis(
        title_styles=title_styles,
        thumbnail_styles=thumbnail_styles,
        hook_modes=hook_modes,
    )


# ── GET /api/insights/recommendations ────────────────────────────────

@router.get("/recommendations")
async def insights_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate actionable recommendations from the adaptive engine."""
    from backend.adaptive_engine import (
        PerformanceProfile, TITLE_STYLES, THUMBNAIL_STYLES,
        MIN_DATA_POINTS, EXPLORATION_FLOOR,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # Fetch content performance data
    q = select(ContentPerformance).where(
        ContentPerformance.user_id == current_user.id,
        ContentPerformance.created_at >= cutoff,
        ContentPerformance.metrics_fetched_at.isnot(None),
    )
    result = await db.execute(q)
    records = result.scalars().all()

    recommendations: list[dict] = []

    if len(records) < MIN_DATA_POINTS:
        recommendations.append({
            "category": "general",
            "label": "Keep creating content",
            "detail": f"The system needs at least {MIN_DATA_POINTS} videos with analytics data to generate personalized recommendations. You have {len(records)} so far — keep publishing and check back soon!",
            "confidence": "low",
        })
        return {"recommendations": recommendations, "data_points": len(records)}

    # ── Title style analysis ─────────────────────────────────────────
    from collections import defaultdict
    title_groups = defaultdict(list)
    thumb_groups = defaultdict(list)
    hook_groups = defaultdict(list)

    for rec in records:
        if rec.title_style_used:
            title_groups[rec.title_style_used].append(rec.engagement_score)
        if rec.thumbnail_concept_used:
            thumb_groups[rec.thumbnail_concept_used].append(rec.engagement_score)
        if rec.hook_mode_used:
            hook_groups[rec.hook_mode_used].append(rec.engagement_score)

    # Find best title style
    if title_groups:
        best_title = max(title_groups.items(), key=lambda x: sum(x[1]) / len(x[1]))
        worst_title = min(title_groups.items(), key=lambda x: sum(x[1]) / len(x[1]))
        best_avg = round(sum(best_title[1]) / len(best_title[1]), 1)
        worst_avg = round(sum(worst_title[1]) / len(worst_title[1]), 1)

        if best_avg > worst_avg + 10:
            recommendations.append({
                "category": "title_style",
                "label": f"Lean into {best_title[0].replace('_', ' ').title()} titles",
                "detail": f"Your '{best_title[0].replace('_', ' ')}' titles average {best_avg} engagement vs {worst_avg} for '{worst_title[0].replace('_', ' ')}'. Consider using this style more frequently.",
                "confidence": "high" if len(best_title[1]) >= 3 else "medium",
            })

    # Find best thumbnail style
    if thumb_groups:
        best_thumb = max(thumb_groups.items(), key=lambda x: sum(x[1]) / len(x[1]))
        best_avg = round(sum(best_thumb[1]) / len(best_thumb[1]), 1)
        recommendations.append({
            "category": "thumbnail",
            "label": f"Best thumbnail style: {best_thumb[0].replace('_', ' ').title()}",
            "detail": f"Your '{best_thumb[0].replace('_', ' ')}' thumbnails achieve an average engagement of {best_avg} across {len(best_thumb[1])} videos.",
            "confidence": "high" if len(best_thumb[1]) >= 3 else "medium",
        })

    # Hook mode analysis
    if hook_groups:
        best_hook = max(hook_groups.items(), key=lambda x: sum(x[1]) / len(x[1]))
        best_avg = round(sum(best_hook[1]) / len(best_hook[1]), 1)
        recommendations.append({
            "category": "hook",
            "label": f"Optimal hook intensity: {best_hook[0].title()}",
            "detail": f"Videos with '{best_hook[0]}' hooks score an average engagement of {best_avg}. The system will weight this approach more heavily.",
            "confidence": "high" if len(best_hook[1]) >= 3 else "medium",
        })

    # General performance trend
    if len(records) >= 6:
        sorted_recs = sorted(records, key=lambda r: r.created_at)
        first_half = sorted_recs[:len(sorted_recs)//2]
        second_half = sorted_recs[len(sorted_recs)//2:]
        avg_first = sum(r.engagement_score for r in first_half) / len(first_half)
        avg_second = sum(r.engagement_score for r in second_half) / len(second_half)
        delta = round(avg_second - avg_first, 1)

        if delta > 5:
            recommendations.append({
                "category": "general",
                "label": "Your content is improving 📈",
                "detail": f"Recent videos score {round(avg_second, 1)} avg engagement vs {round(avg_first, 1)} for earlier ones — a +{delta} point improvement. The adaptive system is learning what works for your audience.",
                "confidence": "high",
            })
        elif delta < -5:
            recommendations.append({
                "category": "general",
                "label": "Engagement dip detected",
                "detail": f"Recent videos average {round(avg_second, 1)} engagement vs {round(avg_first, 1)} earlier (−{abs(delta)} points). Consider experimenting with different topics or styles.",
                "confidence": "medium",
            })
        else:
            recommendations.append({
                "category": "general",
                "label": "Consistent performance",
                "detail": f"Your engagement is steady at ~{round(avg_second, 1)}. The system continues to explore different styles to find your best approach.",
                "confidence": "medium",
            })

    # CTR insight
    ctr_records = [r for r in records if r.ctr_pct]
    if len(ctr_records) >= 3:
        avg_ctr = sum(float(r.ctr_pct) for r in ctr_records) / len(ctr_records)
        if avg_ctr < 4.0:
            recommendations.append({
                "category": "general",
                "label": "Improve click-through rate",
                "detail": f"Your average CTR is {round(avg_ctr, 1)}%, which is below the YouTube average of ~5%. Focus on more compelling thumbnails and curiosity-driven titles.",
                "confidence": "medium",
            })
        elif avg_ctr >= 8.0:
            recommendations.append({
                "category": "general",
                "label": "Excellent click-through rate! 🎯",
                "detail": f"Your average CTR of {round(avg_ctr, 1)}% is well above industry average. Your thumbnails and titles are working great.",
                "confidence": "high",
            })

    return {"recommendations": recommendations, "data_points": len(records)}
