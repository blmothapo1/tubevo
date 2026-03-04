# filepath: backend/routers/youtube.py
"""
YouTube / Google OAuth router — /oauth/youtube/*

Endpoints
---------
GET  /oauth/youtube/authorize  — Generate Google OAuth consent URL
POST /oauth/youtube/callback   — Exchange auth code for tokens, store per-user
GET  /oauth/youtube/status     — Check if current user has a YouTube connection
DELETE /oauth/youtube/disconnect — Remove stored tokens (revoke + delete)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.config import get_settings
from backend.database import get_db
from backend.encryption import decrypt, encrypt
from backend.models import OAuthToken, User
from backend.rate_limit import limiter
from backend.schemas import (
    MessageResponse,
    YouTubeAuthURLResponse,
    YouTubeCallbackRequest,
    YouTubeConnectionResponse,
)

logger = logging.getLogger("tubevo.backend.youtube_router")

router = APIRouter(prefix="/oauth/youtube", tags=["YouTube OAuth"])

# Scopes needed for uploading videos + reading channel info + analytics
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def _check_google_configured() -> None:
    """Raise 503 if Google OAuth credentials are not set."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )


# ── GET /oauth/youtube/authorize ─────────────────────────────────────

@router.get("/authorize", response_model=YouTubeAuthURLResponse)
@limiter.limit("10/minute")
async def authorize(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> YouTubeAuthURLResponse:
    """Generate a Google OAuth2 consent URL.

    The frontend redirects the user to this URL.  After consent Google
    redirects back to ``google_redirect_uri`` with a ``code`` param.
    """
    _check_google_configured()
    settings = get_settings()

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",       # get a refresh_token
        "prompt": "consent",            # always show consent to ensure refresh_token
        "state": current_user.id,       # passed through to callback
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    logger.info("Generated Google OAuth URL for user %s", current_user.email)
    return YouTubeAuthURLResponse(auth_url=auth_url)


# ── POST /oauth/youtube/callback ─────────────────────────────────────

@router.post("/callback", response_model=YouTubeConnectionResponse)
@limiter.limit("10/minute")
async def callback(
    request: Request,
    body: YouTubeCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YouTubeConnectionResponse:
    """Exchange the authorization code for tokens and store them.

    The frontend sends the ``code`` (and optional ``state``) after
    Google redirects back.
    """
    _check_google_configured()
    settings = get_settings()

    # ── Step 1: Exchange code for tokens ─────────────────────────────
    token_payload = {
        "code": body.code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_resp.status_code != 200:
        logger.error("Google token exchange failed: %s", token_resp.text)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange authorization code: {token_resp.json().get('error_description', 'unknown error')}",
        )

    token_data = token_resp.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=expires_in)
    scopes = token_data.get("scope", "")

    # ── Step 2: Fetch Google user info ───────────────────────────────
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    provider_email = None
    provider_account_id = None
    if userinfo_resp.status_code == 200:
        userinfo = userinfo_resp.json()
        provider_email = userinfo.get("email")
        provider_account_id = userinfo.get("id")

    # ── Step 3: Fetch YouTube channel info ───────────────────────────
    channel_title = None
    channel_id = None
    async with httpx.AsyncClient() as client:
        yt_resp = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if yt_resp.status_code == 200:
        items = yt_resp.json().get("items", [])
        if items:
            channel_id = items[0]["id"]
            channel_title = items[0]["snippet"]["title"]

    # ── Step 4: Upsert OAuthToken in DB ──────────────────────────────
    # Encrypt tokens at rest — decrypt() handles legacy plaintext gracefully
    encrypted_access = encrypt(access_token)
    encrypted_refresh = encrypt(refresh_token) if refresh_token else None

    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = encrypted_access
        if encrypted_refresh:
            existing.refresh_token = encrypted_refresh
        existing.expires_at = expires_at
        existing.scopes = scopes
        existing.provider_email = provider_email
        existing.provider_account_id = provider_account_id
        existing.channel_title = channel_title
        existing.channel_id = channel_id
        db.add(existing)
        logger.info("Updated OAuth token for user %s (channel: %s)", current_user.email, channel_title)
    else:
        oauth_token = OAuthToken(
            user_id=current_user.id,
            provider="google",
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            expires_at=expires_at,
            scopes=scopes,
            provider_email=provider_email,
            provider_account_id=provider_account_id,
            channel_title=channel_title,
            channel_id=channel_id,
        )
        db.add(oauth_token)
        logger.info("Stored new OAuth token for user %s (channel: %s)", current_user.email, channel_title)

    await db.flush()

    return YouTubeConnectionResponse(
        connected=True,
        provider_email=provider_email,
        channel_title=channel_title,
        channel_id=channel_id,
        scopes=scopes,
        connected_at=datetime.now(timezone.utc),
    )


# ── GET /oauth/youtube/status ────────────────────────────────────────

@router.get("/status", response_model=YouTubeConnectionResponse)
async def connection_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YouTubeConnectionResponse:
    """Check whether the current user has a connected YouTube account."""
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    token = result.scalar_one_or_none()

    if not token:
        return YouTubeConnectionResponse(connected=False)

    return YouTubeConnectionResponse(
        connected=True,
        provider_email=token.provider_email,
        channel_title=token.channel_title,
        channel_id=token.channel_id,
        scopes=token.scopes,
        connected_at=token.created_at,
    )


# ── DELETE /oauth/youtube/disconnect ─────────────────────────────────

@router.delete("/disconnect", response_model=MessageResponse)
@limiter.limit("5/minute")
async def disconnect(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke the stored Google token and delete the DB record."""
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == current_user.id,
            OAuthToken.provider == "google",
        )
    )
    token = result.scalar_one_or_none()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No YouTube connection found.",
        )

    # Best-effort revoke at Google
    try:
        async with httpx.AsyncClient() as client:
            revoke_token = decrypt(token.refresh_token or "") or decrypt(token.access_token or "")
            await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": revoke_token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        logger.info("Revoked Google token for user %s", current_user.email)
    except Exception as exc:
        logger.warning("Failed to revoke Google token for user %s: %s", current_user.email, exc)

    await db.delete(token)
    await db.flush()

    logger.info("Disconnected YouTube for user %s", current_user.email)
    return MessageResponse(message="YouTube channel disconnected successfully.")
