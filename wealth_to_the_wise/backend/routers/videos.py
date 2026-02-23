# filepath: backend/routers/videos.py
"""
Video pipeline router — /api/videos/*

Exposes the CLI auto-pipeline as a REST API for the frontend.

Endpoints
---------
POST /api/videos/generate   — Trigger auto video generation for a topic
GET  /api/videos/history     — Get the user's video upload history
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.models import User
from backend.rate_limit import limiter

logger = logging.getLogger("wealth_to_the_wise.backend.videos")

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
    video_id: str
    title: str
    file_path: str
    url: str


# ── POST /api/videos/generate ────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
@limiter.limit("5/hour")
async def generate_video(
    request: Request,
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Trigger the full-auto pipeline for a given topic.

    This runs the pipeline in a background thread so it doesn't block
    the event loop.  In a real production system this should be a
    Celery / ARQ task queue job.
    """
    logger.info("User %s requested video generation: '%s'", current_user.email, body.topic)

    try:
        # Run the CPU-bound pipeline in a thread pool
        video_id = await asyncio.to_thread(_run_pipeline, body.topic)
    except Exception as e:
        logger.exception("Pipeline failed for topic '%s': %s", body.topic, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Video generation failed: {str(e)}",
        )

    if video_id:
        return GenerateResponse(
            status="completed",
            topic=body.topic,
            message=f"Video uploaded successfully.",
            video_id=video_id,
        )
    else:
        return GenerateResponse(
            status="completed_no_upload",
            topic=body.topic,
            message="Video was generated but upload was skipped (duplicate or limit reached).",
        )


def _run_pipeline(topic: str) -> str | None:
    """Synchronous wrapper around the existing CLI pipeline."""
    # Import here to avoid circular imports and keep Phase 1 code isolated
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    from main import run_full_auto_pipeline

    # The pipeline currently doesn't return video_id cleanly,
    # so we read it from the upload history after completion.
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
                return after[-1].get("video_id")
        except Exception:
            pass

    return None


# ── GET /api/videos/history ──────────────────────────────────────────

@router.get("/history", response_model=list[VideoHistoryItem])
async def video_history(
    current_user: User = Depends(get_current_user),
):
    """Return the upload history from the JSON log.

    NOTE: This reads from the shared output/upload_history.json.
    In a multi-user production system, this should be per-user
    and stored in the database.
    """
    import json

    history_path = OUTPUT_DIR / "upload_history.json"
    if not history_path.exists():
        return []

    try:
        data = json.loads(history_path.read_text())
    except Exception:
        return []

    return [
        VideoHistoryItem(
            video_id=item.get("video_id", ""),
            title=item.get("title", "Untitled"),
            file_path=item.get("file_path", ""),
            url=f"https://www.youtube.com/watch?v={item.get('video_id', '')}",
        )
        for item in data
        if item.get("video_id")
    ]
