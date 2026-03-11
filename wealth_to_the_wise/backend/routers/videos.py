"""
Video pipeline router — /api/videos/*

Exposes the CLI auto-pipeline as a REST API for the frontend.

Endpoints
---------
POST /api/videos/generate      — Trigger auto video generation for a topic
GET  /api/videos/{id}/status   — Poll the status of a generation job
GET  /api/videos/history       — Get the user's video upload history
GET  /api/videos/stats         — Dashboard stats for the current user
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import threading
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import async_session_factory, get_db
from backend.encryption import decrypt, decrypt_or_raise, DecryptionFailedError
from backend.events import emit_event
from backend.models import Channel, ContentMemory, ContentPerformance, OAuthToken, User, UserApiKeys, UserPreferences, VideoRecord
from backend.models import AdminEvent, PlatformError, RevenueEvent, ThumbExperiment, ThumbVariant, TrendAlert
from backend.rate_limit import limiter
from backend.utils import PLAN_MONTHLY_LIMITS

logger = logging.getLogger("tubevo.backend.videos")

# ── Lazy import of PipelineError at module level (safe — pure Python file)
# This lets the except clause classify typed errors from the pipeline modules.
try:
    _project_root = str(Path(__file__).resolve().parent.parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from pipeline_errors import PipelineError
except ImportError:
    # Graceful fallback — treat all errors as unclassified
    PipelineError = None  # type: ignore[assignment,misc]

router = APIRouter(prefix="/api/videos", tags=["Videos"])

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Maximum time a pipeline is allowed to run before we consider it dead.
PIPELINE_TIMEOUT_SECONDS = 10 * 60  # 10 minutes
# If a record has been "generating" for longer than this, mark it failed.
STALE_JOB_MINUTES = 15

# ── Concurrency limiter ─────────────────────────────────────────────
# Cap simultaneous video generations to avoid OOM from multiple FFmpeg
# processes + OpenAI/ElevenLabs streams hitting at once.
# Railway single-container: default to 1 to prevent OOM kills.
MAX_CONCURRENT_PIPELINES = int(os.environ.get("MAX_CONCURRENT_PIPELINES", "1"))
_pipeline_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)

# ── Circuit breaker ─────────────────────────────────────────────────
# If the last N consecutive video attempts for a user ALL failed,
# stop auto-generating to prevent burning API credits on a known-bad
# environment (e.g. FFmpeg OOM on Railway).  Manual "Generate" from the
# UI still works — only scheduler / trend radar auto-generation is paused.
CIRCUIT_BREAKER_THRESHOLD = 3  # 3 consecutive failures → pause auto-gen

# ── Per-user in-flight tracking ─────────────────────────────────────
# Prevents the same user from having multiple videos generating at once
# (scheduler + trend radar + manual could all collide).
# Tracks user_id → record_id of the video currently generating.
_user_inflight: dict[str, str] = {}
_user_inflight_lock = asyncio.Lock()

# YouTube video category ID (22 = "People & Blogs")
DEFAULT_VIDEO_CATEGORY = os.environ.get("DEFAULT_VIDEO_CATEGORY", "22")

# ── In-memory progress tracker (Phase 6) ────────────────────────────
# Keyed by record_id → { "step": str, "pct": int, "started_at": float }
# This avoids hammering the DB on every sub-step update.
_progress_store: dict[str, dict] = {}

# ── Plan-based monthly video limits ─────────────────────────────────
# Canonical definition lives in backend.utils — imported above.

# ── Schemas ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=300)
    auto: bool = True  # full-auto by default

    @field_validator("topic")
    @classmethod
    def sanitize_topic(cls, v: str) -> str:
        """Strip control characters, collapse whitespace, and reject
        obvious prompt-injection attempts."""
        import re
        import unicodedata

        # Remove control characters (except newline/tab which we'll collapse)
        cleaned = "".join(
            ch for ch in v
            if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
        )
        # Collapse all whitespace to single spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Reject if the "topic" looks like a prompt-injection attempt:
        # multi-line system/assistant role overrides, or very long blocks
        # of instructions.
        _injection_patterns = [
            r"(?i)\bsystem\s*:",
            r"(?i)\bassistant\s*:",
            r"(?i)\bignore\s+(all\s+)?previous\b",
            r"(?i)\bforget\s+(all\s+)?instructions\b",
            r"(?i)\byou\s+are\s+now\b",
            r"(?i)\bact\s+as\b",
        ]
        for pattern in _injection_patterns:
            if re.search(pattern, cleaned):
                raise ValueError(
                    "Topic contains disallowed content. "
                    "Please enter a simple video topic."
                )

        if len(cleaned) < 3:
            raise ValueError("Topic must be at least 3 characters after cleanup.")

        return cleaned


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
    srt_path: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    thumbnail_path: str | None = None
    error_message: str | None = None
    error_category: str | None = None
    progress_step: str | None = None
    progress_pct: int = 0
    has_script: bool = False
    # Multi-format export
    portrait_path: str | None = None
    square_path: str | None = None
    # Bulk generation
    batch_id: str | None = None
    batch_position: int | None = None
    created_at: str
    updated_at: str


class VideoStats(BaseModel):
    total_generated: int
    total_posted: int
    total_failed: int
    total_pending: int
    monthly_used: int = 0
    monthly_limit: int = 1
    plan: str = "free"


# ── Script Refinement Schemas ────────────────────────────────────────

class GenerateScriptRequest(BaseModel):
    """Phase 1: Generate script only (fast, ~15s). No render."""
    topic: str = Field(..., min_length=3, max_length=300)
    tone: str | None = Field(None, description="One of: educational, energetic, dramatic, humorous, documentary")
    audience_level: str | None = Field(None, description="One of: beginner, general, expert")
    emphasis_keywords: list[str] | None = Field(None, max_length=10, description="Keywords to emphasize")
    humor: bool = False

    @field_validator("topic")
    @classmethod
    def sanitize_topic(cls, v: str) -> str:
        return GenerateRequest.sanitize_topic(v)

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str | None) -> str | None:
        if v is not None and v not in ("educational", "energetic", "dramatic", "humorous", "documentary"):
            raise ValueError("tone must be one of: educational, energetic, dramatic, humorous, documentary")
        return v

    @field_validator("audience_level")
    @classmethod
    def validate_audience(cls, v: str | None) -> str | None:
        if v is not None and v not in ("beginner", "general", "expert"):
            raise ValueError("audience_level must be one of: beginner, general, expert")
        return v


class GenerateScriptResponse(BaseModel):
    script: str
    metadata: dict
    read_time: dict
    topic: str
    video_id: str


class HookVariationsRequest(BaseModel):
    script: str = Field(..., min_length=50)
    topic: str = Field(..., min_length=3, max_length=300)


class HookVariationsResponse(BaseModel):
    hooks: list[str]
    current_hook: str


class RegenerateParagraphRequest(BaseModel):
    script: str = Field(..., min_length=50)
    topic: str = Field(..., min_length=3, max_length=300)
    paragraph_index: int = Field(..., ge=0)


class RegenerateParagraphResponse(BaseModel):
    new_paragraph: str
    paragraph_index: int


class ApplyToneRequest(BaseModel):
    script: str = Field(..., min_length=50)
    tone: str

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        if v not in ("educational", "energetic", "dramatic", "humorous", "documentary"):
            raise ValueError("tone must be one of: educational, energetic, dramatic, humorous, documentary")
        return v


class ApplyToneResponse(BaseModel):
    script: str
    tone: str
    read_time: dict


class RenderVideoRequest(BaseModel):
    """Phase 2: Take a finalized script and render the full video."""
    video_id: str = Field(..., description="The video_id from generate-script")
    script: str = Field(..., min_length=50)
    topic: str = Field(..., min_length=3, max_length=300)
    voice_style: str | None = Field("storyteller", description="Voice style preset key")
    metadata: dict | None = Field(None, description="Override metadata (title/desc/tags)")

    @field_validator("voice_style")
    @classmethod
    def validate_voice_style(cls, v: str | None) -> str | None:
        valid = ("storyteller", "documentary", "energetic", "calm", "dramatic")
        if v is not None and v not in valid:
            raise ValueError(f"voice_style must be one of: {', '.join(valid)}")
        return v


class VoiceStylesResponse(BaseModel):
    styles: list[dict]


# ── Bulk Generation Schemas (Phase 3) ────────────────────────────────

# Per-plan max topics per batch
BULK_MAX_TOPICS: dict[str, int] = {
    "free": 0,       # Free plan can't bulk generate
    "starter": 5,
    "pro": 10,
    "agency": 20,
}


class BulkGenerateRequest(BaseModel):
    topics: list[str] = Field(..., min_length=2, max_length=20)

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: list[str]) -> list[str]:
        """Sanitize each topic and reject duplicates."""
        import re
        import unicodedata

        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in v:
            t = "".join(
                ch for ch in raw
                if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
            )
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) < 3:
                raise ValueError(f"Topic too short after cleanup: '{raw[:50]}'")
            if len(t) > 300:
                raise ValueError(f"Topic too long (max 300 chars): '{t[:50]}…'")
            lower = t.lower()
            if lower in seen:
                raise ValueError(f"Duplicate topic: '{t[:50]}'")
            seen.add(lower)
            cleaned.append(t)
        return cleaned


class BulkGenerateResponse(BaseModel):
    batch_id: str
    total: int
    queued: int
    skipped: int
    message: str
    video_ids: list[str]


class BulkStatusItem(BaseModel):
    id: str
    topic: str
    status: str
    position: int
    progress_step: str | None = None
    progress_pct: int = 0
    error_message: str | None = None
    title: str | None = None


class BulkStatusResponse(BaseModel):
    batch_id: str
    total: int
    completed: int
    failed: int
    generating: int
    queued: int
    items: list[BulkStatusItem]


# ── GET /api/videos/voice-styles — List available voice styles ────────

@router.get("/voice-styles", response_model=VoiceStylesResponse)
async def list_voice_styles(
    current_user: User = Depends(get_current_user),
):
    """Return available voice style presets for the Script Refiner."""
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from voiceover import VOICE_STYLE_PRESETS
    styles = [
        {
            "key": key,
            "label": preset["label"],
            "description": preset["description"],
        }
        for key, preset in VOICE_STYLE_PRESETS.items()
    ]
    return VoiceStylesResponse(styles=styles)


# ── POST /api/videos/generate-script — Phase 1: script only ─────────

@router.post("/generate-script", response_model=GenerateScriptResponse)
@limiter.limit("10/hour")
async def generate_script_only(
    request: Request,
    body: GenerateScriptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a script and metadata without starting the render pipeline.

    This is the fast Phase 1 of the two-phase creation flow.
    Returns the script for editing in the Script Refiner UI.
    """
    logger.info("User %s requested script generation: '%s'", current_user.email, body.topic)

    # ── Fetch the user's OpenAI key ──────────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    except DecryptionFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Your saved API keys could not be decrypted ({exc.field_label}). Please re-enter them in Settings → API Keys.",
        )

    if not openai_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your OpenAI API key in Settings → API Keys before creating videos.",
        )

    # ── Enforce plan limit ───────────────────────────────────────────
    await _enforce_plan_limit(current_user, db)

    # ── Fetch user preferences ───────────────────────────────────────
    user_prefs_dict: dict = {}
    try:
        prefs_stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.id)
        prefs_row = (await db.execute(prefs_stmt)).scalar_one_or_none()
        if prefs_row:
            import json as _json
            user_prefs_dict = {
                "niches": _json.loads(prefs_row.niches_json) if prefs_row.niches_json else [],
                "tone_style": prefs_row.tone_style,
                "target_audience": prefs_row.target_audience,
                "channel_goal": prefs_row.channel_goal,
            }
    except Exception:
        pass

    # ── Fetch performance profile ────────────────────────────────────
    perf_profile_dict: dict = {}
    try:
        perf_stmt = (
            select(ContentPerformance)
            .where(ContentPerformance.user_id == current_user.id)
            .order_by(ContentPerformance.created_at.desc())
            .limit(50)
        )
        perf_rows = (await db.execute(perf_stmt)).scalars().all()
        if perf_rows:
            raw_rows = [
                {
                    "title_style_used": getattr(r, "title_style_used", None),
                    "thumbnail_concept_used": r.thumbnail_concept_used,
                    "engagement_score": r.engagement_score,
                    "ctr_pct": r.ctr_pct,
                    "avg_view_duration_pct": r.avg_view_duration_pct,
                }
                for r in perf_rows
            ]
            from backend.adaptive_engine import get_user_performance_profile, profile_to_dict
            profile = get_user_performance_profile(raw_rows)
            perf_profile_dict = profile_to_dict(profile)
    except Exception:
        pass

    # ── Create a "pending" video record (will be updated on render) ──
    record = VideoRecord(
        user_id=current_user.id,
        topic=body.topic,
        title=body.topic,
        status="pending",
    )
    db.add(record)
    await db.commit()
    record_id = record.id

    # ── Generate script + metadata in a thread (sync OpenAI calls) ───
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    import script_generator

    try:
        script_kwargs: dict = {
            "api_key": openai_key,
        }
        if user_prefs_dict:
            script_kwargs["user_preferences"] = user_prefs_dict
        if perf_profile_dict:
            script_kwargs["performance_profile"] = perf_profile_dict
        if body.tone:
            script_kwargs["tone"] = body.tone
        if body.audience_level:
            script_kwargs["audience_level"] = body.audience_level
        if body.emphasis_keywords:
            script_kwargs["emphasis_keywords"] = body.emphasis_keywords
        if body.humor:
            script_kwargs["humor"] = body.humor

        script_text = await asyncio.to_thread(
            script_generator.generate_script, body.topic, **script_kwargs
        )

        metadata = await asyncio.to_thread(
            script_generator.generate_metadata, script_text, body.topic,
            api_key=openai_key,
            user_preferences=user_prefs_dict if user_prefs_dict else None,
            performance_profile=perf_profile_dict if perf_profile_dict else None,
        )

        read_time = script_generator.estimate_read_time(script_text)

    except Exception as e:
        # Mark the record as failed
        record.status = "failed"
        record.error_message = str(e)[:2000]
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Script generation failed: {str(e)[:300]}",
        )

    # ── Save script to the record ────────────────────────────────────
    record.script_text = script_text
    record.title = metadata.get("title", body.topic)
    import json as _json
    try:
        record.metadata_json = _json.dumps(metadata)
    except Exception:
        pass
    await db.commit()

    return GenerateScriptResponse(
        script=script_text,
        metadata=metadata,
        read_time=read_time,
        topic=body.topic,
        video_id=record_id,
    )


# ── POST /api/videos/generate-hooks — Hook variation generator ──────

@router.post("/generate-hooks", response_model=HookVariationsResponse)
@limiter.limit("20/hour")
async def generate_hooks(
    request: Request,
    body: HookVariationsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate 3 alternate opening hooks for a script."""
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    except DecryptionFailedError:
        raise HTTPException(status_code=400, detail="API key decryption failed. Re-enter in Settings.")
    if not openai_key:
        raise HTTPException(status_code=400, detail="OpenAI API key required.")

    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import script_generator

    try:
        hooks = await asyncio.to_thread(
            script_generator.generate_hook_variations,
            body.script, body.topic, api_key=openai_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hook generation failed: {str(e)[:300]}")

    # Extract current hook
    paragraphs = [p.strip() for p in body.script.split("\n\n") if p.strip()]
    current_hook = paragraphs[0] if paragraphs else body.script[:200]

    return HookVariationsResponse(hooks=hooks, current_hook=current_hook)


# ── POST /api/videos/regenerate-paragraph ────────────────────────────

@router.post("/regenerate-paragraph", response_model=RegenerateParagraphResponse)
@limiter.limit("30/hour")
async def regenerate_paragraph_endpoint(
    request: Request,
    body: RegenerateParagraphRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate a single paragraph of a script."""
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    except DecryptionFailedError:
        raise HTTPException(status_code=400, detail="API key decryption failed. Re-enter in Settings.")
    if not openai_key:
        raise HTTPException(status_code=400, detail="OpenAI API key required.")

    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import script_generator

    try:
        new_para = await asyncio.to_thread(
            script_generator.regenerate_paragraph,
            body.script, body.paragraph_index, body.topic, api_key=openai_key,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Paragraph regeneration failed: {str(e)[:300]}")

    return RegenerateParagraphResponse(new_paragraph=new_para, paragraph_index=body.paragraph_index)


# ── POST /api/videos/apply-tone — Rewrite script in a different tone ─

@router.post("/apply-tone", response_model=ApplyToneResponse)
@limiter.limit("15/hour")
async def apply_tone_endpoint(
    request: Request,
    body: ApplyToneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rewrite a script in a different tone (educational, energetic, etc.)."""
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
    except DecryptionFailedError:
        raise HTTPException(status_code=400, detail="API key decryption failed. Re-enter in Settings.")
    if not openai_key:
        raise HTTPException(status_code=400, detail="OpenAI API key required.")

    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import script_generator

    try:
        rewritten = await asyncio.to_thread(
            script_generator.apply_tone_rewrite,
            body.script, body.tone, api_key=openai_key,
        )
        read_time = script_generator.estimate_read_time(rewritten)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tone rewrite failed: {str(e)[:300]}")

    return ApplyToneResponse(script=rewritten, tone=body.tone, read_time=read_time)


# ── POST /api/videos/render — Phase 2: Render the video ─────────────

@router.post("/render", response_model=GenerateResponse)
@limiter.limit("5/hour")
async def render_video(
    request: Request,
    body: RenderVideoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase 2: Take a finalized script and kick off the full render pipeline.

    Expects a video_id from the generate-script phase. The record must exist
    and belong to the current user.
    """
    logger.info("User %s requested video render for record %s", current_user.email, body.video_id)

    # ── Verify the record exists and belongs to the user ─────────────
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == body.video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video record not found.")
    if record.status == "generating":
        raise HTTPException(status_code=409, detail="This video is already being rendered.")
    if record.status in ("completed", "posted"):
        raise HTTPException(status_code=409, detail="This video has already been rendered.")

    # ── Fetch user API keys ──────────────────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
        elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
        pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""
        pixabay_key = decrypt_or_raise(user_keys.pixabay_api_key, field="pixabay_api_key") if user_keys and getattr(user_keys, "pixabay_api_key", None) else ""
    except DecryptionFailedError as exc:
        raise HTTPException(status_code=400, detail=f"API key decryption failed ({exc.field_label}). Re-enter in Settings.")

    if not openai_key:
        raise HTTPException(status_code=400, detail="OpenAI API key required.")
    if not elevenlabs_key:
        raise HTTPException(status_code=400, detail="ElevenLabs API key required.")

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        "pixabay_api_key": pixabay_key,
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
        # Pass the voice style for the render pipeline
        "_voice_style": body.voice_style or "storyteller",
        # Pass the refined script so the pipeline doesn't regenerate it
        "_refined_script": body.script,
        "_refined_metadata": body.metadata,
        # Plan-based quality profile
        "_plan": current_user.plan or "free",
    }

    # ── Fetch YouTube OAuth tokens ───────────────────────────────────
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = oauth_result.scalar_one_or_none()
    yt_access_token: str | None = None
    yt_refresh_token: str | None = None
    if oauth_token:
        try:
            yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token")
            yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token")
        except DecryptionFailedError:
            yt_access_token = None
            yt_refresh_token = None

    # ── Per-user in-flight guard ─────────────────────────────────────
    async with _user_inflight_lock:
        if current_user.id in _user_inflight:
            raise HTTPException(status_code=409, detail="You already have a video rendering. Please wait.")

    # ── Update the record to "generating" ────────────────────────────
    record.status = "generating"
    record.script_text = body.script
    record.title = (body.metadata or {}).get("title", record.title)
    if body.metadata:
        import json as _json
        try:
            record.metadata_json = _json.dumps(body.metadata)
        except Exception:
            pass
    record.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # ── Admin event ──────────────────────────────────────────────────
    async with async_session_factory() as ev_db:
        await emit_event(ev_db, "video_started", user_id=current_user.id, video_id=record.id, meta={"topic": body.topic})
        await ev_db.commit()

    # ── Fire off the render pipeline ─────────────────────────────────
    asyncio.create_task(
        _run_pipeline_background(
            record_id=record.id,
            topic=body.topic,
            user_id=current_user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )

    return GenerateResponse(
        status="generating",
        topic=body.topic,
        message="Video render started! This takes 2-4 minutes.",
        video_id=record.id,
    )


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

    Creates a VideoRecord in the database, kicks off the pipeline as a
    fire-and-forget asyncio task, and returns immediately so the HTTP
    request doesn't time out.
    The frontend can poll GET /api/videos/{id}/status for progress.
    """
    logger.info("User %s requested video generation: '%s'", current_user.email, body.topic)

    # ── Fetch the user's API keys (BYOK) ─────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    # Decrypt stored keys (encrypted at rest via Fernet)
    # Use decrypt_or_raise for pipeline-critical keys so a silent '' cannot
    # propagate into external API calls.
    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
        elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
        pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""
        pixabay_key = decrypt_or_raise(user_keys.pixabay_api_key, field="pixabay_api_key") if user_keys and getattr(user_keys, "pixabay_api_key", None) else ""
    except DecryptionFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Your saved API keys could not be decrypted ({exc.field_label}). "
                "Please re-enter them in Settings → API Keys."
            ),
        )

    if not openai_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your OpenAI API key in Settings → API Keys before generating videos.",
        )
    if not elevenlabs_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your ElevenLabs API key in Settings → API Keys before generating videos.",
        )

    # Pack the user's decrypted keys + video preferences for the pipeline
    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        "pixabay_api_key": pixabay_key,
        # Phase 4 & 5 video production preferences
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
        # Plan-based quality profile
        "_plan": current_user.plan or "free",
    }

    # ── Enforce plan-based monthly video limits ──────────────────────
    await _enforce_plan_limit(current_user, db)

    # ── Fetch the user's YouTube OAuth tokens (needed for upload) ────
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = result.scalar_one_or_none()

    # We still allow generation without YouTube connected —
    # the video will be built but not uploaded.
    # If the stored token can't be decrypted (e.g. JWT_SECRET_KEY rotated),
    # treat it the same as "no YouTube connected" instead of crashing.
    yt_access_token: str | None = None
    yt_refresh_token: str | None = None
    if oauth_token:
        try:
            yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token")
            yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token")
        except DecryptionFailedError:
            logger.warning(
                "YouTube OAuth token for user %s could not be decrypted — "
                "video will be generated but not uploaded. "
                "User should re-link their YouTube account.",
                current_user.email,
            )
            yt_access_token = None
            yt_refresh_token = None

    # ── Per-user in-flight guard ────────────────────────────────────
    # Prevent the same user from having multiple videos generating at once.
    # Check both in-memory tracker AND DB for active "generating" jobs.
    async with _user_inflight_lock:
        if current_user.id in _user_inflight:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a video generating. Please wait for it to finish before starting another.",
            )

    # Also check DB for generating jobs (survives container restarts)
    active_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.status == "generating",
        )
    )
    active_count = (await db.execute(active_stmt)).scalar() or 0
    if active_count > 0:
        # Clean up stale ones first, then re-check
        await _cleanup_stale_jobs(current_user.id, db)
        active_count = (await db.execute(active_stmt)).scalar() or 0
        if active_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a video generating. Please wait for it to finish before starting another.",
            )

    # ── Create a "generating" record and commit immediately ──────────
    # We commit *before* spawning the background task so the record is
    # guaranteed to exist in the DB when the task tries to read it.
    record = VideoRecord(
        user_id=current_user.id,
        topic=body.topic,
        title=body.topic,  # will be updated by the pipeline
        status="generating",
    )
    db.add(record)
    await db.commit()
    record_id = record.id
    logger.info("Created VideoRecord %s for user %s", record_id, current_user.email)

    # ── Admin event: video_started ───────────────────────────────────
    async with async_session_factory() as ev_db:
        await emit_event(ev_db, "video_started", user_id=current_user.id, video_id=record_id, meta={"topic": body.topic})
        await ev_db.commit()

    # ── Kick off the pipeline as a fire-and-forget task ──────────────
    # Using asyncio.create_task instead of BackgroundTasks so the task
    # isn't tied to the HTTP request lifecycle.
    asyncio.create_task(
        _run_pipeline_background(
            record_id=record_id,
            topic=body.topic,
            user_id=current_user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )

    return GenerateResponse(
        status="generating",
        topic=body.topic,
        message="Video generation started! This takes 2-5 minutes. Check back shortly.",
        video_id=record_id,
    )


# ── Background pipeline runner ───────────────────────────────────────

async def _run_pipeline_background(
    *,
    record_id: str,
    topic: str,
    user_id: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
) -> None:
    """Run the full auto pipeline in a background thread, then update the DB.

    Uses its own DB session (the request session is already closed).
    Wraps the synchronous pipeline in asyncio.to_thread with a timeout.

    Acquires ``_pipeline_semaphore`` to limit concurrent FFmpeg / AI
    calls and prevent OOM on Railway's single container.
    """
    logger.info(
        "Background pipeline queued for record %s (semaphore: %d/%d available)",
        record_id,
        _pipeline_semaphore._value,  # noqa: SLF001 — just for logging
        MAX_CONCURRENT_PIPELINES,
    )

    # Register this user as having an in-flight video
    async with _user_inflight_lock:
        _user_inflight[user_id] = record_id

    # Initialise in-memory progress tracker
    _progress_store[record_id] = {"step": "Queued — waiting for slot…", "pct": 0, "started_at": time.time()}

    try:
        async with _pipeline_semaphore:
            logger.info("Background pipeline STARTING for record %s (slot acquired)", record_id)
            _progress_store[record_id]["step"] = "Starting…"
            await _run_pipeline_inner(
                record_id=record_id,
                topic=topic,
                user_id=user_id,
                user_api_keys=user_api_keys,
                yt_access_token=yt_access_token,
                yt_refresh_token=yt_refresh_token,
            )
    finally:
        # Always unregister the user from in-flight tracking
        async with _user_inflight_lock:
            _user_inflight.pop(user_id, None)
        logger.info("Background pipeline FINISHED for record %s — user slot freed", record_id)


async def _run_pipeline_inner(
    *,
    record_id: str,
    topic: str,
    user_id: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
) -> None:
    """Inner pipeline logic — called once the semaphore slot is acquired."""

    # ── Phase 7: Fetch past titles from content memory ───────────────
    past_titles: list[str] = []
    try:
        async with async_session_factory() as db:
            cm_stmt = (
                select(ContentMemory.title)
                .where(ContentMemory.user_id == user_id)
                .order_by(ContentMemory.created_at.desc())
                .limit(15)
            )
            cm_rows = (await db.execute(cm_stmt)).scalars().all()
            past_titles = [t for t in cm_rows if t]  # filter empty
            logger.info("Phase 7: loaded %d past titles from content memory", len(past_titles))
    except Exception as cm_err:
        logger.warning("Phase 7: content memory query failed (non-fatal): %s", cm_err)

    # Inject past titles into user_api_keys dict for the sync pipeline
    user_api_keys["_past_titles"] = past_titles

    # ── Fetch user preferences for adaptive generation ───────────────
    user_prefs_dict: dict = {}
    try:
        async with async_session_factory() as db:
            prefs_stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
            prefs_row = (await db.execute(prefs_stmt)).scalar_one_or_none()
            if prefs_row:
                import json as _json
                user_prefs_dict = {
                    "niches": _json.loads(prefs_row.niches_json) if prefs_row.niches_json else [],
                    "tone_style": prefs_row.tone_style,
                    "target_audience": prefs_row.target_audience,
                    "channel_goal": prefs_row.channel_goal,
                    "posting_frequency": prefs_row.posting_frequency,
                }
                logger.info("Loaded user preferences: niches=%s goal=%s", user_prefs_dict["niches"], user_prefs_dict["channel_goal"])
    except Exception as prefs_err:
        logger.warning("User preferences fetch failed (non-fatal, using defaults): %s", prefs_err)

    user_api_keys["_user_preferences"] = user_prefs_dict

    # ── Fetch performance profile for adaptive learning ──────────────
    perf_profile_dict: dict = {}
    try:
        async with async_session_factory() as db:
            perf_stmt = (
                select(ContentPerformance)
                .where(ContentPerformance.user_id == user_id)
                .order_by(ContentPerformance.created_at.desc())
                .limit(50)
            )
            perf_rows = (await db.execute(perf_stmt)).scalars().all()
            if perf_rows:
                raw_rows = [
                    {
                        "title_style_used": getattr(r, "title_style_used", None),
                        "thumbnail_concept_used": r.thumbnail_concept_used,
                        "engagement_score": r.engagement_score,
                        "ctr_pct": r.ctr_pct,
                        "avg_view_duration_pct": r.avg_view_duration_pct,
                    }
                    for r in perf_rows
                ]
                from backend.adaptive_engine import get_user_performance_profile, profile_to_dict
                profile = get_user_performance_profile(raw_rows)
                perf_profile_dict = profile_to_dict(profile)
                logger.info("Adaptive profile loaded: %d points, active=%s, hook=%s, title=%s, thumb=%s",
                            profile.total_data_points, profile.adaptation_active,
                            profile.hook_mode, profile.recommended_title_style,
                            profile.recommended_thumbnail_style)
    except Exception as perf_err:
        logger.warning("Adaptive profile fetch failed (non-fatal, using defaults): %s", perf_err)

    user_api_keys["_performance_profile"] = perf_profile_dict

    result: dict
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_pipeline_sync,
                topic=topic,
                user_api_keys=user_api_keys,
                yt_access_token=yt_access_token,
                yt_refresh_token=yt_refresh_token,
                record_id=record_id,
            ),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Pipeline timed out after %ds for record %s", PIPELINE_TIMEOUT_SECONDS, record_id)
        result = {"error": f"Video generation timed out after {PIPELINE_TIMEOUT_SECONDS // 60} minutes.", "_error_type": "pipeline", "_error_category": "timeout", "_stack": None}
    except Exception as e:
        tb = traceback.format_exc()
        # Phase 8: mask any API keys that might appear in tracebacks
        from backend.utils import mask_secrets
        safe_tb = mask_secrets(tb)
        safe_msg = mask_secrets(str(e))
        logger.error("Pipeline background task failed for record %s: %s\n%s", record_id, safe_msg, safe_tb)
        # Phase 2: classify error if it's a typed PipelineError
        _err_category = "unknown"
        if PipelineError is not None and isinstance(e, PipelineError):
            _err_category = e.category
            # Store user-friendly message + technical detail for admin debugging
            _technical = mask_secrets(str(e))
            safe_msg = f"{e.user_hint}\n\n[Detail: {_technical}]" if _technical != e.user_hint else e.user_hint
        result = {"error": safe_msg, "_error_type": "pipeline", "_error_category": _err_category, "_stack": safe_tb}

    # ── Update the DB record with results ────────────────────────────
    try:
        async with async_session_factory() as db:
            stmt = select(VideoRecord).where(VideoRecord.id == record_id)
            row = (await db.execute(stmt)).scalar_one_or_none()
            if not row:
                logger.error("VideoRecord %s not found after pipeline!", record_id)
                return

            if "error" in result:
                row.status = "failed"
                # Phase 8: sanitise error message before DB storage
                from backend.utils import mask_secrets as _mask
                row.error_message = _mask(result["error"])[:2000]
                # Phase 2: store typed error category
                row.error_category = result.get("_error_category", "unknown")
            else:
                # ── Persist artifacts to durable storage BEFORE marking success ──
                from backend.storage import get_storage, StorageUploadError
                try:
                    _store = get_storage()

                    _file_path = result.get("file_path")
                    if _file_path and Path(_file_path).is_file():
                        _artifact_key = f"videos/{record_id}/{Path(_file_path).name}"
                        _artifact_url = _store.upload(_artifact_key, Path(_file_path))
                        result["_artifact_url"] = _artifact_url
                        logger.info("Artifact stored: %s → %s", _artifact_key, _artifact_url)

                    _thumb_path = result.get("thumbnail_path")
                    if _thumb_path and Path(_thumb_path).is_file():
                        _thumb_key = f"thumbnails/{record_id}/{Path(_thumb_path).name}"
                        _store.upload(_thumb_key, Path(_thumb_path))
                        logger.info("Thumbnail stored: %s", _thumb_key)

                except StorageUploadError as _sup_err:
                    # Storage upload failed → mark the job as failed so it doesn't
                    # consume the user's quota.
                    logger.error(
                        "Artifact upload failed for record %s: %s", record_id, _sup_err,
                    )
                    row.status = "failed"
                    row.error_message = f"Artifact storage failed: {_sup_err}"[:2000]
                    row.error_category = "external_service"
                    row.updated_at = datetime.now(timezone.utc)
                    await db.commit()

                    # Capture the error for the admin dashboard
                    from backend.errors import capture_error as _cap_err
                    await _cap_err(
                        db, "storage",
                        message=str(_sup_err)[:2000],
                        user_id=user_id,
                        video_id=record_id,
                    )
                    await db.commit()
                    return
                except Exception as _store_warn:
                    # Non-StorageUploadError: log but don't block success
                    # (e.g. STORAGE_PROVIDER=local in dev — files already on disk)
                    logger.warning("Artifact storage skipped (non-fatal): %s", _store_warn)

                # ── Now set the success status ───────────────────────
                if result.get("youtube_video_id"):
                    row.status = "posted"
                    row.title = result.get("title", topic)
                    row.file_path = result.get("file_path")
                    row.srt_path = result.get("srt_path")
                    row.thumbnail_path = result.get("thumbnail_path")
                    row.youtube_video_id = result["youtube_video_id"]
                    row.youtube_url = f"https://www.youtube.com/watch?v={result['youtube_video_id']}"
                    row.published_at = datetime.now(timezone.utc)  # Analytics: mark publish time
                elif result.get("file_path"):
                    row.status = "completed"
                    row.title = result.get("title", topic)
                    row.file_path = result.get("file_path")
                    row.srt_path = result.get("srt_path")
                    row.thumbnail_path = result.get("thumbnail_path")
                else:
                    row.status = "completed"
                    row.title = result.get("title", topic)

            row.updated_at = datetime.now(timezone.utc)

            # ── Persist admin-visible artefacts ──────────────────────
            import json as _json
            if result.get("_script_text"):
                row.script_text = result["_script_text"]
            if result.get("_metadata"):
                try:
                    row.metadata_json = _json.dumps(result["_metadata"])
                except Exception:
                    pass
            if result.get("_voice_id"):
                row.voice_id = result["_voice_id"]
            if result.get("_pipeline_steps"):
                try:
                    row.pipeline_log_json = _json.dumps(result["_pipeline_steps"])
                except Exception:
                    pass

            await db.commit()
            logger.info("Updated VideoRecord %s → status=%s", record_id, row.status)

            # ── Admin events: video outcome ──────────────────────────
            if row.status == "failed":
                await emit_event(db, "video_failed", user_id=user_id, video_id=record_id, meta={"error": (row.error_message or "")[:200]})
                # ── Capture to platform_errors table ─────────────────
                from backend.errors import capture_error
                await capture_error(
                    db,
                    result.get("_error_type", "pipeline"),
                    message=row.error_message or "Unknown pipeline error",
                    stack=result.get("_stack"),
                    user_id=user_id,
                    video_id=record_id,
                )
            elif row.status == "posted":
                await emit_event(db, "video_completed", user_id=user_id, video_id=record_id, meta={"title": row.title})
                await emit_event(db, "upload_success", user_id=user_id, video_id=record_id, meta={"youtube_id": row.youtube_video_id})
            elif row.status == "completed":
                await emit_event(db, "video_completed", user_id=user_id, video_id=record_id, meta={"title": row.title})
            await db.commit()

            # ── Persist refreshed YouTube access token back to DB ────
            _new_yt_token = result.get("_refreshed_yt_access_token")
            if _new_yt_token:
                try:
                    from backend.encryption import encrypt as _encrypt
                    yt_stmt = select(OAuthToken).where(
                        OAuthToken.user_id == user_id,
                        OAuthToken.provider == "google",
                    )
                    yt_row = (await db.execute(yt_stmt)).scalar_one_or_none()
                    if yt_row:
                        yt_row.access_token = _encrypt(_new_yt_token)
                        yt_row.updated_at = datetime.now(timezone.utc)
                        await db.commit()
                        logger.info("Persisted refreshed YouTube access token for user %s", user_id)
                except Exception as yt_persist_err:
                    logger.warning("Failed to persist refreshed YouTube token (non-fatal): %s", yt_persist_err)

            # ── Phase 7: Save to content memory on success ───────────
            if row.status in ("completed", "posted"):
                try:
                    from variation_engine import compute_topic_fingerprint
                    cm_entry = ContentMemory(
                        user_id=user_id,
                        topic=topic,
                        topic_fingerprint=compute_topic_fingerprint(topic),
                        title=row.title or topic,
                        temperature_used=str(result.get("_temperature_used", "")),
                        music_mood=result.get("_music_mood", ""),
                    )
                    db.add(cm_entry)
                    await db.commit()
                    logger.info("Phase 7: saved content memory entry for '%s'", topic[:60])
                except Exception as cm_save_err:
                    logger.warning("Phase 7: content memory save failed (non-fatal): %s", cm_save_err)

                # ── Adaptive learning: save ContentPerformance record ────
                try:
                    cp_entry = ContentPerformance(
                        user_id=user_id,
                        video_record_id=record_id,
                        title_variant_used=row.title or topic,
                        thumbnail_concept_used=result.get("_thumbnail_concept_used", "bold_curiosity"),
                        title_style_used=result.get("_title_style_used", ""),
                        hook_mode_used=result.get("_hook_mode_used", "balanced"),
                    )
                    db.add(cp_entry)
                    await db.commit()
                    logger.info("Adaptive: saved ContentPerformance for record %s (style=%s, thumb=%s, hook=%s)",
                                record_id, cp_entry.title_style_used, cp_entry.thumbnail_concept_used, cp_entry.hook_mode_used)
                except Exception as cp_err:
                    logger.warning("Adaptive: ContentPerformance save failed (non-fatal): %s", cp_err)

                # ── Thumbnail A/B: auto-create experiment if 2+ variants ─
                try:
                    _thumb_variants = result.get("thumbnail_variants", [])
                    if len(_thumb_variants) >= 2 and row.status == "posted":
                        from backend.feature_flags import FF_THUMB_AB, is_globally_enabled
                        if is_globally_enabled(FF_THUMB_AB):
                            # Look up the user's channel
                            _ch_stmt = select(Channel).where(
                                Channel.user_id == user_id
                            ).order_by(Channel.created_at.asc()).limit(1)
                            _ch_row = (await db.execute(_ch_stmt)).scalar_one_or_none()
                            if _ch_row:
                                from backend.services.thumb_ab_service import create_experiment as _create_thumb_exp
                                _exp, _exp_variants = await _create_thumb_exp(
                                    channel_id=_ch_row.id,
                                    video_record_id=record_id,
                                    variants=_thumb_variants,
                                    db=db,
                                )
                                await db.commit()
                                logger.info(
                                    "Thumbnail A/B: auto-created experiment %s with %d variants for video %s",
                                    _exp.id, len(_exp_variants), record_id,
                                )
                            else:
                                logger.debug("Thumbnail A/B: no channel found for user %s — skipping experiment", user_id)
                except Exception as _tab_err:
                    logger.warning("Thumbnail A/B: auto-create failed (non-fatal): %s", _tab_err)
    except Exception:
        logger.exception("Failed to update VideoRecord %s after pipeline", record_id)
    finally:
        # Clean up in-memory progress store
        _progress_store.pop(record_id, None)

    # ── Phase 3: Clean up per-run output directory after successful upload ──
    # After YouTube upload, the local MP4/clips/thumbnails are no longer needed.
    # For non-uploaded videos, we keep files for 24 h (handled by _cleanup_old_output_dirs).
    if result.get("youtube_video_id"):
        _cleanup_run_dir(record_id)


# ── Per-run output directory cleanup ─────────────────────────────────

def _cleanup_run_dir(record_id: str) -> None:
    """Delete the ``output/{record_id}/`` directory tree.

    Best-effort — never raises.  Logs the outcome.
    """
    import shutil

    run_dir = OUTPUT_DIR / record_id
    if not run_dir.is_dir():
        return
    try:
        shutil.rmtree(run_dir)
        logger.info("🧹 Cleaned up output directory: %s", run_dir)
    except Exception as exc:
        logger.warning("🧹 Failed to clean up %s (non-fatal): %s", run_dir, exc)


async def _cleanup_old_output_dirs(max_age_hours: int = 24) -> None:
    """Remove per-run output directories older than *max_age_hours*.

    Intended to be called periodically (e.g. from the scheduler or
    lifespan startup) to reclaim disk space on Railway's limited volumes.
    Directories for videos that were uploaded are already cleaned immediately
    by ``_cleanup_run_dir``; this catches completed-but-not-uploaded leftovers.
    """
    import shutil

    cutoff = time.time() - (max_age_hours * 3600)
    cleaned = 0
    try:
        for child in OUTPUT_DIR.iterdir():
            if not child.is_dir():
                continue
            # Only clean UUID-named dirs (per-run dirs), not "clips", "thumb_*", etc.
            if len(child.name) < 30:
                continue
            try:
                mtime = child.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(child)
                    cleaned += 1
            except Exception:
                pass
        if cleaned:
            logger.info("🧹 Cleaned up %d old output directories (>%dh)", cleaned, max_age_hours)
    except Exception as exc:
        logger.warning("🧹 Old output dir cleanup failed (non-fatal): %s", exc)


# ── Plan-based limit enforcement ─────────────────────────────────────

async def _enforce_plan_limit(user: User, db: AsyncSession) -> None:
    """Raise HTTP 403 if the user has exhausted their monthly video quota."""
    plan = user.plan or "free"
    limit = PLAN_MONTHLY_LIMITS.get(plan, PLAN_MONTHLY_LIMITS["free"])

    # Count videos created this calendar month.
    # Exclude failed/interrupted jobs so that server restarts and transient
    # errors don't consume the user's quota.
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == user.id,
            VideoRecord.created_at >= month_start,
            VideoRecord.status.notin_(["failed"]),
        )
    )
    count = (await db.execute(count_stmt)).scalar() or 0

    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You've reached your {plan.title()} plan limit of {limit} video(s) this month. "
                "Upgrade your plan in Settings → Plan to generate more."
            ),
        )


# ── Bulk Generation Endpoints (Phase 3) ─────────────────────────────

@router.post("/bulk-generate", response_model=BulkGenerateResponse)
@limiter.limit("3/hour")
async def bulk_generate_videos(
    request: Request,
    body: BulkGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue multiple topics for sequential video generation.

    Creates VideoRecords for all valid topics upfront with status='queued',
    groups them by a batch_id, then processes them one at a time through
    the normal pipeline — respecting the existing semaphore and inflight guard.

    Free plan users cannot use bulk generation.
    Plan limits are enforced upfront — if the user can't afford all N videos,
    none are queued (atomic check).
    """
    plan = current_user.plan or "free"
    max_topics = BULK_MAX_TOPICS.get(plan, 0)

    if max_topics == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bulk generation is available on Starter, Pro, and Agency plans. Upgrade in Settings → Plan.",
        )

    if len(body.topics) > max_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Your {plan.title()} plan allows up to {max_topics} topics per batch. You submitted {len(body.topics)}.",
        )

    # ── Check plan quota can accommodate ALL topics ──────────────────
    limit = PLAN_MONTHLY_LIMITS.get(plan, PLAN_MONTHLY_LIMITS["free"])
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.created_at >= month_start,
            VideoRecord.status.notin_(["failed"]),
        )
    )
    current_count = (await db.execute(count_stmt)).scalar() or 0
    remaining_quota = max(0, limit - current_count)

    if len(body.topics) > remaining_quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You have {remaining_quota} video(s) left this month on your {plan.title()} plan, "
                f"but submitted {len(body.topics)} topics. Reduce the number of topics or upgrade your plan."
            ),
        )

    # ── Fetch user API keys ──────────────────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
        elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
        pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""
        pixabay_key = decrypt_or_raise(user_keys.pixabay_api_key, field="pixabay_api_key") if user_keys and getattr(user_keys, "pixabay_api_key", None) else ""
    except DecryptionFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Your saved API keys could not be decrypted ({exc.field_label}). Please re-enter them in Settings → API Keys.",
        )

    if not openai_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please add your OpenAI API key in Settings → API Keys before generating videos.")
    if not elevenlabs_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please add your ElevenLabs API key in Settings → API Keys before generating videos.")

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        "pixabay_api_key": pixabay_key,
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
    }

    # ── Fetch YouTube OAuth tokens ───────────────────────────────────
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = result.scalar_one_or_none()

    yt_access_token: str | None = None
    yt_refresh_token: str | None = None
    if oauth_token:
        try:
            yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token")
            yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token")
        except DecryptionFailedError:
            logger.warning("YouTube OAuth token for user %s could not be decrypted — bulk videos will not be uploaded.", current_user.email)

    # ── Create batch ─────────────────────────────────────────────────
    import uuid as _uuid
    batch_id = str(_uuid.uuid4())
    video_ids: list[str] = []

    for idx, topic_text in enumerate(body.topics):
        record = VideoRecord(
            user_id=current_user.id,
            topic=topic_text,
            title=topic_text,
            status="queued",
            batch_id=batch_id,
            batch_position=idx,
        )
        db.add(record)
        await db.flush()
        video_ids.append(record.id)

    await db.commit()
    logger.info(
        "Bulk batch %s created for user %s: %d videos queued",
        batch_id, current_user.email, len(video_ids),
    )

    # ── Admin event ──────────────────────────────────────────────────
    async with async_session_factory() as ev_db:
        await emit_event(ev_db, "bulk_started", user_id=current_user.id, meta={"batch_id": batch_id, "count": len(video_ids)})
        await ev_db.commit()

    # ── Kick off sequential background processor ─────────────────────
    asyncio.create_task(
        _run_bulk_pipeline(
            batch_id=batch_id,
            video_ids=video_ids,
            topics=body.topics,
            user_id=current_user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )

    return BulkGenerateResponse(
        batch_id=batch_id,
        total=len(body.topics),
        queued=len(video_ids),
        skipped=0,
        message=f"Batch queued! {len(video_ids)} video(s) will be created sequentially.",
        video_ids=video_ids,
    )


async def _run_bulk_pipeline(
    *,
    batch_id: str,
    video_ids: list[str],
    topics: list[str],
    user_id: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
) -> None:
    """Process a batch of videos sequentially through the pipeline.

    For each video:
    1. Mark it as 'generating'
    2. Run it through the normal pipeline (with semaphore + inflight guard)
    3. Regardless of success/failure, move to the next one

    A single failure does NOT cancel the rest of the batch.
    """
    logger.info("Bulk pipeline started for batch %s (%d videos)", batch_id, len(video_ids))

    for idx, (record_id, topic_text) in enumerate(zip(video_ids, topics)):
        logger.info(
            "Bulk batch %s — processing video %d/%d: %s (record %s)",
            batch_id, idx + 1, len(video_ids), topic_text[:60], record_id,
        )

        # Update status to generating
        try:
            async with async_session_factory() as db:
                stmt = (
                    update(VideoRecord)
                    .where(VideoRecord.id == record_id)
                    .values(status="generating", updated_at=datetime.now(timezone.utc))
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as e:
            logger.error("Bulk batch %s — failed to update record %s to generating: %s", batch_id, record_id, e)
            continue

        # Run through the same pipeline runner used by single generate
        try:
            await _run_pipeline_background(
                record_id=record_id,
                topic=topic_text,
                user_id=user_id,
                user_api_keys=user_api_keys,
                yt_access_token=yt_access_token,
                yt_refresh_token=yt_refresh_token,
            )
        except Exception as e:
            logger.error(
                "Bulk batch %s — video %d/%d failed: %s",
                batch_id, idx + 1, len(video_ids), e,
            )
            # Mark as failed if the pipeline didn't handle it
            try:
                async with async_session_factory() as db:
                    stmt = (
                        update(VideoRecord)
                        .where(
                            VideoRecord.id == record_id,
                            VideoRecord.status == "generating",
                        )
                        .values(
                            status="failed",
                            error_message=f"Bulk pipeline error: {str(e)[:500]}",
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()
            except Exception:
                pass

        # Brief pause between videos to let resources settle
        await asyncio.sleep(5)

    logger.info("Bulk pipeline finished for batch %s — all %d videos processed", batch_id, len(video_ids))

    # ── Admin event ──────────────────────────────────────────────────
    try:
        async with async_session_factory() as db:
            await emit_event(db, "bulk_completed", user_id=user_id, meta={"batch_id": batch_id, "count": len(video_ids)})
            await db.commit()
    except Exception:
        pass


@router.get("/bulk-status/{batch_id}", response_model=BulkStatusResponse)
async def get_bulk_status(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of all videos in a bulk batch."""
    stmt = (
        select(VideoRecord)
        .where(
            VideoRecord.batch_id == batch_id,
            VideoRecord.user_id == current_user.id,
        )
        .order_by(VideoRecord.batch_position)
    )
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="Batch not found.")

    items: list[BulkStatusItem] = []
    completed = failed = generating = queued = 0

    for row in rows:
        # Enrich with in-memory progress if currently generating
        prog = _progress_store.get(row.id, {})
        step = prog.get("step") or row.progress_step
        pct = prog.get("pct") or row.progress_pct

        items.append(BulkStatusItem(
            id=row.id,
            topic=row.topic,
            status=row.status,
            position=row.batch_position or 0,
            progress_step=step,
            progress_pct=pct,
            error_message=row.error_message,
            title=row.title if row.title != row.topic else None,
        ))

        if row.status in ("completed", "posted"):
            completed += 1
        elif row.status == "failed":
            failed += 1
        elif row.status == "generating":
            generating += 1
        elif row.status == "queued":
            queued += 1

    return BulkStatusResponse(
        batch_id=batch_id,
        total=len(rows),
        completed=completed,
        failed=failed,
        generating=generating,
        queued=queued,
        items=items,
    )


@router.get("/batches")
async def list_batches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all batch IDs for the current user, most recent first."""
    from sqlalchemy import distinct

    stmt = (
        select(
            VideoRecord.batch_id,
            func.count().label("total"),
            func.min(VideoRecord.created_at).label("started_at"),
        )
        .where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.batch_id.isnot(None),
        )
        .group_by(VideoRecord.batch_id)
        .order_by(func.min(VideoRecord.created_at).desc())
        .limit(20)
    )
    rows = (await db.execute(stmt)).all()

    batches = []
    for row in rows:
        # Get status counts for this batch
        status_stmt = (
            select(VideoRecord.status, func.count().label("cnt"))
            .where(
                VideoRecord.batch_id == row.batch_id,
                VideoRecord.user_id == current_user.id,
            )
            .group_by(VideoRecord.status)
        )
        status_rows = (await db.execute(status_stmt)).all()
        status_counts = {s.status: s.cnt for s in status_rows}

        batches.append({
            "batch_id": row.batch_id,
            "total": row.total,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed": status_counts.get("completed", 0) + status_counts.get("posted", 0),
            "failed": status_counts.get("failed", 0),
            "generating": status_counts.get("generating", 0),
            "queued": status_counts.get("queued", 0),
        })

    return batches


# ── Stale job cleanup helper ─────────────────────────────────────────

async def _cleanup_stale_jobs(user_id: str, db: AsyncSession) -> None:
    """Mark any 'generating' jobs older than STALE_JOB_MINUTES as failed.

    Called on status polls and history fetches to self-heal after crashes
    or Railway redeployments that kill in-progress background tasks.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_JOB_MINUTES)
    stmt = (
        update(VideoRecord)
        .where(
            VideoRecord.user_id == user_id,
            VideoRecord.status == "generating",
            VideoRecord.updated_at < cutoff,
        )
        .values(
            status="failed",
            error_message="Generation timed out or was interrupted by a server restart. Please try again.",
            updated_at=datetime.now(timezone.utc),
        )
    )
    result = await db.execute(stmt)
    # SQLAlchemy async Result may not have rowcount attribute in type hints, so ignore type checker
    if getattr(result, "rowcount", 0):  # type: ignore[attr-defined]
        await db.commit()
        logger.info("Cleaned up %d stale 'generating' jobs for user %s", getattr(result, "rowcount", 0), user_id)


async def user_has_inflight_video(user_id: str, db: AsyncSession) -> bool:
    """Check if a user already has a video in-flight (generating or queued).

    Checks both the in-memory tracker (fast) and the DB (survives restarts).
    Used by scheduler and trend radar workers to skip users who already
    have an active pipeline — prevents resource contention.
    Also checks for 'queued' status to detect active bulk batches.
    """
    # Fast path: check in-memory tracker
    if user_id in _user_inflight:
        return True

    # Slow path: check DB (picks up jobs from before container restart)
    active_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == user_id,
            VideoRecord.status.in_(["generating", "queued"]),
        )
    )
    active_count = (await db.execute(active_stmt)).scalar() or 0
    return active_count > 0


async def is_circuit_broken(user_id: str, db: AsyncSession) -> bool:
    """Return True if the user's last N video attempts ALL failed.

    Used by scheduler_worker and trend_radar_worker to stop auto-generating
    videos when there's a persistent infrastructure failure (e.g. FFmpeg OOM).
    This prevents burning API credits on doomed pipelines.

    Manual generation from the UI is NOT blocked — only automated generation.
    The circuit resets automatically once any video succeeds.
    """
    stmt = (
        select(VideoRecord.status)
        .where(VideoRecord.user_id == user_id)
        .order_by(VideoRecord.created_at.desc())
        .limit(CIRCUIT_BREAKER_THRESHOLD)
    )
    recent_statuses = (await db.execute(stmt)).scalars().all()

    if len(recent_statuses) < CIRCUIT_BREAKER_THRESHOLD:
        return False  # Not enough history to judge

    return all(s == "failed" for s in recent_statuses)


# ── Per-record pipeline locks ─────────────────────────────────────────
# Allow parallel pipeline runs for DIFFERENT records while preventing
# duplicate concurrent runs for the SAME record_id.
# An OrderedDict acts as an LRU cache so that stale entries are evicted
# once MAX_LOCK_ENTRIES is exceeded.
_lock_map_guard = threading.Lock()  # protects the dict itself
_record_locks: OrderedDict[str, threading.Lock] = OrderedDict()
_MAX_LOCK_ENTRIES = 200  # upper bound; each entry is ~100 bytes


def _get_record_lock(record_id: str) -> threading.Lock:
    """Return (or create) a per-record threading.Lock, with LRU eviction."""
    with _lock_map_guard:
        if record_id in _record_locks:
            # Move to end (most-recently used)
            _record_locks.move_to_end(record_id)
            return _record_locks[record_id]
        # Evict oldest entries if we've hit the cap
        while len(_record_locks) >= _MAX_LOCK_ENTRIES:
            _evicted_id, _evicted_lock = _record_locks.popitem(last=False)
            # Only evict if the lock is not currently held
            if _evicted_lock.locked():
                # Put it back and evict the *next* oldest instead
                _record_locks[_evicted_id] = _evicted_lock
                _record_locks.move_to_end(_evicted_id, last=False)
                break
        lock = threading.Lock()
        _record_locks[record_id] = lock
        return lock


def _release_record_lock(record_id: str) -> None:
    """Remove a per-record lock entry after the pipeline finishes."""
    with _lock_map_guard:
        lock = _record_locks.pop(record_id, None)
        # Ensure the lock is released if it's still held (defensive)
        if lock and lock.locked():
            try:
                lock.release()
            except RuntimeError:
                pass


def _run_pipeline_sync(
    *,
    topic: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
    record_id: str | None = None,
) -> dict:
    """Synchronous pipeline: script → voiceover → video → (optional) upload.

    Uses per-user API keys (BYOK model) and per-user OAuth tokens
    instead of server-level env vars.

    A per-record lock prevents duplicate concurrent runs for the same
    record_id while allowing different records to execute in parallel.
    """
    rid = record_id or str(int(time.time()))
    lock = _get_record_lock(rid)
    if not lock.acquire(blocking=False):
        raise RuntimeError(f"Pipeline already running for record {rid}")
    try:
        return _run_pipeline_locked(
            topic=topic,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
            record_id=record_id,
        )
    finally:
        try:
            lock.release()
        except RuntimeError:
            pass
        _release_record_lock(rid)


def _run_pipeline_locked(
    *,
    topic: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
    record_id: str | None = None,
) -> dict:
    """Inner pipeline function — runs under a per-record lock."""

    # ── Per-run output directory (isolate files between concurrent runs) ──
    run_id = record_id or str(int(time.time()))
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_clips_dir = run_dir / "clips"
    run_clips_dir.mkdir(exist_ok=True)
    logger.info("Pipeline run directory: %s", run_dir)

    # Pipeline step timestamps for admin inspection
    _pipeline_steps: list[dict] = []

    def _report(step: str, pct: int) -> None:
        """Update in-memory progress for real-time polling."""
        if record_id and record_id in _progress_store:
            _progress_store[record_id]["step"] = step
            _progress_store[record_id]["pct"] = pct
        _pipeline_steps.append({"step": step, "pct": pct, "ts": time.time()})

    # Ensure the top-level project dir is on sys.path so we can import
    # the Phase 1 modules (script_generator, voiceover, etc.)
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Extract per-user API keys for parameter injection (no global mutation)
    _openai_key = user_api_keys["openai_api_key"]
    _elevenlabs_key = user_api_keys["elevenlabs_api_key"]
    _pexels_key = user_api_keys.get("pexels_api_key") or ""
    _pixabay_key = user_api_keys.get("pixabay_api_key") or ""

    # ── Plan-based quality profile ───────────────────────────────────
    from backend.utils import get_quality_profile
    _user_plan = user_api_keys.get("_plan", "free")
    _quality = get_quality_profile(_user_plan)
    logger.info("Pipeline using quality profile: plan=%s model=%s resolution=%s crf=%s scenes=%d",
                _user_plan, _quality["gpt_model"], _quality["video_resolution"],
                _quality["video_crf"], _quality["target_scenes"])

    import config
    import script_generator

    result: dict = {"title": topic}

    try:
        # ── Phase 7: Build variation context ─────────────────────────
        _report("Preparing variations…", 3)
        variation_ctx = None
        past_titles: list[str] = []
        try:
            from variation_engine import create_variation_context
            # Fetch past titles from content memory (sync DB query via raw SQL)
            past_titles = user_api_keys.get("_past_titles", [])
            variation_ctx = create_variation_context(topic, past_titles=past_titles)
            logger.info("Phase 7: variation context ready — temp=%.2f music=%s past=%d",
                        variation_ctx.script_temperature, variation_ctx.music_mood.label, len(past_titles))
        except Exception as var_err:
            logger.warning("Phase 7: variation engine failed (non-fatal, using defaults): %s", var_err)

        # ── Step 1: Generate script ──────────────────────────────────
        # If a refined script was provided (from the Script Refiner),
        # skip generation and use it directly.
        _refined_script = user_api_keys.get("_refined_script")
        _refined_metadata = user_api_keys.get("_refined_metadata")

        # User preferences and performance profile (used in adaptive generation)
        _user_prefs = user_api_keys.get("_user_preferences", {})
        _perf_profile = user_api_keys.get("_performance_profile", {})

        if _refined_script:
            _report("Using your refined script…", 5)
            script = _refined_script
            (run_dir / "latest_script.txt").write_text(script, encoding="utf-8")
            result["_script_text"] = script
            logger.info("Pipeline step 1/5: Using refined script (%d chars)", len(script))
            _report("Script ready", 15)
        else:
            _report("Generating script…", 5)
            logger.info("Pipeline step 1/5: Generating script for '%s'", topic)
            script_kwargs: dict = {}
            if variation_ctx:
                script_kwargs["temperature"] = variation_ctx.script_temperature
                script_kwargs["avoidance_prompt"] = variation_ctx.avoidance_prompt
            if _user_prefs:
                script_kwargs["user_preferences"] = _user_prefs
            if _perf_profile:
                script_kwargs["performance_profile"] = _perf_profile
            script_kwargs["model"] = _quality["gpt_model"]
            script_kwargs["max_tokens"] = _quality["max_script_tokens"]
            script = script_generator.generate_script(topic, api_key=_openai_key, **script_kwargs)
            (run_dir / "latest_script.txt").write_text(script, encoding="utf-8")
            result["_script_text"] = script
            logger.info("Pipeline step 1/5: Script generated (%d chars)", len(script))
            _report("Script ready", 15)

        # ── Step 2: Generate metadata ────────────────────────────────
        if _refined_metadata:
            _report("Using your metadata…", 18)
            metadata = _refined_metadata
            # Merge default tags
            extra_tags = [t for t in config.DEFAULT_TAGS if t not in metadata.get("tags", [])]
            metadata["tags"] = metadata.get("tags", []) + extra_tags
            result["title"] = metadata.get("title", topic)
            result["_metadata"] = metadata
            logger.info("Pipeline step 2/5: Using refined metadata — title: %s", result["title"])
            _report("Metadata ready", 22)
        else:
            _report("Generating metadata…", 18)
            logger.info("Pipeline step 2/5: Generating metadata")
            meta_kwargs: dict = {}
            if variation_ctx:
                meta_kwargs["temperature"] = variation_ctx.metadata_temperature
                meta_kwargs["avoidance_prompt"] = variation_ctx.metadata_avoidance
            if _user_prefs:
                meta_kwargs["user_preferences"] = _user_prefs
            if _perf_profile:
                meta_kwargs["performance_profile"] = _perf_profile
            meta_kwargs["model"] = _quality["gpt_model"]
            metadata = script_generator.generate_metadata(script, topic, api_key=_openai_key, **meta_kwargs)
            result["title"] = metadata.get("title", topic)
            result["_metadata"] = metadata
            logger.info("Pipeline step 2/5: Metadata ready — title: %s", result["title"])
            _report("Metadata ready", 22)

        # ── Step 3: Generate voiceover ───────────────────────────────
        _report("Generating voiceover…", 25)
        logger.info("Pipeline step 3/5: Generating voiceover")
        import voiceover as voiceover_mod

        # Voice style preset — from Script Refiner or variation engine
        _voice_style_key = user_api_keys.get("_voice_style")
        voice_kwargs: dict = {
            "output_path": str(run_dir / "voiceover.mp3"),
            "api_key": _elevenlabs_key,
            "model_id": _quality["voice_model"],
        }
        if user_api_keys.get("elevenlabs_voice_id"):
            voice_kwargs["voice_id"] = user_api_keys["elevenlabs_voice_id"]

        # Apply voice style preset parameters
        if _voice_style_key:
            style_params = voiceover_mod.get_voice_style_params(_voice_style_key)
            voice_kwargs["stability"] = style_params["stability"]
            voice_kwargs["similarity_boost"] = style_params["similarity_boost"]
            voice_kwargs["style"] = style_params["style"]
            voice_kwargs["speed"] = style_params["speed"]
            logger.info("Using voice style preset: %s", _voice_style_key)
        elif variation_ctx:
            voice_kwargs["stability"] = variation_ctx.voice_params.stability
            voice_kwargs["similarity_boost"] = variation_ctx.voice_params.similarity_boost
            voice_kwargs["style"] = variation_ctx.voice_params.style

        # Override speed from user settings if explicitly set
        if user_api_keys.get("speech_speed"):
            voice_kwargs["speed"] = float(user_api_keys["speech_speed"])

        audio_path = voiceover_mod.generate_voiceover(script, **voice_kwargs)
        result["_voice_id"] = voice_kwargs.get("voice_id") or voiceover_mod.DEFAULT_VOICE_ID
        logger.info("Pipeline step 3/5: Voiceover saved → %s", audio_path)
        _report("Voiceover ready", 35)

        # ── Step 3b: Audio polish (Phase 4) ─────────────────────────
        _report("Polishing audio…", 36)
        try:
            from audio_processor import polish_audio
            # Phase 7: music mood rotation — pass frequencies from variation context
            polish_kwargs: dict = {}
            if variation_ctx:
                polish_kwargs["music_frequencies"] = variation_ctx.music_mood.frequencies
                polish_kwargs["music_tremolo_base"] = variation_ctx.music_mood.tremolo_base
            polished_path = polish_audio(audio_path, output_path=str(run_dir / "voiceover_polished.mp3"), **polish_kwargs)
            audio_path = polished_path
            logger.info("Pipeline step 3b: Audio polished → %s", audio_path)
            _report("Audio polished", 38)
        except Exception as audio_err:
            logger.warning("Audio polish failed (non-fatal, using raw voiceover): %s", audio_err)
            _report("Audio polish skipped", 38)

        # ── Step 4: Scene planning + stock footage + video build ────────
        _report("Planning scenes…", 40)
        logger.info("Pipeline step 4/6: Scene planning")
        import stock_footage as stock_mod

        scene_clip_data = None
        _use_ai_illustrations = _quality.get("ai_illustrations", False)
        try:
            from scene_planner import plan_scenes
            # Phase 7: pass style_seed from variation context for better rotation
            plan_kwargs: dict = {
                "openai_api_key": user_api_keys["openai_api_key"],
                "target_total_clips": _quality["target_scenes"],
            }
            if variation_ctx and variation_ctx.style_seed:
                plan_kwargs["style_seed"] = variation_ctx.style_seed
            scene_plans = plan_scenes(script, topic, **plan_kwargs)
            logger.info(
                "Pipeline step 4/6: Scene plan ready — %d scenes, %d clips",
                len(scene_plans),
                sum(s.clip_count for s in scene_plans),
            )
            _report("Scene plan ready", 45)

            if _use_ai_illustrations:
                # ── Premium path: AI-generated video clips (Pro/Agency) ──
                _report("Generating AI video clips…", 48)
                logger.info("Pipeline step 4b/6: Generating AI scene videos (premium)")
                try:
                    from scene_illustrator import generate_illustrations_for_scenes
                    _style_seed = variation_ctx.style_seed if variation_ctx and variation_ctx.style_seed else ""
                    # Runway API key: user BYOK → platform default
                    _runway_key = user_api_keys.get("runway_api_key", "") or ""
                    if not _runway_key:
                        try:
                            from backend.config import get_settings as _get_cfg
                            _runway_key = _get_cfg().runway_api_key
                        except Exception:
                            pass
                    scene_clip_data = generate_illustrations_for_scenes(
                        scene_plans,
                        openai_api_key=_openai_key,
                        runway_api_key=_runway_key,
                        topic=topic,
                        style_seed=_style_seed,
                        clips_dir=run_clips_dir,
                        image_quality=_quality.get("ai_image_quality", "standard"),
                        video_width=_quality["video_resolution"][0],
                        video_height=_quality["video_resolution"][1],
                        video_fps=_quality["video_fps"],
                        ai_video_model=_quality.get("ai_video_model", "gen4_turbo"),
                        ai_video_duration=_quality.get("ai_video_duration", 5),
                    )
                    total_clips = sum(len(sd.get("clips", [])) for sd in scene_clip_data)
                    _runway_count = sum(1 for sd in scene_clip_data if sd.get("_method") == "runway")
                    logger.info("Pipeline step 4b/6: Generated %d AI video clips (%d Runway, %d fallback) across %d scenes", total_clips, _runway_count, total_clips - _runway_count, len(scene_clip_data))
                    _report("AI video clips ready", 60)
                except Exception as ai_err:
                    logger.warning(
                        "AI illustration failed — falling back to stock footage: %s", ai_err
                    )
                    _use_ai_illustrations = False
                    # Fall through to stock footage below

            if not _use_ai_illustrations or scene_clip_data is None:
                # ── Standard path: stock footage (Free/Starter/fallback) ──
                _report("Downloading stock footage…", 48)
                logger.info("Pipeline step 4b/6: Downloading scene-aware stock footage")
                from stock_footage import download_clips_for_scenes
                scene_clip_data = download_clips_for_scenes(scene_plans, clips_dir=run_clips_dir, api_key=_pexels_key, pixabay_api_key=_pixabay_key)
                total_clips = sum(len(sd.get("clips", [])) for sd in scene_clip_data)
                logger.info("Pipeline step 4b/6: Downloaded %d clips across %d scenes", total_clips, len(scene_clip_data))
                _report("Stock footage ready", 60)
        except Exception as scene_err:
            logger.warning(
                "Scene planner failed, falling back to legacy download: %s", scene_err
            )
            # scene_clip_data stays None → build_video will auto-download

        _report("Building video…", 62)
        logger.info("Pipeline step 4c/6: Building video")
        from video_builder import build_video
        import re as _re
        import video_builder as _vb_mod
        _slug = _re.sub(r'[^\w\s-]', '', metadata["title"]).strip().lower()
        _slug = _re.sub(r'[\s_]+', '_', _slug)[:80]
        _video_output_path = str(run_dir / f"{_slug}.mp4")
        # Unpack resolution tuple (e.g. (1920, 1080)) into width/height
        _vid_w, _vid_h = _quality["video_resolution"]
        video_path = build_video(
            audio_path=audio_path,
            title=metadata["title"],
            script=script,
            output_path=_video_output_path,
            scene_clip_data=scene_clip_data,
            subtitle_style=user_api_keys.get("subtitle_style", "bold_pop"),
            burn_captions=user_api_keys.get("burn_captions", True),
            video_width=_vid_w,
            video_height=_vid_h,
            video_fps=_quality["video_fps"],
            video_crf=str(_quality["video_crf"]),
            video_bitrate=_quality["video_bitrate"],
            audio_bitrate=_quality["audio_bitrate"],
            watermark=_quality.get("watermark", False),
            openai_api_key=_openai_key,
            visual_tier=_quality.get("visual_tier", "free"),
            topic_label=topic,
        )
        result["file_path"] = video_path
        # Phase 5: capture SRT path from video builder
        result["srt_path"] = getattr(_vb_mod, "last_srt_path", None)
        logger.info("Pipeline step 4c/6: Video built → %s", video_path)
        _report("Video built", 78)

        # ── Step 5: Generate thumbnail variants ────────────────────
        _report("Generating thumbnails…", 80)
        logger.info("Pipeline step 5/6: Generating thumbnail variants (including AI)")
        from thumbnail import generate_thumbnail, generate_thumbnail_variants
        thumbnail_variants = generate_thumbnail_variants(
            metadata["title"],
            output_dir=str(run_dir),
            openai_api_key=_openai_key,
        )
        # Select primary thumbnail based on adaptive profile recommendation
        _recommended_thumb = _perf_profile.get("recommended_thumbnail_style", "bold_curiosity") if _perf_profile else "bold_curiosity"
        thumbnail_path = None
        for tv in thumbnail_variants:
            if tv["concept"] == _recommended_thumb:
                thumbnail_path = tv["path"]
                break
        if not thumbnail_path:
            thumbnail_path = thumbnail_variants[0]["path"] if thumbnail_variants else generate_thumbnail(metadata["title"], output_path=str(run_dir / "thumbnail.jpg"))
        result["thumbnail_variants"] = thumbnail_variants
        result["_thumbnail_concept_used"] = _recommended_thumb
        logger.info("Pipeline step 5/6: Generated %d variants, primary=%s", len(thumbnail_variants), _recommended_thumb)
        _report("Thumbnails ready", 85)

        # ── Step 6: Skip auto-upload — user reviews in Preview first ──
        # The pipeline now ALWAYS stops at "completed" so the user can
        # preview the video, thumbnail, and metadata before publishing.
        # Publishing is triggered via POST /api/videos/{id}/publish.
        result["thumbnail_path"] = thumbnail_path
        if yt_access_token:
            logger.info("Pipeline step 6/6: Video ready for preview (YouTube connected — user can publish)")
        else:
            logger.info("Pipeline step 6/6: Video ready for preview (no YouTube connection)")
        _report("Ready for preview", 100)

    except Exception:
        # Phase 8: mask keys in the traceback logged here
        logger.exception("Pipeline error during locked execution")
        raise

    # ── Phase 7: Attach variation metadata for content memory ────────
    if variation_ctx:
        result["_temperature_used"] = variation_ctx.script_temperature
        result["_music_mood"] = variation_ctx.music_mood.label

    # ── Adaptive learning: attach style choices for ContentPerformance ──
    result["_title_style_used"] = metadata.get("title_style", "")
    result["_hook_mode_used"] = _perf_profile.get("hook_mode", "balanced") if _perf_profile else "balanced"

    # ── Pipeline step log for admin detail view ──────────────────────
    result["_pipeline_steps"] = _pipeline_steps

    # ── Generation summary (Step 6: Output summary) ──────────────────
    _user_prefs = user_api_keys.get("_user_preferences", {})
    summary_lines = [
        f"Topic: {topic}",
        f"Title: {result.get('title', topic)}",
    ]
    if _user_prefs.get("niches"):
        summary_lines.append(f"Niches: {', '.join(_user_prefs['niches'])}")
    if _user_prefs.get("channel_goal"):
        summary_lines.append(f"Goal: {_user_prefs['channel_goal']}")
    if _user_prefs.get("tone_style"):
        summary_lines.append(f"Tone: {_user_prefs['tone_style']}")
    if variation_ctx:
        summary_lines.append(f"Temp: {variation_ctx.script_temperature:.2f}")
        summary_lines.append(f"Music mood: {variation_ctx.music_mood.label}")
    thumbnail_variants = result.get("thumbnail_variants", [])
    if thumbnail_variants:
        summary_lines.append(f"Thumbnails: {', '.join(v['concept'] for v in thumbnail_variants)}")
    # Adaptive profile summary
    if _perf_profile and _perf_profile.get("adaptation_active"):
        summary_lines.append(f"Hook: {result.get('_hook_mode_used', 'balanced')}")
        summary_lines.append(f"Title style: {result.get('_title_style_used', '?')}")
        summary_lines.append(f"Thumb pick: {result.get('_thumbnail_concept_used', '?')}")
        summary_lines.append(f"Adapt pts: {_perf_profile.get('total_data_points', 0)}")
    result["_generation_summary"] = " | ".join(summary_lines)
    logger.info("Generation summary: %s", result["_generation_summary"])

    return result


def _upload_with_user_tokens(
    *,
    video_path: str,
    metadata: dict,
    thumbnail_path: str | None,
    access_token: str,
    refresh_token: str | None,
) -> tuple[str | None, str | None]:
    """Upload a video to YouTube using per-user OAuth tokens from the DB.

    Returns ``(youtube_video_id, refreshed_access_token)``.
    ``refreshed_access_token`` is non-None only when the token was actually
    refreshed during this call — the caller should persist it back to the DB.

    This replaces the CLI uploader's ``get_authenticated_service()`` which
    reads from a local ``token.json`` file.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    # Build credentials from the stored tokens
    from backend.config import get_settings
    settings = get_settings()

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
        ],
    )

    # Lazy import of UploadError for typed error classification
    try:
        from pipeline_errors import UploadError as _UploadError
    except ImportError:
        _UploadError = RuntimeError  # type: ignore[assignment,misc]

    # Track whether the token was refreshed so the caller can persist it
    _refreshed_access_token: str | None = None

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _refreshed_access_token = creds.token
            logger.info("Refreshed YouTube access token")
        except Exception as e:
            logger.error("Failed to refresh YouTube token: %s", e)
            raise _UploadError(
                "YouTube token expired and could not be refreshed. "
                "Please reconnect your YouTube channel in Settings."
            ) from e

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "categoryId": DEFAULT_VIDEO_CATEGORY,
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True)

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    logger.info("Uploading to YouTube: %s", metadata["title"])

    # Resumable upload loop
    # Phase 8: Extended retry — handles 5xx, 403 rate limit, and network errors
    response = None
    retry = 0
    max_retries = 10

    while response is None:
        try:
            upload_status, response = insert_request.next_chunk()
            if upload_status:
                logger.info("Upload progress: %d%%", int(upload_status.progress() * 100))
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry += 1
                if retry > max_retries:
                    raise _UploadError(f"YouTube upload failed after {max_retries} retries (server errors)")
                wait = random.random() * (2 ** retry)
                logger.warning("Retriable YouTube error %s, retrying in %.1fs", e.resp.status, wait)
                time.sleep(wait)
                continue
            # Phase 8: Retry on 403 rate-limit / userRateLimitExceeded
            if e.resp.status == 403:
                err_content = str(e.content).lower() if hasattr(e, "content") else str(e).lower()
                if "ratelimit" in err_content or "rate" in err_content or "userRateLimitExceeded".lower() in err_content:
                    retry += 1
                    if retry > max_retries:
                        raise _UploadError(f"YouTube upload rate-limited after {max_retries} retries")
                    wait = min(random.random() * (2 ** retry), 60.0)
                    logger.warning("YouTube rate limit (403), retrying in %.1fs", wait)
                    time.sleep(wait)
                    continue
            raise _UploadError(
                f"YouTube upload failed: HTTP {e.resp.status} — {str(e)[:300]}"
            ) from e
        except (ConnectionError, TimeoutError, OSError) as net_err:
            # Phase 8: Retry on transient network errors
            retry += 1
            if retry > max_retries:
                raise _UploadError(
                    f"YouTube upload failed after {max_retries} retries due to network error"
                ) from net_err
            wait = min(random.random() * (2 ** retry), 60.0)
            logger.warning(
                "YouTube upload network error (attempt %d/%d): %s — retrying in %.1fs",
                retry, max_retries, type(net_err).__name__, wait,
            )
            time.sleep(wait)

    video_id = response.get("id")
    logger.info("YouTube upload complete! Video ID: %s", video_id)

    # Set custom thumbnail
    if thumbnail_path and os.path.isfile(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            logger.info("Custom thumbnail set for video %s", video_id)
        except HttpError as e:
            logger.warning("Failed to set thumbnail: %s", e)

    return video_id, _refreshed_access_token


# ── GET /api/videos/{video_id}/status ────────────────────────────────

@router.get("/{video_id}/status")
async def video_status(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll the status of a video generation job."""
    # Clean up any stale jobs first
    await _cleanup_stale_jobs(current_user.id, db)

    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    # Merge in-memory progress (live during generation) with DB fields
    progress = _progress_store.get(video_id)
    progress_step = progress["step"] if progress else record.progress_step
    progress_pct = progress["pct"] if progress else (record.progress_pct or 0)
    started_at = progress["started_at"] if progress else None

    # If status is final, force 100%
    if record.status in ("completed", "posted"):
        progress_pct = 100
        progress_step = "Complete"
    elif record.status == "failed":
        progress_step = progress_step or "Failed"

    return {
        "id": record.id,
        "status": record.status,
        "title": record.title,
        "error_message": record.error_message,
        "youtube_url": record.youtube_url,
        "file_path": record.file_path,
        "progress_step": progress_step,
        "progress_pct": progress_pct,
        "started_at": started_at,
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }


# ── GET /api/videos/history ──────────────────────────────────────────

@router.get("/history", response_model=list[VideoHistoryItem])
async def video_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the per-user video history from the database."""
    # Clean up any stale jobs first
    await _cleanup_stale_jobs(current_user.id, db)

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
            srt_path=getattr(r, "srt_path", None),
            youtube_video_id=r.youtube_video_id,
            youtube_url=r.youtube_url,
            thumbnail_path=r.thumbnail_path,
            error_message=r.error_message,
            progress_step=_progress_store.get(r.id, {}).get("step") or r.progress_step,
            progress_pct=_progress_store.get(r.id, {}).get("pct", r.progress_pct or 0),
            has_script=bool(r.script_text),
            portrait_path=getattr(r, "portrait_path", None),
            square_path=getattr(r, "square_path", None),
            batch_id=getattr(r, "batch_id", None),
            batch_position=getattr(r, "batch_position", None),
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in records
    ]


# ── GET /api/videos/{video_id}/script — Resume editing a pending video ──

@router.get("/{video_id}/script")
async def get_video_script(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the saved script + metadata for a pending video so the user can resume editing."""
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")
    if not record.script_text:
        raise HTTPException(status_code=404, detail="No script saved for this video.")

    # Parse stored metadata JSON
    metadata = {}
    if record.metadata_json:
        import json as _json
        try:
            metadata = _json.loads(record.metadata_json)
        except Exception:
            metadata = {"title": record.title or record.topic}

    # Compute read time
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import script_generator
    read_time = script_generator.estimate_read_time(record.script_text)

    return {
        "script": record.script_text,
        "metadata": metadata,
        "read_time": read_time,
        "topic": record.topic,
        "video_id": record.id,
    }


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
        base.where(VideoRecord.status.in_(["pending", "generating", "queued"]))
    )).scalar() or 0

    # Monthly usage for plan limit display
    # Exclude failed videos — they don't count toward the user's quota
    # (server-side rendering failures shouldn't penalise the user).
    plan = current_user.plan or "free"
    limit = PLAN_MONTHLY_LIMITS.get(plan, PLAN_MONTHLY_LIMITS["free"])
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.created_at >= month_start,
            VideoRecord.status.notin_(["failed"]),
        )
    )
    monthly_used = (await db.execute(monthly_stmt)).scalar() or 0

    return VideoStats(
        total_generated=total,
        total_posted=posted,
        total_failed=failed,
        total_pending=pending,
        monthly_used=monthly_used,
        monthly_limit=limit,
        plan=plan,
    )


# ── DELETE /api/videos/clear-failed ──────────────────────────────────

@router.delete("/clear-failed")
async def clear_failed_videos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all failed VideoRecords for the current user.

    Properly cascades through all FK-dependent tables before removing
    the video records themselves.
    """
    from sqlalchemy import delete as sa_delete

    # 1. Collect the IDs of failed records
    failed_ids_result = await db.execute(
        select(VideoRecord.id).where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.status == "failed",
        )
    )
    failed_ids = [r[0] for r in failed_ids_result.all()]

    if not failed_ids:
        return {"deleted": 0, "message": "No failed videos to clear."}

    # 2. Delete ThumbVariants linked through ThumbExperiments
    exp_ids_result = await db.execute(
        select(ThumbExperiment.id).where(
            ThumbExperiment.video_record_id.in_(failed_ids)
        )
    )
    exp_ids = [r[0] for r in exp_ids_result.all()]
    if exp_ids:
        await db.execute(
            sa_delete(ThumbVariant).where(ThumbVariant.experiment_id.in_(exp_ids))
        )

    # 3. Delete ThumbExperiments (NOT NULL FK → video_records)
    await db.execute(
        sa_delete(ThumbExperiment).where(ThumbExperiment.video_record_id.in_(failed_ids))
    )

    # 4. Delete ContentPerformance (NOT NULL FK → video_records)
    await db.execute(
        sa_delete(ContentPerformance).where(ContentPerformance.video_record_id.in_(failed_ids))
    )

    # 5. NULL out nullable FKs in other tables
    await db.execute(
        update(AdminEvent).where(AdminEvent.video_id.in_(failed_ids)).values(video_id=None)
    )
    await db.execute(
        update(PlatformError).where(PlatformError.video_id.in_(failed_ids)).values(video_id=None)
    )
    await db.execute(
        update(RevenueEvent).where(RevenueEvent.video_record_id.in_(failed_ids)).values(video_record_id=None)
    )
    await db.execute(
        update(TrendAlert).where(TrendAlert.video_record_id.in_(failed_ids)).values(video_record_id=None)
    )

    # 6. Finally delete the video records themselves
    result = await db.execute(
        sa_delete(VideoRecord).where(VideoRecord.id.in_(failed_ids))
    )
    deleted = getattr(result, "rowcount", 0) or 0
    await db.commit()

    logger.info("Cleared %d failed video records for user %s", deleted, current_user.email)
    return {"deleted": deleted, "message": f"Cleared {deleted} failed video(s)."}


# ── GET /api/videos/{video_id}/download ──────────────────────────────

@router.get("/{video_id}/download")
async def download_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve the built MP4 file for download."""
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    if not record.file_path or not os.path.isfile(record.file_path):
        raise HTTPException(status_code=404, detail="Video file not found on server.")

    safe_title = (record.title or "video").replace(" ", "_")[:60]
    return FileResponse(
        path=record.file_path,
        media_type="video/mp4",
        filename=f"{safe_title}.mp4",
    )


# ══════════════════════════════════════════════════════════════════════
# MULTI-FORMAT EXPORT — reformat landscape → portrait / square
# ══════════════════════════════════════════════════════════════════════


@router.get("/formats")
async def list_formats():
    """Return available export format presets."""
    try:
        from video_builder import get_available_formats
        return {"formats": get_available_formats()}
    except Exception:
        # Fallback if video_builder import fails
        return {"formats": [
            {"key": "landscape", "label": "YouTube (16:9)", "width": 1280, "height": 720, "aspect": "16:9"},
            {"key": "portrait", "label": "Shorts / Reels / TikTok (9:16)", "width": 1080, "height": 1920, "aspect": "9:16"},
            {"key": "square", "label": "Instagram Feed (1:1)", "width": 1080, "height": 1080, "aspect": "1:1"},
        ]}


class ReformatRequest(BaseModel):
    target_format: str = Field(..., description="portrait or square")

    @field_validator("target_format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in ("portrait", "square"):
            raise ValueError("target_format must be 'portrait' or 'square'")
        return v


# In-flight reformat tracking to prevent duplicate runs
_reformat_inflight: dict[str, str] = {}  # record_id → format being generated
_reformat_lock = asyncio.Lock()


@router.post("/{video_id}/reformat")
async def reformat_video_endpoint(
    video_id: str,
    body: ReformatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reformat a completed landscape video to portrait (9:16) or square (1:1).

    This is a post-build operation — crops and scales the existing video.
    Takes ~30-60 seconds.  The result is stored on the VideoRecord and
    available for download via the format-specific download endpoint.
    """
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    if record.status not in ("completed", "posted"):
        raise HTTPException(status_code=400, detail="Video must be completed before reformatting.")

    if not record.file_path or not os.path.isfile(record.file_path):
        raise HTTPException(status_code=404, detail="Original video file not found on server.")

    target_format = body.target_format

    # Check if already reformatted
    existing_path = getattr(record, f"{target_format}_path", None)
    if existing_path and os.path.isfile(existing_path):
        size_mb = os.path.getsize(existing_path) / (1024 * 1024)
        return {
            "status": "ready",
            "format": target_format,
            "file_path": existing_path,
            "size_mb": round(size_mb, 1),
            "message": f"{target_format.title()} version already exists.",
        }

    # Check in-flight
    async with _reformat_lock:
        if video_id in _reformat_inflight:
            return {
                "status": "generating",
                "format": _reformat_inflight[video_id],
                "message": "Reformat already in progress.",
            }
        _reformat_inflight[video_id] = target_format

    try:
        # Run reformat in a thread to avoid blocking the event loop
        import video_builder as vb_mod

        # Build output path next to the original
        base, ext = os.path.splitext(record.file_path)
        output_path = f"{base}_{target_format}{ext}"

        reformatted_path = await asyncio.to_thread(
            vb_mod.reformat_video,
            source_video_path=record.file_path,
            target_format=target_format,
            output_path=output_path,
            script=record.script_text,
            title=record.title,
            subtitle_style="bold_pop",
            burn_captions=True,
        )

        # Persist the path on the record
        if target_format == "portrait":
            record.portrait_path = reformatted_path
        elif target_format == "square":
            record.square_path = reformatted_path
        await db.commit()

        size_mb = os.path.getsize(reformatted_path) / (1024 * 1024)
        logger.info(
            "Reformatted video %s → %s (%s, %.1f MB) for user %s",
            video_id, target_format, reformatted_path, size_mb, current_user.email,
        )

        return {
            "status": "ready",
            "format": target_format,
            "file_path": reformatted_path,
            "size_mb": round(size_mb, 1),
            "message": f"{target_format.title()} version ready for download.",
        }

    except Exception as e:
        logger.exception("Reformat failed for video %s → %s", video_id, target_format)
        raise HTTPException(status_code=500, detail=f"Reformat failed: {str(e)[:200]}")
    finally:
        async with _reformat_lock:
            _reformat_inflight.pop(video_id, None)


@router.get("/{video_id}/download/{target_format}")
async def download_formatted_video(
    video_id: str,
    target_format: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a reformatted video (portrait or square)."""
    if target_format not in ("portrait", "square", "landscape"):
        raise HTTPException(status_code=400, detail="Format must be 'landscape', 'portrait', or 'square'.")

    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    # Landscape = original file
    if target_format == "landscape":
        if not record.file_path or not os.path.isfile(record.file_path):
            raise HTTPException(status_code=404, detail="Video file not found on server.")
        safe_title = (record.title or "video").replace(" ", "_")[:60]
        return FileResponse(
            path=record.file_path,
            media_type="video/mp4",
            filename=f"{safe_title}_landscape.mp4",
        )

    # Portrait / square
    file_path = getattr(record, f"{target_format}_path", None)
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"{target_format.title()} version not found. Generate it first via POST /reformat.",
        )

    safe_title = (record.title or "video").replace(" ", "_")[:60]
    # Format label mapping for filename
    fmt_labels = {"portrait": "shorts_9x16", "square": "square_1x1"}
    fmt_label = fmt_labels.get(target_format, target_format)

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=f"{safe_title}_{fmt_label}.mp4",
    )


@router.get("/{video_id}/formats")
async def get_video_formats(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return which format variants exist for a video."""
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    variants = []

    # Landscape (original)
    if record.file_path and os.path.isfile(record.file_path):
        size_mb = os.path.getsize(record.file_path) / (1024 * 1024)
        variants.append({
            "format": "landscape",
            "label": "YouTube (16:9)",
            "status": "ready",
            "size_mb": round(size_mb, 1),
        })

    # Portrait
    if record.portrait_path and os.path.isfile(record.portrait_path):
        size_mb = os.path.getsize(record.portrait_path) / (1024 * 1024)
        variants.append({
            "format": "portrait",
            "label": "Shorts / Reels / TikTok (9:16)",
            "status": "ready",
            "size_mb": round(size_mb, 1),
        })
    else:
        variants.append({
            "format": "portrait",
            "label": "Shorts / Reels / TikTok (9:16)",
            "status": "not_generated",
            "size_mb": None,
        })

    # Square
    if record.square_path and os.path.isfile(record.square_path):
        size_mb = os.path.getsize(record.square_path) / (1024 * 1024)
        variants.append({
            "format": "square",
            "label": "Instagram Feed (1:1)",
            "status": "ready",
            "size_mb": round(size_mb, 1),
        })
    else:
        variants.append({
            "format": "square",
            "label": "Instagram Feed (1:1)",
            "status": "not_generated",
            "size_mb": None,
        })

    return {"video_id": video_id, "variants": variants}


# ── GET /api/videos/{video_id}/pipeline-log ──────────────────────────

@router.get("/{video_id}/pipeline-log")
async def get_pipeline_log(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the structured pipeline step log for a video.

    Each entry has ``step`` (human-readable label), ``pct`` (0-100),
    and ``ts`` (UNIX timestamp).  The frontend can render this as a
    timeline / progress trail.  Also returns the error classification
    if the video failed.
    """
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    import json as _json

    steps: list[dict] = []
    if record.pipeline_log_json:
        try:
            steps = _json.loads(record.pipeline_log_json)
        except (ValueError, TypeError):
            pass

    return {
        "video_id": record.id,
        "status": record.status,
        "error_message": record.error_message,
        "error_category": record.error_category,
        "steps": steps,
    }


# ── POST /api/videos/{video_id}/regenerate ───────────────────────────

@router.post("/{video_id}/regenerate", response_model=GenerateResponse)
@limiter.limit("5/hour")
async def regenerate_video(
    request: Request,
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-trigger the pipeline for the same topic as an existing video."""
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    if record.status == "generating":
        raise HTTPException(status_code=409, detail="This video is already being generated.")

    # ── Per-user in-flight guard ────────────────────────────────────
    async with _user_inflight_lock:
        if current_user.id in _user_inflight:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a video generating. Please wait for it to finish before starting another.",
            )
    if await user_has_inflight_video(current_user.id, db):
        await _cleanup_stale_jobs(current_user.id, db)
        if await user_has_inflight_video(current_user.id, db):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a video generating. Please wait for it to finish before starting another.",
            )

    # ── Fetch the user's API keys (BYOK) ─────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    openai_key = ""
    elevenlabs_key = ""
    pexels_key = ""
    pixabay_key = ""
    try:
        openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""
        elevenlabs_key = decrypt_or_raise(user_keys.elevenlabs_api_key, field="elevenlabs_api_key") if user_keys and user_keys.elevenlabs_api_key else ""
        pexels_key = decrypt_or_raise(user_keys.pexels_api_key, field="pexels_api_key") if user_keys and user_keys.pexels_api_key else ""
        pixabay_key = decrypt_or_raise(user_keys.pixabay_api_key, field="pixabay_api_key") if user_keys and getattr(user_keys, "pixabay_api_key", None) else ""
    except DecryptionFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Your saved API keys could not be decrypted ({exc.field_label}). "
                "Please re-enter them in Settings → API Keys."
            ),
        )

    if not openai_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your OpenAI API key in Settings → API Keys.",
        )
    if not elevenlabs_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your ElevenLabs API key in Settings → API Keys.",
        )

    user_api_keys = {
        "openai_api_key": openai_key,
        "elevenlabs_api_key": elevenlabs_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "" if user_keys else "",
        "pexels_api_key": pexels_key,
        "pixabay_api_key": pixabay_key,
        # Phase 4 & 5 video production preferences
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
        # Plan-based quality profile
        "_plan": current_user.plan or "free",
    }

    # ── Enforce plan-based monthly video limits ──────────────────────
    await _enforce_plan_limit(current_user, db)

    # ── Fetch YouTube tokens ─────────────────────────────────────────
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = oauth_result.scalar_one_or_none()
    yt_access_token: str | None = None
    yt_refresh_token: str | None = None
    if oauth_token:
        try:
            yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token")
            yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token")
        except DecryptionFailedError:
            logger.warning(
                "Regenerate: YouTube OAuth token for user %s could not be decrypted — "
                "video will be generated but not uploaded.",
                current_user.email,
            )
            yt_access_token = None
            yt_refresh_token = None

    # ── Create a NEW "generating" record (preserve old one) ──────────
    new_record = VideoRecord(
        user_id=current_user.id,
        topic=record.topic,
        title=record.topic,
        status="generating",
    )
    db.add(new_record)
    await db.commit()
    new_record_id = new_record.id
    logger.info("Regenerate: created VideoRecord %s from original %s", new_record_id, video_id)

    asyncio.create_task(
        _run_pipeline_background(
            record_id=new_record_id,
            topic=record.topic,
            user_id=current_user.id,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )

    return GenerateResponse(
        status="generating",
        topic=record.topic,
        message="Regeneration started! This takes 2-5 minutes.",
        video_id=new_record_id,
    )


# ══════════════════════════════════════════════════════════════════════
# VIDEO PREVIEW & PUBLISH — Review before posting to YouTube
# ══════════════════════════════════════════════════════════════════════


@router.get("/{video_id}/preview")
async def preview_video(
    request: Request,
    video_id: str,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream the built MP4 for in-browser preview playback.

    Accepts auth via:
    - Standard Bearer token (header)
    - ?token= query parameter (for <video> elements that can't send headers)
    """
    # Resolve user: try header first, fall back to query param
    user = None
    # Try standard Bearer auth
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            user = await get_current_user(token=auth_header.split(" ", 1)[1], db=db)
        except Exception:
            pass
    # Fall back to query param token
    if not user and token:
        try:
            user = await get_current_user(token=token, db=db)
        except Exception:
            pass
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")

    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")
    if not record.file_path or not os.path.isfile(record.file_path):
        raise HTTPException(status_code=404, detail="Video file not found on server.")

    return FileResponse(
        path=record.file_path,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/{video_id}/preview-thumbnail")
async def preview_thumbnail(
    request: Request,
    video_id: str,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Serve the thumbnail image for preview.

    Accepts auth via Bearer header or ?token= query param.
    """
    user = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            user = await get_current_user(token=auth_header.split(" ", 1)[1], db=db)
        except Exception:
            pass
    if not user and token:
        try:
            user = await get_current_user(token=token, db=db)
        except Exception:
            pass
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")

    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")
    if not record.thumbnail_path or not os.path.isfile(record.thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found.")

    ext = os.path.splitext(record.thumbnail_path)[1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext.lstrip("."), "image/jpeg")
    return FileResponse(path=record.thumbnail_path, media_type=mime)


@router.get("/{video_id}/preview-data")
async def preview_data(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all data needed for the preview modal: title, description, tags, thumbnail URL, etc."""
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    # Parse stored metadata
    import json as _json
    metadata = {}
    if record.metadata_json:
        try:
            metadata = _json.loads(record.metadata_json)
        except Exception:
            pass

    # Check YouTube connection
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    has_youtube = oauth_result.scalar_one_or_none() is not None

    return {
        "id": record.id,
        "title": record.title or "Untitled",
        "topic": record.topic,
        "description": metadata.get("description", ""),
        "tags": metadata.get("tags", []),
        "status": record.status,
        "has_video": bool(record.file_path and os.path.isfile(record.file_path)),
        "has_thumbnail": bool(record.thumbnail_path and os.path.isfile(record.thumbnail_path)),
        "has_youtube": has_youtube,
        "youtube_video_id": record.youtube_video_id,
        "youtube_url": record.youtube_url,
        "created_at": record.created_at.isoformat() if record.created_at else "",
    }


class PublishRequest(BaseModel):
    """Optional overrides when publishing to YouTube."""
    title: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=5000)
    tags: list[str] | None = Field(None, max_length=30)


@router.post("/{video_id}/publish")
@limiter.limit("5/hour")
async def publish_video(
    request: Request,
    video_id: str,
    body: PublishRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a completed video to YouTube.

    The user has previewed the video and chosen to publish. This endpoint
    uploads the video + thumbnail to YouTube and updates the record status
    from 'completed' to 'posted'.
    """
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")
    if record.status == "posted":
        raise HTTPException(status_code=409, detail="This video has already been published to YouTube.")
    if record.status not in ("completed",):
        raise HTTPException(status_code=400, detail=f"Cannot publish a video with status '{record.status}'. Video must be completed first.")
    if not record.file_path or not os.path.isfile(record.file_path):
        raise HTTPException(status_code=404, detail="Video file not found on server.")

    # ── Fetch YouTube OAuth tokens ───────────────────────────────────
    oauth_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = oauth_result.scalar_one_or_none()
    if not oauth_token:
        raise HTTPException(status_code=400, detail="No YouTube channel connected. Connect one in Settings.")

    try:
        yt_access_token = decrypt_or_raise(oauth_token.access_token, field="yt_access_token")
        yt_refresh_token = decrypt_or_raise(oauth_token.refresh_token, field="yt_refresh_token")
    except DecryptionFailedError:
        raise HTTPException(status_code=400, detail="YouTube token expired. Please reconnect your YouTube channel in Settings.")

    # ── Build metadata (allow overrides from the preview modal) ──────
    import json as _json
    stored_metadata = {}
    if record.metadata_json:
        try:
            stored_metadata = _json.loads(record.metadata_json)
        except Exception:
            pass

    metadata = {
        "title": (body.title if body and body.title else None) or record.title or record.topic,
        "description": (body.description if body and body.description else None) or stored_metadata.get("description", ""),
        "tags": (body.tags if body and body.tags else None) or stored_metadata.get("tags", []),
    }

    # If user changed the title, update the record
    if body and body.title and body.title != record.title:
        record.title = body.title

    # Persist updated metadata
    if body and (body.title or body.description or body.tags):
        merged = {**stored_metadata, **{k: v for k, v in metadata.items() if v is not None}}
        try:
            record.metadata_json = _json.dumps(merged)
        except Exception:
            pass

    # ── Upload in the background so the HTTP request doesn't time out ──
    record.status = "generating"  # Temporary — shows "Publishing…" in the UI
    record.progress_step = "Publishing to YouTube…"
    record.progress_pct = 90
    await db.commit()

    _progress_store[video_id] = {"step": "Publishing to YouTube…", "pct": 90, "started_at": time.time()}

    asyncio.create_task(
        _publish_to_youtube_background(
            record_id=video_id,
            user_id=current_user.id,
            video_path=record.file_path,
            thumbnail_path=record.thumbnail_path,
            metadata=metadata,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    )

    return {
        "status": "publishing",
        "message": "Publishing to YouTube — this takes about 30 seconds.",
        "video_id": video_id,
    }


async def _publish_to_youtube_background(
    *,
    record_id: str,
    user_id: str,
    video_path: str,
    thumbnail_path: str | None,
    metadata: dict,
    yt_access_token: str,
    yt_refresh_token: str | None,
) -> None:
    """Background task: upload a completed video to YouTube, then update DB."""
    logger.info("Publishing video %s to YouTube in background", record_id)
    try:
        youtube_video_id, refreshed_yt_token = await asyncio.to_thread(
            _upload_with_user_tokens,
            video_path=video_path,
            metadata=metadata,
            thumbnail_path=thumbnail_path,
            access_token=yt_access_token,
            refresh_token=yt_refresh_token,
        )
    except Exception as e:
        logger.error("YouTube publish failed for record %s: %s", record_id, e)
        youtube_video_id = None
        refreshed_yt_token = None

        async with async_session_factory() as db:
            stmt = select(VideoRecord).where(VideoRecord.id == record_id)
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row:
                row.status = "completed"  # Revert to completed — user can retry
                row.error_message = f"YouTube publish failed: {str(e)[:500]}"
                row.progress_step = "Publish failed"
                row.progress_pct = 85
                row.updated_at = datetime.now(timezone.utc)
                await db.commit()

            from backend.errors import capture_error
            await capture_error(db, "upload", message=str(e)[:2000], user_id=user_id, video_id=record_id)
            await db.commit()

        _progress_store.pop(record_id, None)
        return

    # ── Success: update the record ───────────────────────────────────
    async with async_session_factory() as db:
        stmt = select(VideoRecord).where(VideoRecord.id == record_id)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if not row:
            logger.error("VideoRecord %s not found after publish!", record_id)
            return

        if youtube_video_id:
            row.status = "posted"
            row.youtube_video_id = youtube_video_id
            row.youtube_url = f"https://www.youtube.com/watch?v={youtube_video_id}"
            row.published_at = datetime.now(timezone.utc)
            row.progress_step = "Published to YouTube!"
            row.progress_pct = 100
            row.error_message = None  # Clear any prior error
        else:
            row.status = "completed"
            row.error_message = "YouTube upload returned no video ID."
            row.progress_step = "Publish failed"

        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Published video %s → youtube_id=%s", record_id, youtube_video_id)

        # ── Emit events ──────────────────────────────────────────────
        if youtube_video_id:
            await emit_event(db, "upload_success", user_id=user_id, video_id=record_id, meta={"youtube_id": youtube_video_id})
            await db.commit()

        # ── Persist refreshed YouTube token ──────────────────────────
        if refreshed_yt_token:
            try:
                from backend.encryption import encrypt as _encrypt
                yt_stmt = select(OAuthToken).where(
                    OAuthToken.user_id == user_id,
                    OAuthToken.provider == "google",
                )
                yt_row = (await db.execute(yt_stmt)).scalar_one_or_none()
                if yt_row:
                    yt_row.access_token = _encrypt(refreshed_yt_token)
                    yt_row.updated_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception as yt_err:
                logger.warning("Failed to persist refreshed YouTube token: %s", yt_err)

    _progress_store.pop(record_id, None)


# ── GET /api/videos/queue ───────────────────────────────────────────

@router.get("/queue")
async def render_queue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the number of currently generating jobs (global + user)."""
    # Global generating count
    global_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(VideoRecord.status == "generating")
    )
    global_count = (await db.execute(global_stmt)).scalar() or 0

    # User's generating count
    user_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.status == "generating",
        )
    )
    user_count = (await db.execute(user_stmt)).scalar() or 0

    # User's queued (bulk batch) count
    queued_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == current_user.id,
            VideoRecord.status == "queued",
        )
    )
    queued_count = (await db.execute(queued_stmt)).scalar() or 0

    return {
        "global_generating": global_count,
        "user_generating": user_count,
        "user_queued": queued_count,
    }


# ── Video preferences schemas (Phase 4 & 5) ─────────────────────────

# ── Valid subtitle styles allowlist (Phase 2 — input sanitization) ───
_VALID_SUBTITLE_STYLES = frozenset({"bold_pop", "minimal", "cinematic", "accent_highlight"})


class VideoPreferences(BaseModel):
    subtitle_style: str = "bold_pop"
    burn_captions: bool = True
    speech_speed: str | None = None  # e.g. "1.0", "0.85", "1.1"

    @field_validator("subtitle_style")
    @classmethod
    def validate_subtitle_style(cls, v: str) -> str:
        if v not in _VALID_SUBTITLE_STYLES:
            raise ValueError(
                f"Invalid subtitle style. Choose from: {', '.join(sorted(_VALID_SUBTITLE_STYLES))}"
            )
        return v

    @field_validator("speech_speed")
    @classmethod
    def validate_speech_speed(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                speed_val = float(v)
                if not (0.7 <= speed_val <= 1.2):
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("Speech speed must be a number between 0.7 and 1.2")
        return v


class VideoPreferencesResponse(BaseModel):
    subtitle_style: str
    burn_captions: bool
    speech_speed: str | None
    available_styles: list[dict]


# ── GET /api/videos/preferences ──────────────────────────────────────

@router.get("/preferences", response_model=VideoPreferencesResponse)
async def get_video_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's video production preferences."""
    result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = result.scalar_one_or_none()

    # Fetch available subtitle styles from subtitle_generator (with fallback)
    available_styles = [
        {"key": "bold_pop", "name": "Bold Pop", "font_size": 44, "bold": True, "border_style": "Outline"},
        {"key": "minimal", "name": "Minimal", "font_size": 38, "bold": False, "border_style": "Outline"},
        {"key": "cinematic", "name": "Cinematic", "font_size": 40, "bold": True, "border_style": "Box"},
        {"key": "accent_highlight", "name": "Accent Highlight", "font_size": 42, "bold": True, "border_style": "Outline"},
    ]
    try:
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from subtitle_generator import get_available_styles
        available_styles = get_available_styles()
    except Exception:
        pass  # use hardcoded fallback

    return VideoPreferencesResponse(
        subtitle_style=getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        burn_captions=getattr(user_keys, "burn_captions", True) if user_keys else True,
        speech_speed=getattr(user_keys, "speech_speed", None) if user_keys else None,
        available_styles=available_styles,
    )


# ── PUT /api/videos/preferences ──────────────────────────────────────

@router.put("/preferences")
async def update_video_preferences(
    body: VideoPreferences,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's video production preferences."""
    result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = result.scalar_one_or_none()

    if not user_keys:
        # Create a UserApiKeys row if it doesn't exist yet
        user_keys = UserApiKeys(user_id=current_user.id)
        db.add(user_keys)

    # Validation is now handled by Pydantic field_validators on VideoPreferences.

    user_keys.subtitle_style = body.subtitle_style
    user_keys.burn_captions = body.burn_captions
    user_keys.speech_speed = body.speech_speed

    await db.commit()
    logger.info("Updated video preferences for user %s: style=%s burn=%s speed=%s",
                current_user.email, body.subtitle_style, body.burn_captions, body.speech_speed)

    return {"message": "Video preferences saved.", "preferences": body.model_dump()}


# ── GET /api/videos/topic-suggestions ────────────────────────────────

class TopicSuggestion(BaseModel):
    topic: str
    score: int = Field(..., ge=1, le=10, description="Estimated demand score 1-10")
    angle: str = Field(..., description="Suggested narrative angle")
    why: str = Field(..., description="One-line reason this topic works")


class TopicSuggestionsResponse(BaseModel):
    suggestions: list[TopicSuggestion]


@router.get("/topic-suggestions", response_model=TopicSuggestionsResponse)
@limiter.limit("10/hour")
async def topic_suggestions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate 5 scored topic suggestions based on the user's past content.

    Uses the content memory to avoid suggesting previously-covered topics
    and returns a demand score (1-10) to help users pick high-impact ideas.
    """
    # Fetch past topics from content memory
    past_titles: list[str] = []
    try:
        cm_stmt = (
            select(ContentMemory.title)
            .where(ContentMemory.user_id == current_user.id)
            .order_by(ContentMemory.created_at.desc())
            .limit(20)
        )
        cm_rows = (await db.execute(cm_stmt)).scalars().all()
        past_titles = [t for t in cm_rows if t]
    except Exception:
        pass

    # Fetch the user's OpenAI key
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()
    openai_key = decrypt_or_raise(user_keys.openai_api_key, field="openai_api_key") if user_keys and user_keys.openai_api_key else ""

    if not openai_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add your OpenAI API key in Settings to get topic suggestions.",
        )

    # Fetch user preferences for niche-aware suggestions
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    user_prefs = prefs_result.scalar_one_or_none()
    niche_context = ""
    primary_niche = ""
    if user_prefs and user_prefs.niches_json:
        import json as _prefs_json
        try:
            user_niches = _prefs_json.loads(user_prefs.niches_json)
            if user_niches:
                niche_context = f"This channel covers: {', '.join(user_niches[:3])}. Suggest topics within these niches.\n"
                primary_niche = user_niches[0]
        except Exception:
            pass

    # Fetch live web trends for grounding
    from datetime import datetime as _dt_cls
    from backend.config import get_settings as _get_app_settings
    _serpapi_key = _get_app_settings().serpapi_api_key
    _today = _dt_cls.now(timezone.utc).strftime("%B %d, %Y")

    live_data_block = ""
    if _serpapi_key and primary_niche:
        try:
            from backend.services.web_trends_service import fetch_live_trend_context
            live_data_block = await asyncio.to_thread(
                fetch_live_trend_context,
                niche=primary_niche,
                serpapi_key=_serpapi_key,
            )
        except Exception as _web_err:
            logger.warning("Live trends fetch failed for topic suggestions (non-fatal): %s", _web_err)
            live_data_block = (
                f"\n\nIMPORTANT: Today's date is {_today}. "
                f"All topics MUST be relevant to {_today}. "
                f"Do NOT suggest outdated topics from 2023 or 2024."
            )
    else:
        live_data_block = (
            f"\n\nIMPORTANT: Today's date is {_today}. "
            f"All topics MUST be relevant to {_today}. "
            f"Do NOT suggest outdated topics from 2023 or 2024."
        )

    # Generate suggestions via OpenAI
    import json as _json
    from openai import OpenAI

    avoidance = ""
    if past_titles:
        avoidance = "\n\nALREADY COVERED (do NOT suggest these or close variations):\n"
        for t in past_titles[:15]:
            avoidance += f"  - {t}\n"

    system = (
        f"You suggest YouTube video topics. Today's date is {_today}. {niche_context}\n"
        "Return ONLY a JSON array of exactly 5 objects. Each object has:\n"
        '  "topic" — a specific, ready-to-use video topic (not generic)\n'
        '  "score" — demand score 1-10 (10=highest search demand + low competition)\n'
        '  "angle" — the narrative angle: one of "myth-bust", "story", "how-to", "contrarian", "case-study"\n'
        '  "why"   — one sentence: why this topic has high potential right now (reference real current events/trends)\n\n'
        "RULES:\n"
        "- Mix angles — never suggest 5 of the same type.\n"
        "- Topics must be SPECIFIC (not 'how to save money' — too broad).\n"
        "- Favor timely, emotionally engaging, or contrarian topics.\n"
        "- Score honestly — not everything is a 10.\n"
        f"- All topics MUST be relevant to {_today} — never suggest outdated content.\n"
        "- Ground your suggestions in the live market data provided below.\n"
        "Do NOT include markdown fences. Return raw JSON only."
        f"{avoidance}"
        f"{live_data_block}"
    )

    try:
        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Suggest 5 high-potential video topics for this week."},
            ],
            max_tokens=600,
            temperature=0.9,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]
        suggestions = _json.loads(raw)

        return TopicSuggestionsResponse(
            suggestions=[
                TopicSuggestion(
                    topic=s.get("topic", ""),
                    score=max(1, min(10, int(s.get("score", 5)))),
                    angle=s.get("angle", "how-to"),
                    why=s.get("why", ""),
                )
                for s in suggestions[:5]
            ]
        )
    except Exception as e:
        logger.error("Topic suggestions failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate topic suggestions. Try again.",
        )


# ── GET / PUT /api/videos/preferences — Channel Intelligence ────────

class PreferencesRequest(BaseModel):
    """PUT /api/videos/channel-preferences body — onboarding + settings."""
    niches: list[str] = Field(default_factory=list)
    tone_style: str = Field("confident, direct, no-fluff educator", max_length=300)
    target_audience: str = Field("general audience", max_length=300)
    channel_goal: str = Field("growth")
    posting_frequency: str = Field("weekly")


class PreferencesResponse(BaseModel):
    niches: list[str] = []
    tone_style: str = "confident, direct, no-fluff educator"
    target_audience: str = "general audience"
    channel_goal: str = "growth"
    posting_frequency: str = "weekly"
    updated_at: str | None = None


@router.get("/channel-preferences", response_model=PreferencesResponse)
async def get_channel_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's channel preferences."""
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        return PreferencesResponse()

    import json as _json
    try:
        niches = _json.loads(prefs.niches_json) if prefs.niches_json else []
    except Exception:
        niches = []

    return PreferencesResponse(
        niches=niches,
        tone_style=prefs.tone_style,
        target_audience=prefs.target_audience,
        channel_goal=prefs.channel_goal,
        posting_frequency=prefs.posting_frequency,
        updated_at=prefs.updated_at.isoformat() if prefs.updated_at else None,
    )


@router.put("/channel-preferences", response_model=PreferencesResponse)
async def update_channel_preferences(
    body: PreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the user's channel preferences (onboarding + settings)."""
    import json as _json

    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()

    niches_str = _json.dumps(body.niches[:15])  # cap at 15

    if prefs:
        prefs.niches_json = niches_str
        prefs.tone_style = body.tone_style
        prefs.target_audience = body.target_audience
        prefs.channel_goal = body.channel_goal
        prefs.posting_frequency = body.posting_frequency
        prefs.updated_at = datetime.now(timezone.utc)
    else:
        prefs = UserPreferences(
            user_id=current_user.id,
            niches_json=niches_str,
            tone_style=body.tone_style,
            target_audience=body.target_audience,
            channel_goal=body.channel_goal,
            posting_frequency=body.posting_frequency,
        )
        db.add(prefs)

    await db.commit()
    logger.info("Updated preferences for user %s: niches=%s goal=%s", current_user.email, body.niches, body.channel_goal)

    return PreferencesResponse(
        niches=body.niches,
        tone_style=body.tone_style,
        target_audience=body.target_audience,
        channel_goal=body.channel_goal,
        posting_frequency=body.posting_frequency,
        updated_at=prefs.updated_at.isoformat() if prefs.updated_at else None,
    )


# ── GET /api/videos/performance-profile — Adaptive Intelligence ─────

class PerformanceProfileResponse(BaseModel):
    recommended_title_style: str = "curiosity"
    title_style_probabilities: dict[str, float] = {}
    recommended_thumbnail_style: str = "bold_curiosity"
    thumbnail_style_probabilities: dict[str, float] = {}
    hook_mode: str = "balanced"
    avg_retention_pct: float = 0.0
    avg_ctr_pct: float = 0.0
    total_data_points: int = 0
    adaptation_active: bool = False


@router.get("/performance-profile", response_model=PerformanceProfileResponse)
async def get_performance_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's adaptive performance profile.

    Shows which title/thumbnail styles perform best, hook mode,
    and whether the system has enough data to adapt.
    """
    perf_stmt = (
        select(ContentPerformance)
        .where(ContentPerformance.user_id == current_user.id)
        .order_by(ContentPerformance.created_at.desc())
        .limit(50)
    )
    perf_rows = (await db.execute(perf_stmt)).scalars().all()

    raw_rows = [
        {
            "title_style_used": getattr(r, "title_style_used", None),
            "thumbnail_concept_used": r.thumbnail_concept_used,
            "engagement_score": r.engagement_score,
            "ctr_pct": r.ctr_pct,
            "avg_view_duration_pct": r.avg_view_duration_pct,
        }
        for r in perf_rows
    ]

    from backend.adaptive_engine import get_user_performance_profile, profile_to_dict
    profile = get_user_performance_profile(raw_rows)
    d = profile_to_dict(profile)

    return PerformanceProfileResponse(**d)


# ── Analytics: Manual metrics refresh ────────────────────────────────

@router.post("/refresh-metrics")
async def refresh_metrics(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger YouTube analytics ingestion for the current user.

    Fetches real metrics from YouTube for videos published 24–72 hours ago
    that haven't had their 48h capture yet.  Returns a summary of results.

    This is primarily for admin/debugging use — the analytics worker runs
    this automatically every hour.
    """
    from backend.analytics_worker import manual_refresh_metrics

    try:
        result = await manual_refresh_metrics(current_user.id)
        return result
    except Exception as exc:
        logger.warning("Manual metrics refresh failed for user %s: %s", current_user.id, exc)
        return {"eligible": 0, "updated": 0, "error": str(exc)}
