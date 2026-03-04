# filepath: backend/routers/schedules.py
"""
Scheduling router — /api/schedules/*

CRUD for posting schedules (automation).

Endpoints
---------
GET    /api/schedules           — List all schedules for current user
POST   /api/schedules           — Create a new schedule
PATCH  /api/schedules/{id}      — Update a schedule (topics, frequency, toggle)
DELETE /api/schedules/{id}      — Delete a schedule
POST   /api/schedules/{id}/run  — Manually trigger the next topic now
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import PostingSchedule, User
from backend.rate_limit import limiter

logger = logging.getLogger("tubevo.backend.schedules")

router = APIRouter(prefix="/api/schedules", tags=["Schedules"])


# ── Frequency → timedelta mapping ────────────────────────────────────

FREQUENCY_DELTAS: dict[str, timedelta] = {
    "daily": timedelta(days=1),
    "every_other_day": timedelta(days=2),
    "twice_weekly": timedelta(days=3, hours=12),  # ~3.5 days
    "weekly": timedelta(days=7),
}

FREQUENCY_LABELS: dict[str, str] = {
    "daily": "Daily",
    "every_other_day": "Every other day",
    "twice_weekly": "Twice a week",
    "weekly": "Weekly",
}

MAX_SCHEDULES_PER_USER = 5


# ── Schemas ──────────────────────────────────────────────────────────

# Prompt-injection patterns — same as GenerateRequest.sanitize_topic in videos.py
_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bsystem\s*:"),
    re.compile(r"(?i)\bassistant\s*:"),
    re.compile(r"(?i)\bignore\s+(all\s+)?previous\b"),
    re.compile(r"(?i)\bforget\s+(all\s+)?instructions\b"),
    re.compile(r"(?i)\byou\s+are\s+now\b"),
    re.compile(r"(?i)\bact\s+as\b"),
]


def _sanitize_topic(v: str) -> str:
    """Sanitize a single topic string (shared with ScheduleCreate/Update)."""
    # Strip control characters
    cleaned = "".join(
        ch for ch in v
        if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                f"Topic '{cleaned[:40]}…' contains disallowed content. "
                "Please enter a simple video topic."
            )

    if len(cleaned) < 3:
        raise ValueError("Each topic must be at least 3 characters.")
    if len(cleaned) > 300:
        raise ValueError("Each topic must be at most 300 characters.")

    return cleaned


_VALID_FREQUENCIES = frozenset(FREQUENCY_DELTAS.keys())


class ScheduleCreate(BaseModel):
    name: str = Field("My Schedule", max_length=200)
    frequency: str = Field("weekly")
    preferred_hour_utc: int = Field(14, ge=0, le=23)
    topics: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in _VALID_FREQUENCIES:
            raise ValueError(
                f"Invalid frequency '{v}'. Choose from: {', '.join(sorted(_VALID_FREQUENCIES))}."
            )
        return v

    @field_validator("topics")
    @classmethod
    def sanitize_topics(cls, v: list[str]) -> list[str]:
        """Sanitize every topic in the list, reject prompt injections."""
        return [_sanitize_topic(t) for t in v]


class ScheduleUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    frequency: str | None = None
    preferred_hour_utc: int | None = Field(None, ge=0, le=23)
    topics: list[str] | None = None
    is_active: bool | None = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_FREQUENCIES:
            raise ValueError(
                f"Invalid frequency '{v}'. Choose from: {', '.join(sorted(_VALID_FREQUENCIES))}."
            )
        return v

    @field_validator("topics")
    @classmethod
    def sanitize_topics(cls, v: list[str] | None) -> list[str] | None:
        """Sanitize every topic in the list, reject prompt injections."""
        if v is None:
            return v
        return [_sanitize_topic(t) for t in v]


class ScheduleResponse(BaseModel):
    id: str
    name: str
    frequency: str
    frequency_label: str
    preferred_hour_utc: int
    topics: list[str]
    topic_index: int
    is_active: bool
    next_run_at: str | None
    last_run_at: str | None
    total_runs: int
    created_at: str
    updated_at: str


# ── Helpers ──────────────────────────────────────────────────────────

def _compute_next_run(frequency: str, preferred_hour: int) -> datetime:
    """Compute the next run timestamp from now."""
    now = datetime.now(timezone.utc)
    delta = FREQUENCY_DELTAS.get(frequency, FREQUENCY_DELTAS["weekly"])

    # Start from today at the preferred hour
    next_run = now.replace(hour=preferred_hour, minute=0, second=0, microsecond=0)

    # If that time already passed today, push to tomorrow + delta - 1 day
    if next_run <= now:
        next_run += timedelta(days=1)

    return next_run


def _serialize_schedule(s: PostingSchedule) -> ScheduleResponse:
    """Convert a PostingSchedule ORM object to a response schema."""
    try:
        topics = json.loads(s.topics_json) if s.topics_json else []
    except (json.JSONDecodeError, TypeError):
        topics = []

    return ScheduleResponse(
        id=s.id,
        name=s.name,
        frequency=s.frequency,
        frequency_label=FREQUENCY_LABELS.get(s.frequency, s.frequency),
        preferred_hour_utc=s.preferred_hour_utc,
        topics=topics,
        topic_index=s.topic_index,
        is_active=s.is_active,
        next_run_at=s.next_run_at.isoformat() if s.next_run_at else None,
        last_run_at=s.last_run_at.isoformat() if s.last_run_at else None,
        total_runs=s.total_runs,
        created_at=s.created_at.isoformat() if s.created_at else "",
        updated_at=s.updated_at.isoformat() if s.updated_at else "",
    )


# ── GET /api/schedules ──────────────────────────────────────────────

@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all posting schedules for the current user."""
    result = await db.execute(
        select(PostingSchedule)
        .where(PostingSchedule.user_id == current_user.id)
        .order_by(PostingSchedule.created_at.desc())
    )
    schedules = result.scalars().all()
    return [_serialize_schedule(s) for s in schedules]


# ── POST /api/schedules ─────────────────────────────────────────────

@router.post("", response_model=ScheduleResponse, status_code=201)
@limiter.limit("10/hour")
async def create_schedule(
    request: Request,
    body: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new posting schedule."""
    # Validate frequency
    if body.frequency not in FREQUENCY_DELTAS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid frequency. Choose from: {', '.join(FREQUENCY_DELTAS.keys())}",
        )

    # Enforce max schedules per user
    count_result = await db.execute(
        select(PostingSchedule).where(PostingSchedule.user_id == current_user.id)
    )
    existing_count = len(count_result.scalars().all())
    if existing_count >= MAX_SCHEDULES_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_SCHEDULES_PER_USER} schedules allowed.",
        )

    # Clean topics
    clean_topics = [t.strip() for t in body.topics if t.strip()]

    schedule = PostingSchedule(
        user_id=current_user.id,
        name=body.name,
        frequency=body.frequency,
        preferred_hour_utc=body.preferred_hour_utc,
        topics_json=json.dumps(clean_topics),
        topic_index=0,
        is_active=body.is_active and len(clean_topics) > 0,
        next_run_at=_compute_next_run(body.frequency, body.preferred_hour_utc) if body.is_active and clean_topics else None,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)

    logger.info("User %s created schedule %s (%s, %d topics)", current_user.email, schedule.id, body.frequency, len(clean_topics))

    return _serialize_schedule(schedule)


# ── PATCH /api/schedules/{schedule_id} ───────────────────────────────

@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing posting schedule."""
    result = await db.execute(
        select(PostingSchedule).where(
            PostingSchedule.id == schedule_id,
            PostingSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    if body.name is not None:
        schedule.name = body.name
    if body.frequency is not None:
        if body.frequency not in FREQUENCY_DELTAS:
            raise HTTPException(status_code=400, detail="Invalid frequency.")
        schedule.frequency = body.frequency
    if body.preferred_hour_utc is not None:
        schedule.preferred_hour_utc = body.preferred_hour_utc
    if body.topics is not None:
        clean_topics = [t.strip() for t in body.topics if t.strip()]
        schedule.topics_json = json.dumps(clean_topics)
        # Reset topic index if topics changed
        if schedule.topic_index >= len(clean_topics):
            schedule.topic_index = 0
    if body.is_active is not None:
        schedule.is_active = body.is_active

    # Recompute next_run_at
    if schedule.is_active:
        topics = json.loads(schedule.topics_json) if schedule.topics_json else []
        if topics:
            schedule.next_run_at = _compute_next_run(
                schedule.frequency, schedule.preferred_hour_utc
            )
        else:
            schedule.is_active = False
            schedule.next_run_at = None
    else:
        schedule.next_run_at = None

    schedule.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(schedule)

    logger.info("User %s updated schedule %s", current_user.email, schedule_id)

    return _serialize_schedule(schedule)


# ── DELETE /api/schedules/{schedule_id} ──────────────────────────────

@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a posting schedule."""
    result = await db.execute(
        select(PostingSchedule).where(
            PostingSchedule.id == schedule_id,
            PostingSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    await db.delete(schedule)
    logger.info("User %s deleted schedule %s", current_user.email, schedule_id)


# ── POST /api/schedules/{schedule_id}/run ────────────────────────────

@router.post("/{schedule_id}/run")
@limiter.limit("5/hour")
async def trigger_schedule_now(
    request: Request,
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the next topic in the schedule immediately.

    This calls the video generation endpoint internally, advancing the
    topic index and updating last_run_at.
    """
    result = await db.execute(
        select(PostingSchedule).where(
            PostingSchedule.id == schedule_id,
            PostingSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found.")

    topics = json.loads(schedule.topics_json) if schedule.topics_json else []
    if not topics:
        raise HTTPException(status_code=400, detail="No topics in this schedule. Add topics first.")

    # Get the current topic
    idx = schedule.topic_index % len(topics)
    topic = topics[idx]

    # Advance index (wraps around)
    schedule.topic_index = (idx + 1) % len(topics)
    schedule.last_run_at = datetime.now(timezone.utc)
    schedule.total_runs += 1

    # Recompute next_run_at
    if schedule.is_active:
        delta = FREQUENCY_DELTAS.get(schedule.frequency, FREQUENCY_DELTAS["weekly"])
        schedule.next_run_at = datetime.now(timezone.utc) + delta

    schedule.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Trigger video generation via the videos router
    from backend.routers.videos import generate_video
    from types import SimpleNamespace

    # Build a minimal request-like object for the rate limiter
    # We'll call the internal generation logic directly instead
    from backend.routers.videos import (
        GenerateRequest,
        _enforce_plan_limit,
        _run_pipeline_background,
    )
    from backend.models import OAuthToken, UserApiKeys
    from backend.encryption import decrypt_or_raise
    import asyncio

    # Enforce plan limits
    await _enforce_plan_limit(current_user, db)

    # Fetch user's API keys
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
    pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""

    if not openai_key:
        raise HTTPException(status_code=400, detail="Please add your OpenAI API key in Settings first.")
    if not elevenlabs_key:
        raise HTTPException(status_code=400, detail="Please add your ElevenLabs API key in Settings first.")

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        # Video production preferences (match scheduler_worker / generate_video)
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
    }

    # Fetch YouTube tokens
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = oauth_result.scalar_one_or_none()
    yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token") if oauth_token and oauth_token.access_token else None
    yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token") if oauth_token and oauth_token.refresh_token else None

    # Create video record
    from backend.models import VideoRecord
    record = VideoRecord(
        user_id=current_user.id,
        topic=topic,
        title=topic,
        status="generating",
    )
    db.add(record)
    await db.flush()
    record_id = record.id

    # Fire and forget
    asyncio.create_task(
        _run_pipeline_background(
            record_id=record_id,
            topic=topic,
            user_id=current_user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )

    logger.info(
        "Schedule %s triggered manually: topic='%s' (index %d/%d)",
        schedule_id, topic, idx, len(topics),
    )

    return {
        "message": f"Video generation started for: {topic}",
        "topic": topic,
        "video_id": record_id,
        "next_topic_index": schedule.topic_index,
    }
