# filepath: backend/tests/test_youtube.py
"""
Tests for the YouTube / Google OAuth router — /oauth/youtube/*
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import OAuthToken


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Fresh app + DB for every test."""
    app = create_app()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _signup_and_login(client: AsyncClient) -> dict:
    """Helper: create a user and return the token response."""
    unique = uuid.uuid4().hex[:8]
    email = f"yt-{unique}@test.com"
    await client.post("/auth/signup", json={
        "email": email,
        "password": "testpass123",
        "full_name": "YouTube Test",
    })
    resp = await client.post("/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    data = resp.json()
    data["email"] = email
    return data


def _auth_header(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── Test: authorize endpoint ─────────────────────────────────────────

@pytest.mark.anyio
async def test_authorize_returns_google_url(client: AsyncClient):
    """GET /oauth/youtube/authorize returns a Google consent URL when configured."""
    tokens = await _signup_and_login(client)

    with patch("backend.routers.youtube.get_settings") as mock_settings:
        settings = MagicMock()
        settings.google_client_id = "fake-client-id"
        settings.google_client_secret = "fake-secret"
        settings.google_redirect_uri = "http://localhost:3000/auth/google/callback"
        mock_settings.return_value = settings

        resp = await client.get("/oauth/youtube/authorize", headers=_auth_header(tokens))

    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]
    assert "fake-client-id" in data["auth_url"]
    assert "youtube.upload" in data["auth_url"]


@pytest.mark.anyio
async def test_authorize_503_when_not_configured(client: AsyncClient):
    """GET /oauth/youtube/authorize returns 503 when Google creds missing."""
    tokens = await _signup_and_login(client)

    with patch("backend.routers.youtube.get_settings") as mock_settings:
        settings = MagicMock()
        settings.google_client_id = ""
        settings.google_client_secret = ""
        mock_settings.return_value = settings

        resp = await client.get("/oauth/youtube/authorize", headers=_auth_header(tokens))

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_authorize_401_without_auth(client: AsyncClient):
    """GET /oauth/youtube/authorize returns 401 without a token."""
    resp = await client.get("/oauth/youtube/authorize")
    assert resp.status_code == 401


# ── Test: status endpoint ────────────────────────────────────────────

@pytest.mark.anyio
async def test_status_not_connected(client: AsyncClient):
    """GET /oauth/youtube/status returns connected=false when no token."""
    tokens = await _signup_and_login(client)
    resp = await client.get("/oauth/youtube/status", headers=_auth_header(tokens))

    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.anyio
async def test_status_connected(client: AsyncClient):
    """GET /oauth/youtube/status returns connection details when token exists."""
    tokens = await _signup_and_login(client)

    # Decode the JWT to get user_id
    from backend.auth import decode_token
    payload = decode_token(tokens["access_token"])
    user_id = payload["sub"]

    # Insert a token record directly in the DB
    async with async_session_factory() as session:
        oauth = OAuthToken(
            user_id=user_id,
            provider="google",
            access_token="fake-access",
            refresh_token="fake-refresh",
            provider_email="yt@example.com",
            channel_title="My Channel",
            channel_id="UC12345",
        )
        session.add(oauth)
        await session.commit()

    resp = await client.get("/oauth/youtube/status", headers=_auth_header(tokens))

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["channel_title"] == "My Channel"
    assert data["channel_id"] == "UC12345"
    assert data["provider_email"] == "yt@example.com"


# ── Test: disconnect endpoint ────────────────────────────────────────

@pytest.mark.anyio
async def test_disconnect_removes_token(client: AsyncClient):
    """DELETE /oauth/youtube/disconnect removes the stored token."""
    tokens = await _signup_and_login(client)

    from backend.auth import decode_token
    payload = decode_token(tokens["access_token"])
    user_id = payload["sub"]

    async with async_session_factory() as session:
        oauth = OAuthToken(
            user_id=user_id,
            provider="google",
            access_token="fake-access",
            refresh_token="fake-refresh",
        )
        session.add(oauth)
        await session.commit()

    resp = await client.delete("/oauth/youtube/disconnect", headers=_auth_header(tokens))
    assert resp.status_code == 200
    assert "disconnected" in resp.json()["message"].lower()

    # Verify token is gone
    resp = await client.get("/oauth/youtube/status", headers=_auth_header(tokens))
    assert resp.json()["connected"] is False


@pytest.mark.anyio
async def test_disconnect_404_when_not_connected(client: AsyncClient):
    """DELETE /oauth/youtube/disconnect returns 404 when no connection."""
    tokens = await _signup_and_login(client)
    resp = await client.delete("/oauth/youtube/disconnect", headers=_auth_header(tokens))
    assert resp.status_code == 404


# ── Test: callback endpoint ──────────────────────────────────────────

@pytest.mark.anyio
async def test_callback_exchanges_code_and_stores_token(client: AsyncClient):
    """POST /oauth/youtube/callback exchanges the code and stores token."""
    tokens = await _signup_and_login(client)

    from backend.auth import decode_token
    payload = decode_token(tokens["access_token"])
    user_id = payload["sub"]

    # Mock httpx responses for Google token exchange, userinfo, and YT channel
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "ya29.fake-access-token",
        "refresh_token": "1//fake-refresh-token",
        "expires_in": 3600,
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "token_type": "Bearer",
    }

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "id": "google-user-123",
        "email": "yt@example.com",
    }

    mock_yt_resp = MagicMock()
    mock_yt_resp.status_code = 200
    mock_yt_resp.json.return_value = {
        "items": [
            {
                "id": "UCxxxx",
                "snippet": {"title": "My Awesome Channel"},
            }
        ]
    }

    async def mock_post(url, **kwargs):
        if "oauth2.googleapis.com/token" in url:
            return mock_token_resp
        return MagicMock(status_code=200, json=MagicMock(return_value={}))

    async def mock_get(url, **kwargs):
        if "userinfo" in url:
            return mock_userinfo_resp
        if "youtube" in url:
            return mock_yt_resp
        return MagicMock(status_code=200, json=MagicMock(return_value={}))

    mock_http_client = AsyncMock()
    mock_http_client.post = mock_post
    mock_http_client.get = mock_get

    with patch("backend.routers.youtube.get_settings") as mock_settings:
        settings = MagicMock()
        settings.google_client_id = "fake-client-id"
        settings.google_client_secret = "fake-secret"
        settings.google_redirect_uri = "http://localhost:3000/auth/google/callback"
        mock_settings.return_value = settings

        with patch("backend.routers.youtube.httpx.AsyncClient") as MockAsyncClient:
            MockAsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            MockAsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await client.post(
                "/oauth/youtube/callback",
                json={"code": "fake-auth-code", "state": user_id},
                headers=_auth_header(tokens),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["channel_title"] == "My Awesome Channel"
    assert data["channel_id"] == "UCxxxx"
    assert data["provider_email"] == "yt@example.com"

    # Verify it's persisted — status endpoint should show connected
    resp = await client.get("/oauth/youtube/status", headers=_auth_header(tokens))
    assert resp.json()["connected"] is True
    assert resp.json()["channel_id"] == "UCxxxx"
