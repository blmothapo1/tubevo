# filepath: backend/tests/test_export_formats.py
"""
Tests for Phase 1: Multi-Format Export — /api/videos/formats, /reformat, /download

Covers:
- List available formats endpoint
- ReformatRequest schema validation
- Download format validation
- Auth gating on reformat / download endpoints
- Video not found handling
- Format-specific download routing (landscape vs portrait vs square)

Run:  python -m pytest backend/tests/test_export_formats.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import User, VideoRecord

from sqlalchemy import select


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


# ── Helpers ──────────────────────────────────────────────────────────

async def _signup_and_login(client: AsyncClient, email: str = "export@test.com") -> dict:
    await client.post("/auth/signup", json={
        "email": email,
        "password": "testpass123",
        "full_name": "Export Tester",
    })
    resp = await client.post("/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    return resp.json()


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _get_user_id(email: str) -> str:
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one().id


async def _create_video_record(user_id: str, status: str = "completed") -> str:
    """Create a VideoRecord and return its ID."""
    async with async_session_factory() as db:
        record = VideoRecord(
            user_id=user_id,
            topic="Test Export Topic",
            title="Test Export Video",
            status=status,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


# ══════════════════════════════════════════════════════════════════════
# 1. List formats (public-ish endpoint)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_formats(client: AsyncClient):
    """GET /api/videos/formats returns available format presets."""
    resp = await client.get("/api/videos/formats")
    assert resp.status_code == 200
    data = resp.json()
    assert "formats" in data
    formats = data["formats"]
    assert len(formats) >= 3  # landscape, portrait, square

    # Verify keys exist
    keys = [f["key"] for f in formats]
    assert "landscape" in keys
    assert "portrait" in keys
    assert "square" in keys


@pytest.mark.anyio
async def test_format_presets_have_dimensions(client: AsyncClient):
    """Each format preset should have width, height, and aspect."""
    resp = await client.get("/api/videos/formats")
    for fmt in resp.json()["formats"]:
        assert "width" in fmt
        assert "height" in fmt
        assert "aspect" in fmt
        assert fmt["width"] > 0
        assert fmt["height"] > 0


# ══════════════════════════════════════════════════════════════════════
# 2. ReformatRequest schema validation
# ══════════════════════════════════════════════════════════════════════

def test_reformat_request_valid():
    """ReformatRequest accepts 'portrait' and 'square'."""
    from backend.routers.videos import ReformatRequest

    req = ReformatRequest(target_format="portrait")
    assert req.target_format == "portrait"

    req = ReformatRequest(target_format="square")
    assert req.target_format == "square"


def test_reformat_request_invalid_format():
    """ReformatRequest rejects invalid formats."""
    from backend.routers.videos import ReformatRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReformatRequest(target_format="landscape")

    with pytest.raises(ValidationError):
        ReformatRequest(target_format="tiktok")


# ══════════════════════════════════════════════════════════════════════
# 3. Auth gating
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reformat_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/videos/fake-id/reformat",
        json={"target_format": "portrait"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_download_format_requires_auth(client: AsyncClient):
    resp = await client.get("/api/videos/fake-id/download/portrait")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# 4. Video not found
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reformat_video_not_found(client: AsyncClient):
    tokens = await _signup_and_login(client)

    resp = await client.post(
        "/api/videos/nonexistent-id/reformat",
        json={"target_format": "portrait"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_download_video_not_found(client: AsyncClient):
    tokens = await _signup_and_login(client)

    resp = await client.get(
        "/api/videos/nonexistent-id/download/portrait",
        headers=_auth(tokens),
    )
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# 5. Reformat — video not in completed/posted state
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reformat_video_not_completed(client: AsyncClient):
    """Can only reformat completed or posted videos."""
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("export@test.com")

    video_id = await _create_video_record(user_id, status="generating")

    resp = await client.post(
        f"/api/videos/{video_id}/reformat",
        json={"target_format": "portrait"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 400
    assert "completed" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════
# 6. Download — invalid format
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_download_invalid_format(client: AsyncClient):
    """Downloading with an invalid format returns 400."""
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("export@test.com")

    video_id = await _create_video_record(user_id)

    resp = await client.get(
        f"/api/videos/{video_id}/download/invalid_format",
        headers=_auth(tokens),
    )
    assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════
# 7. Download — portrait/square not yet generated
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_download_portrait_not_generated(client: AsyncClient):
    """Portrait download returns 404 if not yet reformatted."""
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("export@test.com")

    video_id = await _create_video_record(user_id)

    resp = await client.get(
        f"/api/videos/{video_id}/download/portrait",
        headers=_auth(tokens),
    )
    assert resp.status_code == 404
    assert "Generate it first" in resp.json()["detail"]


@pytest.mark.anyio
async def test_download_square_not_generated(client: AsyncClient):
    """Square download returns 404 if not yet reformatted."""
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("export@test.com")

    video_id = await _create_video_record(user_id)

    resp = await client.get(
        f"/api/videos/{video_id}/download/square",
        headers=_auth(tokens),
    )
    assert resp.status_code == 404
    assert "Generate it first" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════════
# 8. Data isolation — can't reformat another user's video
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reformat_other_users_video(client: AsyncClient):
    """User A can't reformat User B's video."""
    tokens_a = await _signup_and_login(client, email="userA@test.com")

    # Create video for user A
    user_a_id = await _get_user_id("userA@test.com")
    video_id = await _create_video_record(user_a_id)

    # User B tries to reformat it
    tokens_b = await _signup_and_login(client, email="userB@test.com")
    resp = await client.post(
        f"/api/videos/{video_id}/reformat",
        json={"target_format": "portrait"},
        headers=_auth(tokens_b),
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_download_other_users_video(client: AsyncClient):
    """User A can't download User B's video."""
    tokens_a = await _signup_and_login(client, email="userA@test.com")
    user_a_id = await _get_user_id("userA@test.com")
    video_id = await _create_video_record(user_a_id)

    tokens_b = await _signup_and_login(client, email="userB@test.com")
    resp = await client.get(
        f"/api/videos/{video_id}/download/landscape",
        headers=_auth(tokens_b),
    )
    assert resp.status_code == 404
