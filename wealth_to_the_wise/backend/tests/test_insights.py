# filepath: backend/tests/test_insights.py
"""
Tests for Phase 2: Performance Insights Dashboard — /api/insights/*

Covers:
- Auth gating (all endpoints require authentication)
- Overview stats (hero cards — views, engagement, etc.)
- Timeline data (empty returns valid structure)
- Top videos (empty and with data)
- Style analysis (empty returns valid structure)
- Recommendations (low data points → encouragement message)
- Query parameter validation (days range)

Run:  python -m pytest backend/tests/test_insights.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import User, VideoRecord, ContentPerformance

from sqlalchemy import select
from datetime import datetime, timezone


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

async def _signup_and_login(client: AsyncClient, email: str = "analyst@test.com") -> dict:
    await client.post("/auth/signup", json={
        "email": email,
        "password": "testpass123",
        "full_name": "Test Analyst",
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


async def _seed_video_with_perf(user_id: str, topic: str = "Test Topic", **perf_overrides):
    """Create a VideoRecord + ContentPerformance for testing."""
    async with async_session_factory() as db:
        video = VideoRecord(
            user_id=user_id,
            topic=topic,
            title=f"Test: {topic}",
            status="posted",
        )
        db.add(video)
        await db.flush()

        perf_defaults = {
            "user_id": user_id,
            "video_record_id": video.id,
            "views_48h": 1000,
            "likes_48h": 50,
            "comments_48h": 10,
            "engagement_score": 72,
            "metrics_fetched_at": datetime.now(timezone.utc),
        }
        perf_defaults.update(perf_overrides)

        perf = ContentPerformance(**perf_defaults)
        db.add(perf)
        await db.commit()
        return video.id


# ══════════════════════════════════════════════════════════════════════
# 1. Auth gating
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_overview_requires_auth(client: AsyncClient):
    resp = await client.get("/api/insights/overview")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_timeline_requires_auth(client: AsyncClient):
    resp = await client.get("/api/insights/timeline")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_top_videos_requires_auth(client: AsyncClient):
    resp = await client.get("/api/insights/top-videos")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_style_analysis_requires_auth(client: AsyncClient):
    resp = await client.get("/api/insights/style-analysis")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_recommendations_requires_auth(client: AsyncClient):
    resp = await client.get("/api/insights/recommendations")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# 2. Overview — empty state
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_overview_empty(client: AsyncClient):
    """Overview returns zeros for a fresh user."""
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/insights/overview", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_videos"] == 0
    assert data["posted_videos"] == 0
    assert data["total_views"] == 0
    assert data["avg_engagement_score"] == 0.0
    assert data["videos_with_metrics"] == 0


# ══════════════════════════════════════════════════════════════════════
# 3. Overview — with data
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_overview_with_data(client: AsyncClient):
    """Overview aggregates correctly with seeded data."""
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("analyst@test.com")

    await _seed_video_with_perf(user_id, "Investing 101", views_48h=2000, likes_48h=100, comments_48h=20, engagement_score=85)
    await _seed_video_with_perf(user_id, "Crypto Basics", views_48h=1500, likes_48h=80, comments_48h=15, engagement_score=70)

    resp = await client.get("/api/insights/overview", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_videos"] == 2
    assert data["total_views"] == 3500
    assert data["total_likes"] == 180
    assert data["total_comments"] == 35
    assert data["best_engagement_score"] == 85
    assert data["videos_with_metrics"] == 2
    # Avg engagement: (85 + 70) / 2 = 77.5
    assert 77.0 <= data["avg_engagement_score"] <= 78.0


# ══════════════════════════════════════════════════════════════════════
# 4. Timeline
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_timeline_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/insights/timeline?days=7", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline" in data
    assert data["days"] == 7
    # Should have 7-8 days of entries (today + 7 lookback)
    assert len(data["timeline"]) >= 7


@pytest.mark.anyio
async def test_timeline_days_validation(client: AsyncClient):
    """Days must be between 7 and 365."""
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/insights/timeline?days=3", headers=_auth(tokens))
    assert resp.status_code == 422

    resp = await client.get("/api/insights/timeline?days=500", headers=_auth(tokens))
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════
# 5. Top videos
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_top_videos_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/insights/top-videos", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["videos"] == []
    assert data["total"] == 0


@pytest.mark.anyio
async def test_top_videos_ordered_by_engagement(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("analyst@test.com")

    await _seed_video_with_perf(user_id, "Low Score", engagement_score=30, views_48h=500)
    await _seed_video_with_perf(user_id, "High Score", engagement_score=95, views_48h=5000)
    await _seed_video_with_perf(user_id, "Mid Score", engagement_score=60, views_48h=2000)

    resp = await client.get("/api/insights/top-videos", headers=_auth(tokens))
    assert resp.status_code == 200
    videos = resp.json()["videos"]
    assert len(videos) == 3
    # Should be ordered by engagement descending
    assert videos[0]["engagement_score"] == 95
    assert videos[1]["engagement_score"] == 60
    assert videos[2]["engagement_score"] == 30


# ══════════════════════════════════════════════════════════════════════
# 6. Style analysis
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_style_analysis_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/insights/style-analysis", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["title_styles"] == []
    assert data["thumbnail_styles"] == []
    assert data["hook_modes"] == []


@pytest.mark.anyio
async def test_style_analysis_with_data(client: AsyncClient):
    tokens = await _signup_and_login(client)
    user_id = await _get_user_id("analyst@test.com")

    await _seed_video_with_perf(
        user_id, "Vid 1",
        title_style_used="curiosity_gap",
        thumbnail_concept_used="bold_text",
        hook_mode_used="high",
        engagement_score=80,
    )
    await _seed_video_with_perf(
        user_id, "Vid 2",
        title_style_used="curiosity_gap",
        thumbnail_concept_used="clean_authority",
        hook_mode_used="low",
        engagement_score=50,
    )

    resp = await client.get("/api/insights/style-analysis", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["title_styles"]) >= 1
    assert len(data["thumbnail_styles"]) >= 1
    assert len(data["hook_modes"]) >= 1


# ══════════════════════════════════════════════════════════════════════
# 7. Recommendations
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_recommendations_low_data(client: AsyncClient):
    """With fewer than MIN_DATA_POINTS, system encourages more content."""
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/insights/recommendations", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_points"] == 0
    assert len(data["recommendations"]) >= 1
    assert data["recommendations"][0]["category"] == "general"
    assert "keep" in data["recommendations"][0]["label"].lower()


# ══════════════════════════════════════════════════════════════════════
# 8. Data isolation — users can't see each other's insights
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_data_isolation(client: AsyncClient):
    """User A's insights don't leak into User B's."""
    tokens_a = await _signup_and_login(client, email="userA@test.com")
    user_a_id = await _get_user_id("userA@test.com")

    tokens_b = await _signup_and_login(client, email="userB@test.com")

    # Seed data for user A
    await _seed_video_with_perf(user_a_id, "A's Video", views_48h=10000, engagement_score=99)

    # User B should see empty
    resp = await client.get("/api/insights/overview", headers=_auth(tokens_b))
    assert resp.status_code == 200
    assert resp.json()["total_views"] == 0

    # User A should see data
    resp = await client.get("/api/insights/overview", headers=_auth(tokens_a))
    assert resp.status_code == 200
    assert resp.json()["total_views"] == 10000
