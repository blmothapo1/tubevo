# filepath: backend/routers/videos.py
"""
Video pipeline router — /api/videos/*

Exposes the CLI auto-pipeline as a REST API for the frontend.

Endpoints
---------
POST /api/videos/generate   — Trigger auto video generation for a topic
GET  /api/videos/history     — Get the user's video upload history
GET  /api/videos/stats       — Dashboard stats for the current user
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User, VideoRecord
from backend.rate_limit import limiter

logger = logging.getLogger("tubevo.backend.videos")

router = APIRouter(prefix="/api/videos", tags=["Videos"])

OUTPUT_DIR = Path("output")


# ── Schemas ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=300)
    auto: bool = True  # full-auto by default


class GenerateResponse(BaseModel):
    status: str
    topic: str
    message: str
    video_id: str | None = None


class VideoHistoryItem(BaseModel):
    id: str
    topic: str
    title: str
    status: str
    file_path: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    thumbnail_path: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class VideoStats(BaseModel):
    total_generated: int
    total_posted: int
    total_failed: int
    total_pending: int


# ── POST /api/videos/generate ────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
@limiter.limit("5/hour")
async def generate_video(
    request: Request,
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger the full-auto pipeline for a given topic.

    Creates a VideoRecord in the database, runs the pipeline in a
    background thread, then updates the record with the result.
    """
    logger.info("User %s requested video generation: '%s'", current_user.email, body.topic)

    # Create a pending record
    record = VideoRecord(
        user_id=current_user.id,
        topic=body.topic,
        title=body.topic,  # will be updated by the pipeline
        status="generating",
    )
    db.add(record)
    await db.flush()  # get the id
    record_id = record.id

    try:
        # Run the CPU-bound pipeline in a thread pool
        result = await asyncio.to_thread(_run_pipeline, body.topic)
    except Exception as e:
        logger.exception("Pipeline failed for topic '%s': %s", body.topic, e)
        record.status = "failed"
        record.error_message = str(e)
        return GenerateResponse(
            status="failed",
            topic=body.topic,
            message=f"Video generation failed: {str(e)}",
            video_id=record_id,
        )

    # Update record with pipeline output
    if result:
        record.status = "posted" if result.get("video_id") else "completed"
        record.title = result.get("title", body.topic)
        record.file_path = result.get("file_path")
        record.youtube_video_id = result.get("video_id")
        record.youtube_url = (
            f"https://www.youtube.com/watch?v={result['video_id']}"
            if result.get("video_id")
            else None
        )
    else:
        record.status = "completed"

    return GenerateResponse(
        status=record.status,
        topic=body.topic,
        message="Video generated successfully.",
        video_id=record_id,
    )


def _run_pipeline(topic: str) -> dict | None:
    """Synchronous wrapper around the existing CLI pipeline."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from main import run_full_auto_pipeline
    import json

    history_path = OUTPUT_DIR / "upload_history.json"

    # Snapshot current history length
    before_count = 0
    if history_path.exists():
        try:
            before = json.loads(history_path.read_text())
            before_count = len(before)
        except Exception:
            pass

    run_full_auto_pipeline(topic)

    # Check if a new entry was added
    if history_path.exists():
        try:
            after = json.loads(history_path.read_text())
            if len(after) > before_count:
                entry = after[-1]
                return {
                    "video_id": entry.get("video_id"),
                    "title": entry.get("title", topic),
                    "file_path": entry.get("file_path"),
                }
        except Exception:
            pass

    return None


# ── GET /api/videos/history ──────────────────────────────────────────

@router.get("/history", response_model=list[VideoHistoryItem])
async def video_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the per-user video history from the database."""
    result = await db.execute(
        select(VideoRecord)
        .where(VideoRecord.user_id == current_user.id)
        .order_by(VideoRecord.created_at.desc())
        .limit(100)
    )
    records = result.scalars().all()

    return [
        VideoHistoryItem(
            id=r.id,
            topic=r.topic,
            title=r.title,
            status=r.status,
            file_path=r.file_path,
            youtube_video_id=r.youtube_video_id,
            youtube_url=r.youtube_url,
            thumbnail_path=r.thumbnail_path,
            error_message=r.error_message,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in records
    ]


# ── GET /api/videos/stats ───────────────────────────────────────────

@router.get("/stats", response_model=VideoStats)
async def video_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregate stats for the dashboard."""
    base = select(func.count()).select_from(VideoRecord).where(
        VideoRecord.user_id == current_user.id
    )

    total = (await db.execute(base)).scalar() or 0
    posted = (await db.execute(base.where(VideoRecord.status == "posted"))).scalar() or 0
    failed = (await db.execute(base.where(VideoRecord.status == "failed"))).scalar() or 0
    pending = (await db.execute(
        base.where(VideoRecord.status.in_(["pending", "generating"]))
    )).scalar() or 0

    return VideoStats(
        total_generated=total,
        total_posted=posted,
        total_failed=failed,
        total_pending=pending,
    )
