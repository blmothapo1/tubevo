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
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import async_session_factory, get_db
from backend.models import OAuthToken, User, UserApiKeys, VideoRecord
from backend.rate_limit import limiter

logger = logging.getLogger("tubevo.backend.videos")

router = APIRouter(prefix="/api/videos", tags=["Videos"])

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger the full-auto pipeline for a given topic.

    Creates a VideoRecord in the database, kicks off the pipeline in the
    background, and returns immediately so the HTTP request doesn't time out.
    The frontend can poll GET /api/videos/{id}/status for progress.
    """
    logger.info("User %s requested video generation: '%s'", current_user.email, body.topic)

    # ── Fetch the user's API keys (BYOK) ─────────────────────────────
    keys_result = await db.execute(
        select(UserApiKeys).where(UserApiKeys.user_id == current_user.id)
    )
    user_keys = keys_result.scalar_one_or_none()

    if not user_keys or not user_keys.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your OpenAI API key in Settings → API Keys before generating videos.",
        )
    if not user_keys.elevenlabs_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please add your ElevenLabs API key in Settings → API Keys before generating videos.",
        )

    # Pack the user's keys for the pipeline
    user_api_keys = {
        "openai_api_key": user_keys.openai_api_key,
        "elevenlabs_api_key": user_keys.elevenlabs_api_key,
        "elevenlabs_voice_id": user_keys.elevenlabs_voice_id or "",
        "pexels_api_key": user_keys.pexels_api_key or "",
    }

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

    # ── Create a pending record ──────────────────────────────────────
    record = VideoRecord(
        user_id=current_user.id,
        topic=body.topic,
        title=body.topic,  # will be updated by the pipeline
        status="generating",
    )
    db.add(record)
    await db.flush()  # get the id
    record_id = record.id

    # ── Kick off the pipeline in the background ──────────────────────
    background_tasks.add_task(
        _run_pipeline_background,
        record_id=record_id,
        topic=body.topic,
        user_id=current_user.id,
        user_api_keys=user_api_keys,
        yt_access_token=yt_access_token,
        yt_refresh_token=yt_refresh_token,
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

    This function owns its own DB session (the request session is already
    closed by the time this runs).
    """
    try:
        result = await asyncio.to_thread(
            _run_pipeline_sync,
            topic=topic,
            user_api_keys=user_api_keys,
            yt_access_token=yt_access_token,
            yt_refresh_token=yt_refresh_token,
        )
    except Exception as e:
        logger.exception("Pipeline background task failed for record %s: %s", record_id, e)
        result = {"error": str(e)}

    # ── Update the DB record with results ────────────────────────────
    async with async_session_factory() as db:
        try:
            stmt = select(VideoRecord).where(VideoRecord.id == record_id)
            row = (await db.execute(stmt)).scalar_one_or_none()
            if not row:
                logger.error("VideoRecord %s not found after pipeline!", record_id)
                return

            if "error" in result:
                row.status = "failed"
                row.error_message = result["error"][:2000]  # truncate
            elif result.get("youtube_video_id"):
                row.status = "posted"
                row.title = result.get("title", topic)
                row.file_path = result.get("file_path")
                row.youtube_video_id = result["youtube_video_id"]
                row.youtube_url = f"https://www.youtube.com/watch?v={result['youtube_video_id']}"
            elif result.get("file_path"):
                row.status = "completed"
                row.title = result.get("title", topic)
                row.file_path = result.get("file_path")
            else:
                row.status = "completed"
                row.title = result.get("title", topic)

            row.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Updated VideoRecord %s → status=%s", record_id, row.status)
        except Exception:
            await db.rollback()
            logger.exception("Failed to update VideoRecord %s", record_id)


def _run_pipeline_sync(
    *,
    topic: str,
    user_api_keys: dict,
    yt_access_token: str | None,
    yt_refresh_token: str | None,
) -> dict:
    """Synchronous pipeline: script → voiceover → video → (optional) upload.

    Uses per-user API keys (BYOK model) and per-user OAuth tokens
    instead of server-level env vars.
    """
    # Ensure the top-level project dir is on sys.path so we can import
    # the Phase 1 modules (config, script_generator, etc.)
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # ── Temporarily override env vars with user's keys ───────────────
    # The Phase 1 modules (script_generator, voiceover, stock_footage)
    # read API keys from env vars / module-level globals.  We patch them
    # for the duration of this call so each user uses their own keys.
    import config as app_config  # noqa: F811 — top-level config.py

    # Patch OpenAI key (used by script_generator via config.OPENAI_API_KEY)
    old_openai = app_config.OPENAI_API_KEY
    app_config.OPENAI_API_KEY = user_api_keys["openai_api_key"]

    # We also need to reset the cached OpenAI client in script_generator
    import script_generator
    script_generator._client = None  # force re-init with new key

    result: dict = {"title": topic}

    try:
        # ── Step 1: Generate script ──────────────────────────────────
        logger.info("Pipeline step 1/5: Generating script for '%s'", topic)
        script = script_generator.generate_script(topic)
        (OUTPUT_DIR / "latest_script.txt").write_text(script, encoding="utf-8")

        # ── Step 2: Generate metadata ────────────────────────────────
        logger.info("Pipeline step 2/5: Generating metadata")
        metadata = script_generator.generate_metadata(script, topic)
        result["title"] = metadata.get("title", topic)

        # ── Step 3: Generate voiceover ───────────────────────────────
        logger.info("Pipeline step 3/5: Generating voiceover")
        import voiceover as voiceover_mod
        # Patch ElevenLabs keys
        old_el_key = voiceover_mod.ELEVENLABS_API_KEY
        old_el_voice = voiceover_mod.DEFAULT_VOICE_ID
        voiceover_mod.ELEVENLABS_API_KEY = user_api_keys["elevenlabs_api_key"]
        if user_api_keys.get("elevenlabs_voice_id"):
            voiceover_mod.DEFAULT_VOICE_ID = user_api_keys["elevenlabs_voice_id"]

        audio_path = voiceover_mod.generate_voiceover(script)

        # Restore ElevenLabs keys
        voiceover_mod.ELEVENLABS_API_KEY = old_el_key
        voiceover_mod.DEFAULT_VOICE_ID = old_el_voice

        # ── Step 4: Build video ──────────────────────────────────────
        logger.info("Pipeline step 4/5: Building video")
        # Patch Pexels key for stock footage
        import stock_footage as stock_mod
        old_pexels = stock_mod.PEXELS_API_KEY
        if user_api_keys.get("pexels_api_key"):
            stock_mod.PEXELS_API_KEY = user_api_keys["pexels_api_key"]

        from video_builder import build_video
        video_path = build_video(audio_path=audio_path, title=metadata["title"], script=script)
        result["file_path"] = video_path

        # Restore Pexels key
        stock_mod.PEXELS_API_KEY = old_pexels

        # ── Step 4b: Generate thumbnail ──────────────────────────────
        logger.info("Pipeline step 4b: Generating thumbnail")
        from thumbnail import generate_thumbnail
        thumbnail_path = generate_thumbnail(metadata["title"])

        # ── Step 5: Upload to YouTube (if user connected) ────────────
        if yt_access_token:
            logger.info("Pipeline step 5/5: Uploading to YouTube")
            youtube_video_id = _upload_with_user_tokens(
                video_path=video_path,
                metadata=metadata,
                thumbnail_path=thumbnail_path,
                access_token=yt_access_token,
                refresh_token=yt_refresh_token,
            )
            if youtube_video_id:
                result["youtube_video_id"] = youtube_video_id
        else:
            logger.info("Pipeline step 5/5: Skipping upload — no YouTube connection")

    finally:
        # ── Always restore original keys ─────────────────────────────
        app_config.OPENAI_API_KEY = old_openai
        script_generator._client = None  # reset client

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
            "categoryId": app_config.DEFAULT_VIDEO_CATEGORY,
        },
        "status": {
            "privacyStatus": app_config.DEFAULT_PRIVACY,
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
                logger.warning("Retriable error %s, retrying in %.1fs", e.resp.status, wait)
                time.sleep(wait)
                continue
            raise

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
    result = await db.execute(
        select(VideoRecord).where(
            VideoRecord.id == video_id,
            VideoRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Video not found.")

    return {
        "id": record.id,
        "status": record.status,
        "title": record.title,
        "error_message": record.error_message,
        "youtube_url": record.youtube_url,
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }


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
