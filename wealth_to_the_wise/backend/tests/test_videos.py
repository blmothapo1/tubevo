# filepath: backend/tests/test_videos.py
"""
Tests for the video pipeline API router.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine


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
    import uuid
    unique = uuid.uuid4().hex[:8]
    await client.post("/auth/signup", json={
        "email": f"video-{unique}@test.com",
        "password": "testpass123",
        "full_name": "Video Test",
    })
    resp = await client.post("/auth/login", json={
        "email": f"video-{unique}@test.com",
        "password": "testpass123",
    })
    return resp.json()


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_generate_requires_auth(client: AsyncClient):
    """Generate endpoint requires authentication."""
    resp = await client.post("/api/videos/generate", json={"topic": "test"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_generate_validates_topic(client: AsyncClient):
    """Topic must be at least 3 characters."""
    tokens = await _signup_and_login(client)
    resp = await client.post(
        "/api/videos/generate",
        json={"topic": "ab"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_history_requires_auth(client: AsyncClient):
    """History endpoint requires authentication."""
    resp = await client.get("/api/videos/history")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_history_returns_list(client: AsyncClient):
    """History endpoint returns a list (empty when no videos generated)."""
    tokens = await _signup_and_login(client)
    resp = await client.get(
        "/api/videos/history",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
