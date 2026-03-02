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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import async_session_factory, get_db
from backend.encryption import decrypt
from backend.models import ContentMemory, ContentPerformance, OAuthToken, User, UserApiKeys, UserPreferences, VideoRecord
from backend.rate_limit import limiter

logger = logging.getLogger("tubevo.backend.videos")

router = APIRouter(prefix="/api/videos", tags=["Videos"])

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Maximum time a pipeline is allowed to run before we consider it dead.
PIPELINE_TIMEOUT_SECONDS = 10 * 60  # 10 minutes
# If a record has been "generating" for longer than this, mark it failed.
STALE_JOB_MINUTES = 15

# ── In-memory progress tracker (Phase 6) ────────────────────────────
# Keyed by record_id → { "step": str, "pct": int, "started_at": float }
# This avoids hammering the DB on every sub-step update.
_progress_store: dict[str, dict] = {}

# ── Plan-based monthly video limits ─────────────────────────────────
PLAN_MONTHLY_LIMITS: dict[str, int] = {
    "free": 1,
    "starter": 10,
    "pro": 50,
    "agency": 999_999,   # effectively unlimited
}


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
    srt_path: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    thumbnail_path: str | None = None
    error_message: str | None = None
    progress_step: str | None = None
    progress_pct: int = 0
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
    openai_key = decrypt(user_keys.openai_api_key) if user_keys and user_keys.openai_api_key else ""
    elevenlabs_key = decrypt(user_keys.elevenlabs_api_key) if user_keys and user_keys.elevenlabs_api_key else ""
    pexels_key = decrypt(user_keys.pexels_api_key) if user_keys and user_keys.pexels_api_key else ""

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
        # Phase 4 & 5 video production preferences
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
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
    yt_access_token = oauth_token.access_token if oauth_token else None
    yt_refresh_token = oauth_token.refresh_token if oauth_token else None

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
    """
    logger.info("Background pipeline starting for record %s", record_id)

    # Initialise in-memory progress tracker
    _progress_store[record_id] = {"step": "Starting…", "pct": 0, "started_at": time.time()}

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
        result = {"error": f"Video generation timed out after {PIPELINE_TIMEOUT_SECONDS // 60} minutes."}
    except Exception as e:
        tb = traceback.format_exc()
        # Phase 8: mask any API keys that might appear in tracebacks
        from config import mask_secrets
        safe_tb = mask_secrets(tb)
        safe_msg = mask_secrets(str(e))
        logger.error("Pipeline background task failed for record %s: %s\n%s", record_id, safe_msg, safe_tb)
        result = {"error": safe_msg}

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
                from config import mask_secrets as _mask
                row.error_message = _mask(result["error"])[:2000]
            elif result.get("youtube_video_id"):
                row.status = "posted"
                row.title = result.get("title", topic)
                row.file_path = result.get("file_path")
                row.srt_path = result.get("srt_path")
                row.youtube_video_id = result["youtube_video_id"]
                row.youtube_url = f"https://www.youtube.com/watch?v={result['youtube_video_id']}"
            elif result.get("file_path"):
                row.status = "completed"
                row.title = result.get("title", topic)
                row.file_path = result.get("file_path")
                row.srt_path = result.get("srt_path")
            else:
                row.status = "completed"
                row.title = result.get("title", topic)

            row.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Updated VideoRecord %s → status=%s", record_id, row.status)

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
    except Exception:
        logger.exception("Failed to update VideoRecord %s after pipeline", record_id)
    finally:
        # Clean up in-memory progress store
        _progress_store.pop(record_id, None)


# ── Plan-based limit enforcement ─────────────────────────────────────

async def _enforce_plan_limit(user: User, db: AsyncSession) -> None:
    """Raise HTTP 403 if the user has exhausted their monthly video quota."""
    plan = user.plan or "free"
    limit = PLAN_MONTHLY_LIMITS.get(plan, PLAN_MONTHLY_LIMITS["free"])

    # Count videos created this calendar month (regardless of status)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count_stmt = (
        select(func.count())
        .select_from(VideoRecord)
        .where(
            VideoRecord.user_id == user.id,
            VideoRecord.created_at >= month_start,
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


# Serialise pipeline runs so that the module-level key patching is thread-safe.
# Only one video generation runs at a time.  This is acceptable because the
# pipeline is CPU/IO-heavy and Railway's single-container model doesn't
# benefit from parallel builds.
_pipeline_lock = threading.Lock()


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

    A threading lock ensures only one pipeline runs at a time so that the
    module-level key patching doesn't collide across concurrent requests.
    """
    with _pipeline_lock:
        return _run_pipeline_locked(
            topic=topic,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
            record_id=record_id,
        )


def _run_pipeline_locked(
    *,
    topic: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
    record_id: str | None = None,
) -> dict:
    """Inner pipeline function — runs under ``_pipeline_lock``."""

    def _report(step: str, pct: int) -> None:
        """Update in-memory progress for real-time polling."""
        if record_id and record_id in _progress_store:
            _progress_store[record_id]["step"] = step
            _progress_store[record_id]["pct"] = pct

    # Ensure the top-level project dir is on sys.path so we can import
    # the Phase 1 modules (config, script_generator, etc.)
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # ── Temporarily override env vars with user's keys ───────────────
    import config as app_config  # noqa: F811 — top-level config.py

    old_openai = getattr(app_config, "OPENAI_API_KEY", None)
    if not hasattr(app_config, "OPENAI_API_KEY"):
        setattr(app_config, "OPENAI_API_KEY", None)
    setattr(app_config, "OPENAI_API_KEY", user_api_keys["openai_api_key"])

    import script_generator
    script_generator._client = None  # force re-init with new key

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
        _report("Generating script…", 5)
        logger.info("Pipeline step 1/5: Generating script for '%s'", topic)
        script_kwargs: dict = {}
        if variation_ctx:
            script_kwargs["temperature"] = variation_ctx.script_temperature
            script_kwargs["avoidance_prompt"] = variation_ctx.avoidance_prompt
        # Inject user preferences for adaptive generation
        _user_prefs = user_api_keys.get("_user_preferences", {})
        if _user_prefs:
            script_kwargs["user_preferences"] = _user_prefs
        script = script_generator.generate_script(topic, **script_kwargs)
        (OUTPUT_DIR / "latest_script.txt").write_text(script, encoding="utf-8")
        logger.info("Pipeline step 1/5: Script generated (%d chars)", len(script))
        _report("Script ready", 15)

        # ── Step 2: Generate metadata ────────────────────────────────
        _report("Generating metadata…", 18)
        logger.info("Pipeline step 2/5: Generating metadata")
        meta_kwargs: dict = {}
        if variation_ctx:
            meta_kwargs["temperature"] = variation_ctx.metadata_temperature
            meta_kwargs["avoidance_prompt"] = variation_ctx.metadata_avoidance
        if _user_prefs:
            meta_kwargs["user_preferences"] = _user_prefs
        metadata = script_generator.generate_metadata(script, topic, **meta_kwargs)
        result["title"] = metadata.get("title", topic)
        logger.info("Pipeline step 2/5: Metadata ready — title: %s", result["title"])
        _report("Metadata ready", 22)

        # ── Step 3: Generate voiceover ───────────────────────────────
        _report("Generating voiceover…", 25)
        logger.info("Pipeline step 3/5: Generating voiceover")
        import voiceover as voiceover_mod
        old_el_key = voiceover_mod.ELEVENLABS_API_KEY
        old_el_voice = voiceover_mod.DEFAULT_VOICE_ID
        voiceover_mod.ELEVENLABS_API_KEY = user_api_keys["elevenlabs_api_key"]
        if user_api_keys.get("elevenlabs_voice_id"):
            voiceover_mod.DEFAULT_VOICE_ID = user_api_keys["elevenlabs_voice_id"]

        # Phase 7: voice tone variation — pass jittered stability/similarity/style
        voice_kwargs: dict = {
            "speed": float(user_api_keys["speech_speed"]) if user_api_keys.get("speech_speed") else None,
        }
        if variation_ctx:
            voice_kwargs["stability"] = variation_ctx.voice_params.stability
            voice_kwargs["similarity_boost"] = variation_ctx.voice_params.similarity_boost
            voice_kwargs["style"] = variation_ctx.voice_params.style

        audio_path = voiceover_mod.generate_voiceover(script, **voice_kwargs)
        logger.info("Pipeline step 3/5: Voiceover saved → %s", audio_path)
        _report("Voiceover ready", 35)

        # Restore ElevenLabs keys
        voiceover_mod.ELEVENLABS_API_KEY = old_el_key
        voiceover_mod.DEFAULT_VOICE_ID = old_el_voice

        # ── Step 3b: Audio polish (Phase 4) ─────────────────────────
        _report("Polishing audio…", 36)
        try:
            from audio_processor import polish_audio
            # Phase 7: music mood rotation — pass frequencies from variation context
            polish_kwargs: dict = {}
            if variation_ctx:
                polish_kwargs["music_frequencies"] = variation_ctx.music_mood.frequencies
                polish_kwargs["music_tremolo_base"] = variation_ctx.music_mood.tremolo_base
            polished_path = polish_audio(audio_path, **polish_kwargs)
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
        old_pexels = stock_mod.PEXELS_API_KEY
        if user_api_keys.get("pexels_api_key"):
            stock_mod.PEXELS_API_KEY = user_api_keys["pexels_api_key"]

        scene_clip_data = None
        try:
            from scene_planner import plan_scenes
            # Phase 7: pass style_seed from variation context for better rotation
            plan_kwargs: dict = {
                "openai_api_key": user_api_keys["openai_api_key"],
                "target_total_clips": 10,
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

            # Download per-scene clips
            _report("Downloading stock footage…", 48)
            logger.info("Pipeline step 4b/6: Downloading scene-aware stock footage")
            from stock_footage import download_clips_for_scenes
            scene_clip_data = download_clips_for_scenes(scene_plans)
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
        import video_builder as _vb_mod
        video_path = build_video(
            audio_path=audio_path,
            title=metadata["title"],
            script=script,
            scene_clip_data=scene_clip_data,
            subtitle_style=user_api_keys.get("subtitle_style", "bold_pop"),
            burn_captions=user_api_keys.get("burn_captions", True),
        )
        result["file_path"] = video_path
        # Phase 5: capture SRT path from video builder
        result["srt_path"] = getattr(_vb_mod, "last_srt_path", None)
        logger.info("Pipeline step 4c/6: Video built → %s", video_path)
        _report("Video built", 78)

        # Restore Pexels key
        stock_mod.PEXELS_API_KEY = old_pexels

        # ── Step 5: Generate thumbnail variants ────────────────────
        _report("Generating thumbnails…", 80)
        logger.info("Pipeline step 5/6: Generating 3 thumbnail variants")
        from thumbnail import generate_thumbnail, generate_thumbnail_variants
        thumbnail_variants = generate_thumbnail_variants(metadata["title"])
        # Primary thumbnail = bold_curiosity (used for upload)
        thumbnail_path = thumbnail_variants[0]["path"] if thumbnail_variants else generate_thumbnail(metadata["title"])
        result["thumbnail_variants"] = thumbnail_variants
        logger.info("Pipeline step 5/6: Generated %d thumbnail variants", len(thumbnail_variants))
        _report("Thumbnails ready", 85)

        # ── Step 6: Upload to YouTube (if user connected) ────────────
        if yt_access_token:
            _report("Uploading to YouTube…", 88)
            logger.info("Pipeline step 6/6: Uploading to YouTube")
            youtube_video_id = _upload_with_user_tokens(
                video_path=video_path,
                metadata=metadata,
                thumbnail_path=thumbnail_path,
                access_token=yt_access_token,
                refresh_token=yt_refresh_token,
            )
            if youtube_video_id:
                result["youtube_video_id"] = youtube_video_id
                _report("Uploaded to YouTube!", 100)
        else:
            logger.info("Pipeline step 6/6: Skipping upload — no YouTube connection")
            _report("Complete", 100)

    except Exception:
        # Phase 8: mask keys in the traceback logged here
        logger.exception("Pipeline error during locked execution")
        raise
    finally:
        # ── Always restore original keys ─────────────────────────────
        setattr(app_config, "OPENAI_API_KEY", old_openai)
        script_generator._client = None

    # ── Phase 7: Attach variation metadata for content memory ────────
    if variation_ctx:
        result["_temperature_used"] = variation_ctx.script_temperature
        result["_music_mood"] = variation_ctx.music_mood.label

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
) -> str | None:
    """Upload a video to YouTube using per-user OAuth tokens from the DB.

    This replaces the CLI uploader's ``get_authenticated_service()`` which
    reads from a local ``token.json`` file.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import config as app_config

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

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Refreshed YouTube access token")
        except Exception as e:
            logger.error("Failed to refresh YouTube token: %s", e)
            raise RuntimeError(
                "YouTube token expired and could not be refreshed. "
                "Please reconnect your YouTube channel in Settings."
            ) from e

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "categoryId": getattr(app_config, "DEFAULT_VIDEO_CATEGORY", "22"),
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
                    raise RuntimeError(f"YouTube upload failed after {max_retries} retries")
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
                        raise RuntimeError(f"YouTube upload rate-limited after {max_retries} retries")
                    wait = min(random.random() * (2 ** retry), 60.0)
                    logger.warning("YouTube rate limit (403), retrying in %.1fs", wait)
                    time.sleep(wait)
                    continue
            raise
        except (ConnectionError, TimeoutError, OSError) as net_err:
            # Phase 8: Retry on transient network errors
            retry += 1
            if retry > max_retries:
                raise RuntimeError(
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

    return video_id


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

    # Monthly usage for plan limit display
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

    # ── Fetch the user's API keys (BYOK) ─────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    openai_key = decrypt(user_keys.openai_api_key) if user_keys and user_keys.openai_api_key else ""
    elevenlabs_key = decrypt(user_keys.elevenlabs_api_key) if user_keys and user_keys.elevenlabs_api_key else ""
    pexels_key = decrypt(user_keys.pexels_api_key) if user_keys and user_keys.pexels_api_key else ""

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
        # Phase 4 & 5 video production preferences
        "subtitle_style": getattr(user_keys, "subtitle_style", "bold_pop") if user_keys else "bold_pop",
        "burn_captions": getattr(user_keys, "burn_captions", True) if user_keys else True,
        "speech_speed": getattr(user_keys, "speech_speed", None) if user_keys else None,
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
    yt_access_token = oauth_token.access_token if oauth_token else None
    yt_refresh_token = oauth_token.refresh_token if oauth_token else None

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

    return {
        "global_generating": global_count,
        "user_generating": user_count,
    }


# ── Video preferences schemas (Phase 4 & 5) ─────────────────────────

class VideoPreferences(BaseModel):
    subtitle_style: str = "bold_pop"
    burn_captions: bool = True
    speech_speed: str | None = None  # e.g. "1.0", "0.85", "1.1"


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

    # Validate subtitle style
    valid_styles = {"bold_pop", "minimal", "cinematic", "accent_highlight"}
    if body.subtitle_style not in valid_styles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid subtitle style. Choose from: {', '.join(sorted(valid_styles))}",
        )

    # Validate speech speed
    if body.speech_speed is not None:
        try:
            speed_val = float(body.speech_speed)
            if not (0.7 <= speed_val <= 1.2):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Speech speed must be a number between 0.7 and 1.2",
            )

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
    openai_key = decrypt(user_keys.openai_api_key) if user_keys and user_keys.openai_api_key else ""

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
    if user_prefs and user_prefs.niches_json:
        import json as _prefs_json
        try:
            user_niches = _prefs_json.loads(user_prefs.niches_json)
            if user_niches:
                niche_context = f"This channel covers: {', '.join(user_niches[:3])}. Suggest topics within these niches.\n"
        except Exception:
            pass

    # Generate suggestions via OpenAI
    import json as _json
    from openai import OpenAI

    avoidance = ""
    if past_titles:
        avoidance = "\n\nALREADY COVERED (do NOT suggest these or close variations):\n"
        for t in past_titles[:15]:
            avoidance += f"  - {t}\n"

    system = (
        f"You suggest YouTube video topics. {niche_context}\n"
        "Return ONLY a JSON array of exactly 5 objects. Each object has:\n"
        '  "topic" — a specific, ready-to-use video topic (not generic)\n'
        '  "score" — demand score 1-10 (10=highest search demand + low competition)\n'
        '  "angle" — the narrative angle: one of "myth-bust", "story", "how-to", "contrarian", "case-study"\n'
        '  "why"   — one sentence: why this topic has high potential right now\n\n'
        "RULES:\n"
        "- Mix angles — never suggest 5 of the same type.\n"
        "- Topics must be SPECIFIC (not 'how to save money' — too broad).\n"
        "- Favor timely, emotionally engaging, or contrarian topics.\n"
        "- Score honestly — not everything is a 10.\n"
        "Do NOT include markdown fences. Return raw JSON only."
        f"{avoidance}"
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
    """PUT /api/videos/preferences body — onboarding + settings."""
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


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
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


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
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
