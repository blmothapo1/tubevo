# filepath: backend/tests/test_video_preview.py
"""
Tests for the video preview & publish feature.

Covers:
- Preview data endpoint (GET /{video_id}/preview-data)
- Preview video streaming (GET /{video_id}/preview)
- Preview thumbnail serving (GET /{video_id}/preview-thumbnail)
- Publish to YouTube (POST /{video_id}/publish)
- Auth gating on all preview/publish endpoints
- Status validation for publish
- Token-based query param auth for media endpoints
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import VideoRecord


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
    """Helper: create a user and return tokens."""
    unique = uuid.uuid4().hex[:8]
    await client.post("/auth/signup", json={
        "email": f"preview-{unique}@test.com",
        "password": "testpass123",
        "full_name": "Preview Test",
    })
    resp = await client.post("/auth/login", json={
        "email": f"preview-{unique}@test.com",
        "password": "testpass123",
    })
    return resp.json()


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _create_video_record(user_id: str, **overrides) -> str:
    """Insert a VideoRecord directly and return its ID."""
    import json
    video_id = uuid.uuid4().hex[:16]
    async with async_session_factory() as db:
        record = VideoRecord(
            id=video_id,
            user_id=user_id,
            topic=overrides.get("topic", "Test Topic"),
            title=overrides.get("title", "Test Title"),
            status=overrides.get("status", "completed"),
            file_path=overrides.get("file_path"),
            thumbnail_path=overrides.get("thumbnail_path"),
            metadata_json=overrides.get("metadata_json", json.dumps({
                "title": "Test Title",
                "description": "A test description.",
                "tags": ["finance", "wealth", "investing"],
            })),
        )
        db.add(record)
        await db.commit()
    return video_id


def _get_user_id_from_tokens(tokens: dict) -> str:
    """Extract user_id from the JWT access token."""
    from backend.auth import decode_token
    payload = decode_token(tokens["access_token"])
    return payload["sub"]


# ══════════════════════════════════════════════════════════════════════
# Auth gating
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_preview_data_requires_auth(client: AsyncClient):
    resp = await client.get("/api/videos/fake-id/preview-data")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_preview_video_requires_auth(client: AsyncClient):
    resp = await client.get("/api/videos/fake-id/preview")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_preview_thumbnail_requires_auth(client: AsyncClient):
    resp = await client.get("/api/videos/fake-id/preview-thumbnail")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_publish_requires_auth(client: AsyncClient):
    resp = await client.post("/api/videos/fake-id/publish")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# Preview Data endpoint
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_preview_data_returns_video_info(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    video_id = await _create_video_record(user_id, status="completed")

    resp = await client.get(f"/api/videos/{video_id}/preview-data", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == video_id
    assert data["title"] == "Test Title"
    assert data["status"] == "completed"
    assert data["description"] == "A test description."
    assert "finance" in data["tags"]
    assert data["has_youtube"] is False  # No OAuth connected


@pytest.mark.anyio
async def test_preview_data_404_wrong_user(client: AsyncClient):
    """User A can't preview User B's video."""
    tokens_a = await _signup_and_login(client)
    tokens_b = await _signup_and_login(client)
    user_a_id = _get_user_id_from_tokens(tokens_a)

    video_id = await _create_video_record(user_a_id, status="completed")

    resp = await client.get(f"/api/videos/{video_id}/preview-data", headers=_auth(tokens_b))
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_preview_data_404_missing(client: AsyncClient):
    tokens = await _signup_and_login(client)
    resp = await client.get("/api/videos/nonexistent/preview-data", headers=_auth(tokens))
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# Preview Video streaming
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_preview_video_streams_file(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    # Create a temp file to simulate a built video
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake-mp4-content-for-testing")
        temp_path = f.name

    try:
        video_id = await _create_video_record(user_id, status="completed", file_path=temp_path)

        resp = await client.get(f"/api/videos/{video_id}/preview", headers=_auth(tokens))
        assert resp.status_code == 200
        assert "video/mp4" in resp.headers.get("content-type", "")
    finally:
        os.unlink(temp_path)


@pytest.mark.anyio
async def test_preview_video_token_query_param(client: AsyncClient):
    """<video> elements can auth via ?token= query param."""
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake-mp4-content")
        temp_path = f.name

    try:
        video_id = await _create_video_record(user_id, status="completed", file_path=temp_path)

        # No auth header — use query param instead
        resp = await client.get(
            f"/api/videos/{video_id}/preview?token={tokens['access_token']}"
        )
        assert resp.status_code == 200
        assert "video/mp4" in resp.headers.get("content-type", "")
    finally:
        os.unlink(temp_path)


@pytest.mark.anyio
async def test_preview_video_no_file_404(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    video_id = await _create_video_record(user_id, status="completed", file_path="/nonexistent.mp4")

    resp = await client.get(f"/api/videos/{video_id}/preview", headers=_auth(tokens))
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# Preview Thumbnail
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_preview_thumbnail_serves_image(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff\xe0fake-jpeg-header")
        temp_path = f.name

    try:
        video_id = await _create_video_record(user_id, status="completed", thumbnail_path=temp_path)

        resp = await client.get(f"/api/videos/{video_id}/preview-thumbnail", headers=_auth(tokens))
        assert resp.status_code == 200
        assert "image/jpeg" in resp.headers.get("content-type", "")
    finally:
        os.unlink(temp_path)


@pytest.mark.anyio
async def test_preview_thumbnail_token_query_param(client: AsyncClient):
    """<img> elements can auth via ?token= query param."""
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"\x89PNGfake-png-header")
        temp_path = f.name

    try:
        video_id = await _create_video_record(user_id, status="completed", thumbnail_path=temp_path)

        resp = await client.get(
            f"/api/videos/{video_id}/preview-thumbnail?token={tokens['access_token']}"
        )
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")
    finally:
        os.unlink(temp_path)


@pytest.mark.anyio
async def test_preview_thumbnail_no_file_404(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    video_id = await _create_video_record(user_id, status="completed")  # no thumbnail_path

    resp = await client.get(f"/api/videos/{video_id}/preview-thumbnail", headers=_auth(tokens))
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# Publish endpoint
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_publish_requires_completed_status(client: AsyncClient):
    """Can't publish a pending/generating/failed video."""
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    for bad_status in ("pending", "generating", "failed"):
        video_id = await _create_video_record(user_id, status=bad_status)
        resp = await client.post(f"/api/videos/{video_id}/publish", headers=_auth(tokens))
        assert resp.status_code == 400, f"Expected 400 for status={bad_status}, got {resp.status_code}"


@pytest.mark.anyio
async def test_publish_already_posted_409(client: AsyncClient):
    """Publishing an already-posted video returns 409."""
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    video_id = await _create_video_record(user_id, status="posted")
    resp = await client.post(f"/api/videos/{video_id}/publish", headers=_auth(tokens))
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_publish_no_youtube_connected(client: AsyncClient):
    """Publishing without a YouTube channel returns 400."""
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake-video-content")
        temp_path = f.name

    try:
        video_id = await _create_video_record(user_id, status="completed", file_path=temp_path)
        resp = await client.post(f"/api/videos/{video_id}/publish", headers=_auth(tokens))
        assert resp.status_code == 400
        assert "YouTube" in resp.json()["detail"] or "channel" in resp.json()["detail"].lower()
    finally:
        os.unlink(temp_path)


@pytest.mark.anyio
async def test_publish_no_file_404(client: AsyncClient):
    """Publishing a video whose file is missing returns 404."""
    tokens = await _signup_and_login(client)
    user_id = _get_user_id_from_tokens(tokens)

    video_id = await _create_video_record(user_id, status="completed", file_path="/nonexistent.mp4")
    resp = await client.post(f"/api/videos/{video_id}/publish", headers=_auth(tokens))
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_publish_wrong_user_404(client: AsyncClient):
    """User B can't publish User A's video."""
    tokens_a = await _signup_and_login(client)
    tokens_b = await _signup_and_login(client)
    user_a_id = _get_user_id_from_tokens(tokens_a)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake-video-content")
        temp_path = f.name

    try:
        video_id = await _create_video_record(user_a_id, status="completed", file_path=temp_path)
        resp = await client.post(f"/api/videos/{video_id}/publish", headers=_auth(tokens_b))
        assert resp.status_code == 404
    finally:
        os.unlink(temp_path)
