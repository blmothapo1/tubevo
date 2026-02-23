"""
uploader.py — Upload videos to YouTube via the Data API v3 (resumable upload).

Usage:
    from uploader import upload_video

    video_id = upload_video(
        file_path="output/final.mp4",
        title="5 Frugal Habits …",
        description="In this video …",
        tags=["wealth", "frugality"],
        privacy="private",          # private | unlisted | public
        category_id="22",           # People & Blogs
    )
"""

from __future__ import annotations

import http.client as httplib
import logging
import os
import random
import sys
import time

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import config

logger = logging.getLogger("tubevo.uploader")

# ── Constants ────────────────────────────────────────────────────────
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
RETRIABLE_EXCEPTIONS = (httplib.NotConnected, httplib.IncompleteRead,
                        httplib.CannotSendRequest,
                        httplib.CannotSendHeader,
                        httplib.ResponseNotReady,
                        httplib.BadStatusLine)
MAX_RETRIES = 10


# ── Auth ─────────────────────────────────────────────────────────────

def get_authenticated_service():
    """Return an authorised ``youtube`` API resource.

    * First run opens a browser-based OAuth consent screen and stores
      the refresh token in ``config.OAUTH_TOKEN_FILE``.
    * Subsequent runs silently refresh the token.
    """
    credentials = None

    if os.path.exists(config.OAUTH_TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            config.OAUTH_TOKEN_FILE, config.YOUTUBE_UPLOAD_SCOPE
        )

    # If there are no (valid) credentials, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not os.path.exists(config.CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"OAuth client-secrets file not found: {config.CLIENT_SECRETS_FILE}\n"
                    "Download it from the Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.CLIENT_SECRETS_FILE, config.YOUTUBE_UPLOAD_SCOPE
            )
            credentials = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(config.OAUTH_TOKEN_FILE, "w") as token_file:
            token_file.write(credentials.to_json())

    return build(
        config.YOUTUBE_API_SERVICE_NAME,
        config.YOUTUBE_API_VERSION,
        credentials=credentials,
    )


# ── Upload ───────────────────────────────────────────────────────────

def upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str | None = None,
    category_id: str | None = None,
) -> str | None:
    """Upload *file_path* to YouTube and return the new video ID, or None on
    non-fatal failures (e.g. upload-limit exceeded).

    Supports **resumable uploads** with automatic retry on transient
    errors.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    privacy = privacy or config.DEFAULT_PRIVACY
    category_id = category_id or config.DEFAULT_VIDEO_CATEGORY
    tags = tags or config.DEFAULT_TAGS

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(file_path, chunksize=10 * 1024 * 1024,  # 10 MB chunks
                            resumable=True)

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    logger.info("Uploading: %s", file_path)
    logger.info("    Title   : %s", title)
    logger.info("    Privacy : %s", privacy)
    logger.info("    Category: %s", category_id)
    logger.info("    Tags    : %s", ', '.join(tags))

    try:
        video_id = _resumable_upload(request)
        return video_id
    except HttpError as e:
        error_str = str(e)
        reason = ""
        if hasattr(e, "error_details") and e.error_details:
            detail = e.error_details[0]
            if isinstance(detail, dict):
                reason = detail.get("reason", "")
        if reason == "uploadLimitExceeded" or "exceeded the number of videos" in error_str:
            logger.warning("YouTube upload limit exceeded!")
            logger.warning("    Your account has hit YouTube's daily upload cap.")
            logger.warning("    The video was built successfully and saved locally.")
            logger.warning("    You can retry the upload later or upload manually.")
            logger.warning("    Video file: %s", file_path)
            return None
        raise


# ── Resumable-upload loop ────────────────────────────────────────────

def _resumable_upload(insert_request) -> str:
    """Execute the resumable upload with exponential back-off."""
    response = None
    error = None
    retry = 0

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("Uploaded %d%%", pct)
            if response is not None:
                video_id = response.get("id", "unknown")
                logger.info("Upload complete!  Video ID: %s", video_id)
                logger.info("    https://www.youtube.com/watch?v=%s", video_id)
                return video_id
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = f"HTTP {e.resp.status}: retriable error — {e.content}"
            else:
                raise
        except RETRIABLE_EXCEPTIONS as e:
            error = f"Retriable transport error: {e}"

        if error is not None:
            retry += 1
            if retry > MAX_RETRIES:
                logger.error("Gave up after %d retries.", MAX_RETRIES)
                raise RuntimeError(f"Upload failed after {MAX_RETRIES} retries.")
            sleep_seconds = random.random() * (2 ** retry)
            logger.warning("%s — Retrying in %.1fs … (attempt %d/%d)", error, sleep_seconds, retry, MAX_RETRIES)
            time.sleep(sleep_seconds)
            error = None

    return "unknown"


# ── Post-upload verification ─────────────────────────────────────────

def verify_video_processed(
    video_id: str,
    *,
    max_wait: int = 300,
    poll_interval: int = 15,
) -> bool:
    """Poll YouTube until the video's upload/processing status is complete.

    Returns True if the video is confirmed as processed and accessible,
    False if it times out or encounters an error.

    Parameters
    ----------
    video_id : str
        The YouTube video ID to check.
    max_wait : int
        Maximum seconds to wait for processing (default 5 minutes).
    poll_interval : int
        Seconds between status checks (default 15).
    """
    youtube = get_authenticated_service()
    elapsed = 0

    logger.info("Verifying video %s is processed on YouTube (timeout %ds) …", video_id, max_wait)

    while elapsed < max_wait:
        try:
            resp = youtube.videos().list(
                part="status,processingDetails",
                id=video_id,
            ).execute()

            items = resp.get("items", [])
            if not items:
                logger.warning("Video %s not found via API — may still be propagating.", video_id)
                time.sleep(poll_interval)
                elapsed += poll_interval
                continue

            video = items[0]
            upload_status = video.get("status", {}).get("uploadStatus", "")
            processing = video.get("processingDetails", {})
            processing_status = processing.get("processingStatus", "")

            logger.info(
                "    Upload status: %s | Processing status: %s  (%ds elapsed)",
                upload_status, processing_status or "n/a", elapsed,
            )

            if upload_status == "processed":
                logger.info("Video %s is fully processed and live ✓", video_id)
                return True

            if upload_status in ("failed", "rejected", "deleted"):
                failure_reason = video.get("status", {}).get("failureReason", "unknown")
                rejection_reason = video.get("status", {}).get("rejectionReason", "")
                logger.error(
                    "Video %s upload failed — status: %s, failure: %s, rejection: %s",
                    video_id, upload_status, failure_reason, rejection_reason,
                )
                return False

        except HttpError as e:
            logger.warning("API error while checking video status: %s", e)

        time.sleep(poll_interval)
        elapsed += poll_interval

    logger.warning(
        "Video %s still processing after %ds — it may finish later. "
        "Check https://www.youtube.com/watch?v=%s",
        video_id, max_wait, video_id,
    )
    return False


# ── Playlist assignment ──────────────────────────────────────────────

def add_video_to_playlist(video_id: str, playlist_id: str | None = None) -> bool:
    """Add a video to a YouTube playlist.

    Parameters
    ----------
    video_id : str
        The YouTube video ID to add.
    playlist_id : str | None
        The playlist ID.  If None, reads from ``config.DEFAULT_PLAYLIST_ID``.
        If that is also empty, the step is silently skipped.

    Returns True on success, False on failure or skip.
    """
    playlist_id = playlist_id or getattr(config, "DEFAULT_PLAYLIST_ID", "")
    if not playlist_id:
        logger.info("No playlist ID configured — skipping playlist assignment.")
        return False

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        },
    }

    try:
        youtube.playlistItems().insert(
            part="snippet",
            body=body,
        ).execute()
        logger.info("Video %s added to playlist %s ✓", video_id, playlist_id)
        return True
    except HttpError as e:
        logger.error("Failed to add video %s to playlist %s: %s", video_id, playlist_id, e)
        return False


# ── Thumbnail upload ─────────────────────────────────────────────────

def set_video_thumbnail(video_id: str, thumbnail_path: str) -> bool:
    """Upload a custom thumbnail for a YouTube video.

    Requires the channel to be verified for custom thumbnails.
    Returns True on success, False on failure.
    """
    if not os.path.isfile(thumbnail_path):
        logger.warning("Thumbnail file not found: %s — skipping.", thumbnail_path)
        return False

    youtube = get_authenticated_service()

    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
        ).execute()
        logger.info("Custom thumbnail set for video %s ✓", video_id)
        return True
    except HttpError as e:
        logger.error("Failed to set thumbnail for video %s: %s", video_id, e)
        return False


# ── Quick CLI test ───────────────────────────────────────────────────
if __name__ == "__main__":
    # Dry-run: just confirm auth works
    logger.info("Authenticating with YouTube …")
    svc = get_authenticated_service()
    logger.info("Authenticated successfully. Ready to upload.")
