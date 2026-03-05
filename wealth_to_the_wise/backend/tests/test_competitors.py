# filepath: backend/tests/test_competitors.py
"""
Tests for Empire OS Phase 5: Competitor Monitoring (Spy Mode).

Covers:
  - Competitor service (add, remove, list, get, snapshots, growth)
  - Router endpoints (list, add, get, delete, snapshots CRUD)
  - Feature flag gating
  - Schema validation
  - Worker importability
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Fresh app + DB with multi-channel and competitor spy ON."""
    with patch.dict(os.environ, {
        "FF_EMPIRE_MULTI_CHANNEL": "1",
        "FF_EMPIRE_COMPETITOR_SPY": "1",
    }):
        app = create_app()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client_flag_off():
    """Competitor spy flag OFF."""
    with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}, clear=False):
        os.environ.pop("FF_EMPIRE_COMPETITOR_SPY", None)
        app = create_app()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# ── Helpers ──────────────────────────────────────────────────────────

SIGNUP_BODY = {
    "email": "spy-test@example.com",
    "password": "strongpass123",
    "full_name": "Spy Tester",
}

COMPETITOR_BODY = {
    "youtube_channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
    "name": "Google Developers",
    "subscriber_count": 5000000,
}


async def _signup_and_login(client: AsyncClient) -> str:
    await client.post("/auth/signup", json=SIGNUP_BODY)
    resp = await client.post(
        "/auth/login",
        json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup_channel(token: str, client: AsyncClient) -> str:
    """Create a channel and return its ID."""
    resp = await client.post(
        "/channels",
        json={"name": "Spy Test Channel", "platform": "youtube"},
        headers=_auth(token),
    )
    return resp.json()["id"]


async def _add_competitor(client: AsyncClient, token: str) -> dict:
    """Add the default competitor and return the JSON."""
    resp = await client.post(
        "/competitors",
        json=COMPETITOR_BODY,
        headers=_auth(token),
    )
    return resp.json(), resp.status_code


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag gating
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_competitors_403_when_flag_off(client_flag_off: AsyncClient):
    token = await _signup_and_login(client_flag_off)
    resp = await client_flag_off.get("/competitors", headers=_auth(token))
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 2. Service unit tests
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_service_add_competitor(client: AsyncClient):
    """add_competitor creates a CompetitorChannel row."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC123test",
            name="Test Rival",
            subscriber_count=1000,
            db=db,
        )
        await db.commit()

    assert comp.youtube_channel_id == "UC123test"
    assert comp.name == "Test Rival"
    assert comp.is_active is True
    assert comp.subscriber_count == 1000


@pytest.mark.anyio
async def test_service_add_duplicate_rejects(client: AsyncClient):
    """Cannot add the same YouTube channel twice."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor

    async with async_session_factory() as db:
        await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_dup",
            name="Dup Rival",
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="Already tracking"):
            await add_competitor(
                channel_id=channel_id,
                youtube_channel_id="UC_dup",
                name="Dup Rival 2",
                db=db,
            )


@pytest.mark.anyio
async def test_service_reactivate_removed_competitor(client: AsyncClient):
    """Re-adding a previously removed competitor reactivates it."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor, remove_competitor

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_react",
            name="React Channel",
            db=db,
        )
        await db.flush()
        await remove_competitor(
            competitor_id=comp.id,
            channel_id=channel_id,
            db=db,
        )
        await db.commit()

    # Re-add
    async with async_session_factory() as db:
        reactivated = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_react",
            name="React Channel Updated",
            db=db,
        )
        await db.commit()

    assert reactivated.is_active is True
    assert reactivated.name == "React Channel Updated"


@pytest.mark.anyio
async def test_service_remove_competitor(client: AsyncClient):
    """remove_competitor sets is_active=False."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor, remove_competitor

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_rem",
            name="Remove Me",
            db=db,
        )
        await db.flush()

        removed = await remove_competitor(
            competitor_id=comp.id,
            channel_id=channel_id,
            db=db,
        )
        await db.commit()

    assert removed.is_active is False


@pytest.mark.anyio
async def test_service_remove_already_removed_rejects(client: AsyncClient):
    """Cannot remove an already-removed competitor."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor, remove_competitor

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_rr",
            name="Double Remove",
            db=db,
        )
        await db.flush()
        await remove_competitor(
            competitor_id=comp.id,
            channel_id=channel_id,
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="already removed"):
            await remove_competitor(
                competitor_id=comp.id,
                channel_id=channel_id,
                db=db,
            )


@pytest.mark.anyio
async def test_service_record_snapshot(client: AsyncClient):
    """record_snapshot stores a snapshot for a competitor."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor, record_snapshot

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_snap",
            name="Snap Channel",
            db=db,
        )
        await db.flush()

        snap = await record_snapshot(
            competitor_id=comp.id,
            snapshot_date="2026-03-04",
            subscriber_count=10000,
            total_views=500000,
            video_count=120,
            avg_views_per_video=4166,
            recent_videos=[{"title": "Latest Vid", "views": 5000}],
            top_tags=["finance", "investing"],
            db=db,
        )
        await db.commit()

    assert snap.snapshot_date == "2026-03-04"
    assert snap.subscriber_count == 10000
    assert snap.total_views == 500000
    assert snap.recent_videos_json is not None
    assert "Latest Vid" in snap.recent_videos_json


@pytest.mark.anyio
async def test_service_snapshot_upsert(client: AsyncClient):
    """Recording a snapshot for the same date updates in place."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor, record_snapshot

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_upsert",
            name="Upsert Channel",
            db=db,
        )
        await db.flush()

        snap1 = await record_snapshot(
            competitor_id=comp.id,
            snapshot_date="2026-03-04",
            subscriber_count=100,
            db=db,
        )
        snap1_id = snap1.id
        await db.flush()

        snap2 = await record_snapshot(
            competitor_id=comp.id,
            snapshot_date="2026-03-04",
            subscriber_count=200,
            db=db,
        )
        await db.commit()

    assert snap2.id == snap1_id  # Same row updated
    assert snap2.subscriber_count == 200


@pytest.mark.anyio
async def test_service_growth_summary(client: AsyncClient):
    """compute_growth_summary compares two most recent snapshots."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import (
        add_competitor,
        compute_growth_summary,
        record_snapshot,
    )

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_growth",
            name="Growth Channel",
            db=db,
        )
        await db.flush()

        await record_snapshot(
            competitor_id=comp.id,
            snapshot_date="2026-03-03",
            subscriber_count=1000,
            total_views=50000,
            video_count=50,
            db=db,
        )
        await record_snapshot(
            competitor_id=comp.id,
            snapshot_date="2026-03-04",
            subscriber_count=1200,
            total_views=55000,
            video_count=52,
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        summary = await compute_growth_summary(
            competitor_id=comp.id,
            db=db,
        )

    assert summary["has_data"] is True
    assert summary["subscriber_change"] == 200
    assert summary["view_change"] == 5000
    assert summary["video_change"] == 2
    assert summary["period_start"] == "2026-03-03"
    assert summary["period_end"] == "2026-03-04"


@pytest.mark.anyio
async def test_service_growth_summary_no_data(client: AsyncClient):
    """Growth summary with < 2 snapshots returns has_data=False."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.competitor_service import add_competitor, compute_growth_summary

    async with async_session_factory() as db:
        comp = await add_competitor(
            channel_id=channel_id,
            youtube_channel_id="UC_nodata",
            name="No Data Channel",
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        summary = await compute_growth_summary(
            competitor_id=comp.id,
            db=db,
        )

    assert summary["has_data"] is False


# ═══════════════════════════════════════════════════════════════════════
# 3. Router: POST /competitors
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_add_competitor_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, status_code = await _add_competitor(client, token)

    assert status_code == 201
    assert data["youtube_channel_id"] == COMPETITOR_BODY["youtube_channel_id"]
    assert data["name"] == COMPETITOR_BODY["name"]
    assert data["is_active"] is True


@pytest.mark.anyio
async def test_add_competitor_requires_channel(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/competitors",
        json=COMPETITOR_BODY,
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "channel" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_add_competitor_duplicate_400(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _add_competitor(client, token)
    resp = await client.post(
        "/competitors",
        json=COMPETITOR_BODY,
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "already tracking" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 4. Router: GET /competitors
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_competitors_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get("/competitors", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.anyio
async def test_list_competitors_after_add(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _add_competitor(client, token)

    resp = await client.get("/competitors", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["competitors"][0]["name"] == "Google Developers"


# ═══════════════════════════════════════════════════════════════════════
# 5. Router: GET /competitors/{id}
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_competitor_by_id(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    resp = await client.get(f"/competitors/{comp_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["competitor"]["id"] == comp_id
    assert resp.json()["growth"]["has_data"] is False


@pytest.mark.anyio
async def test_get_competitor_404(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get("/competitors/nonexistent-id", headers=_auth(token))
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 6. Router: DELETE /competitors/{id}
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_delete_competitor_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    resp = await client.delete(f"/competitors/{comp_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert "removed" in resp.json()["message"].lower()

    # Should no longer appear in active list
    list_resp = await client.get("/competitors", headers=_auth(token))
    assert list_resp.json()["count"] == 0


@pytest.mark.anyio
async def test_delete_competitor_not_found(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.delete("/competitors/nonexistent-id", headers=_auth(token))
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# 7. Router: POST /competitors/{id}/snapshots
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_record_snapshot_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    resp = await client.post(
        f"/competitors/{comp_id}/snapshots",
        json={
            "snapshot_date": "2026-03-04",
            "subscriber_count": 5100000,
            "total_views": 2000000000,
            "video_count": 1500,
            "avg_views_per_video": 1333333,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["subscriber_count"] == 5100000
    assert resp.json()["snapshot_date"] == "2026-03-04"


@pytest.mark.anyio
async def test_record_snapshot_invalid_date_422(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    resp = await client.post(
        f"/competitors/{comp_id}/snapshots",
        json={
            "snapshot_date": "not-a-date",
            "subscriber_count": 100,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_record_snapshot_unknown_competitor_404(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/competitors/nonexistent-id/snapshots",
        json={"snapshot_date": "2026-03-04"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 8. Router: GET /competitors/{id}/snapshots
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_snapshots_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    resp = await client.get(
        f"/competitors/{comp_id}/snapshots",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.anyio
async def test_list_snapshots_after_record(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    # Record 2 snapshots
    for date in ["2026-03-03", "2026-03-04"]:
        await client.post(
            f"/competitors/{comp_id}/snapshots",
            json={
                "snapshot_date": date,
                "subscriber_count": 5000000,
                "total_views": 2000000000,
                "video_count": 1500,
            },
            headers=_auth(token),
        )

    resp = await client.get(
        f"/competitors/{comp_id}/snapshots",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
    # Newest first
    assert resp.json()["snapshots"][0]["snapshot_date"] == "2026-03-04"


@pytest.mark.anyio
async def test_list_snapshots_unknown_competitor_404(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get(
        "/competitors/nonexistent-id/snapshots",
        headers=_auth(token),
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 9. Include inactive filter
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_include_inactive(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, _ = await _add_competitor(client, token)
    comp_id = data["id"]

    # Remove it
    await client.delete(f"/competitors/{comp_id}", headers=_auth(token))

    # Without include_inactive — 0
    resp = await client.get("/competitors", headers=_auth(token))
    assert resp.json()["count"] == 0

    # With include_inactive — 1
    resp = await client.get(
        "/competitors?include_inactive=true",
        headers=_auth(token),
    )
    assert resp.json()["count"] == 1
    assert resp.json()["competitors"][0]["is_active"] is False


# ═══════════════════════════════════════════════════════════════════════
# 10. Schema / import tests
# ═══════════════════════════════════════════════════════════════════════

class TestCompetitorSchemas:

    def test_schemas_import(self):
        from backend.schemas import (
            CompetitorAddRequest,
            CompetitorGrowthResponse,
            CompetitorListResponse,
            CompetitorResponse,
            CompetitorSnapshotCreateRequest,
            CompetitorSnapshotListResponse,
            CompetitorSnapshotResponse,
        )
        assert CompetitorAddRequest
        assert CompetitorGrowthResponse

    def test_service_import(self):
        from backend.services.competitor_service import (
            add_competitor,
            compute_growth_summary,
            get_competitor,
            list_competitors,
            list_snapshots,
            record_snapshot,
            remove_competitor,
            MAX_COMPETITORS,
        )
        assert callable(add_competitor)
        assert MAX_COMPETITORS == 10

    def test_worker_import(self):
        from backend.workers.competitor_worker import competitor_loop
        assert callable(competitor_loop)
