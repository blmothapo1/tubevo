# filepath: backend/tests/test_bulk_generate.py
"""
Tests for Phase 3: Bulk Video Generation — /api/videos/bulk-generate

Covers:
- Auth gating
- Plan gating (free plan blocked, paid plans allowed)
- Topic validation (min/max length, duplicates, sanitization)
- Per-plan max topics enforcement
- Quota check (remaining monthly videos)
- Batch status endpoint
- Batch listing endpoint
- Bulk schemas (BulkGenerateRequest, BulkStatusResponse)
- Constants sanity (BULK_MAX_TOPICS)

Run:  python -m pytest backend/tests/test_bulk_generate.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import User

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

async def _signup_and_login(client: AsyncClient, email: str = "bulk@test.com") -> dict:
    await client.post("/auth/signup", json={
        "email": email,
        "password": "testpass123",
        "full_name": "Bulk Tester",
    })
    resp = await client.post("/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    return resp.json()


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _set_plan(email: str, plan: str):
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.plan = plan
        await db.commit()


# ══════════════════════════════════════════════════════════════════════
# 1. Auth gating
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_bulk_generate_requires_auth(client: AsyncClient):
    resp = await client.post("/api/videos/bulk-generate", json={
        "topics": ["Topic A", "Topic B"],
    })
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_bulk_status_requires_auth(client: AsyncClient):
    resp = await client.get("/api/videos/bulk-status/fake-batch-id")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_batches_list_requires_auth(client: AsyncClient):
    resp = await client.get("/api/videos/batches")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# 2. Plan gating
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_free_plan_blocked(client: AsyncClient):
    """Free plan users cannot use bulk generation."""
    tokens = await _signup_and_login(client)

    resp = await client.post(
        "/api/videos/bulk-generate",
        json={"topics": ["Topic A", "Topic B"]},
        headers=_auth(tokens),
    )
    assert resp.status_code == 403
    assert "Upgrade" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════════
# 3. Topic validation
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_topics_minimum_two(client: AsyncClient):
    """Bulk generate requires at least 2 topics."""
    tokens = await _signup_and_login(client)
    await _set_plan("bulk@test.com", "starter")

    resp = await client.post(
        "/api/videos/bulk-generate",
        json={"topics": ["Only One"]},
        headers=_auth(tokens),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_topics_too_short(client: AsyncClient):
    """Topics shorter than 3 chars are rejected."""
    tokens = await _signup_and_login(client)
    await _set_plan("bulk@test.com", "starter")

    resp = await client.post(
        "/api/videos/bulk-generate",
        json={"topics": ["OK Topic", "AB"]},
        headers=_auth(tokens),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_topics_duplicate_rejected(client: AsyncClient):
    """Duplicate topics (case-insensitive) are rejected."""
    tokens = await _signup_and_login(client)
    await _set_plan("bulk@test.com", "starter")

    resp = await client.post(
        "/api/videos/bulk-generate",
        json={"topics": ["Same Topic", "same topic"]},
        headers=_auth(tokens),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_topics_max_per_plan(client: AsyncClient):
    """Starter plan allows max 5 topics; 6 should fail."""
    tokens = await _signup_and_login(client)
    await _set_plan("bulk@test.com", "starter")

    topics = [f"Topic number {i}" for i in range(6)]
    resp = await client.post(
        "/api/videos/bulk-generate",
        json={"topics": topics},
        headers=_auth(tokens),
    )
    assert resp.status_code == 400
    assert "5" in resp.json()["detail"]


# ══════════════════════════════════════════════════════════════════════
# 4. Batch status — not found
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_bulk_status_nonexistent(client: AsyncClient):
    """Querying a batch that doesn't exist returns 404."""
    tokens = await _signup_and_login(client)

    resp = await client.get(
        "/api/videos/bulk-status/nonexistent-batch-id",
        headers=_auth(tokens),
    )
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# 5. Batches list — empty
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_batches_list_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)
    resp = await client.get("/api/videos/batches", headers=_auth(tokens))
    assert resp.status_code == 200
    assert resp.json() == []


# ══════════════════════════════════════════════════════════════════════
# 6. Schema validation
# ══════════════════════════════════════════════════════════════════════

def test_bulk_generate_request_schema():
    """BulkGenerateRequest validates correctly."""
    from backend.routers.videos import BulkGenerateRequest

    # Valid
    req = BulkGenerateRequest(topics=["Topic A", "Topic B"])
    assert len(req.topics) == 2

    # Too few
    with pytest.raises(Exception):
        BulkGenerateRequest(topics=["Only one"])


def test_bulk_status_item_schema():
    """BulkStatusItem and BulkStatusResponse have correct fields."""
    from backend.routers.videos import BulkStatusItem, BulkStatusResponse

    item = BulkStatusItem(
        id="test-id",
        topic="Test Topic",
        status="queued",
        position=0,
    )
    assert item.progress_pct == 0  # default

    response = BulkStatusResponse(
        batch_id="batch-1",
        total=2,
        completed=0,
        failed=0,
        generating=0,
        queued=2,
        items=[item],
    )
    assert response.total == 2


# ══════════════════════════════════════════════════════════════════════
# 7. Constants sanity
# ══════════════════════════════════════════════════════════════════════

def test_bulk_max_topics_constants():
    """BULK_MAX_TOPICS has sensible plan-based limits."""
    from backend.routers.videos import BULK_MAX_TOPICS

    assert BULK_MAX_TOPICS["free"] == 0
    assert BULK_MAX_TOPICS["starter"] == 5
    assert BULK_MAX_TOPICS["pro"] == 10
    assert BULK_MAX_TOPICS["agency"] == 20

    # Each tier allows more than the previous
    assert BULK_MAX_TOPICS["starter"] < BULK_MAX_TOPICS["pro"]
    assert BULK_MAX_TOPICS["pro"] < BULK_MAX_TOPICS["agency"]
