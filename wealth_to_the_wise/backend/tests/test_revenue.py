# filepath: backend/tests/test_revenue.py
"""
Tests for Empire OS Phase 3: Revenue Attribution.

Covers:
  - Revenue service (record_revenue_event, aggregate_daily_revenue, compute_revenue_summary)
  - Router endpoints (summary, events CRUD, daily, aggregation trigger)
  - Feature flag gating
  - Schema validation
  - Worker importability
  - Deduplication logic
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
    """Fresh app + DB with multi-channel and revenue ON."""
    with patch.dict(os.environ, {
        "FF_EMPIRE_MULTI_CHANNEL": "1",
        "FF_EMPIRE_REVENUE": "1",
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
    """Revenue flag OFF."""
    with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}, clear=False):
        os.environ.pop("FF_EMPIRE_REVENUE", None)
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
    "email": "revenue-test@example.com",
    "password": "strongpass123",
    "full_name": "Revenue Tester",
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
        json={"name": "Revenue Test Channel", "platform": "youtube"},
        headers=_auth(token),
    )
    return resp.json()["id"]


async def _create_event(
    client: AsyncClient,
    token: str,
    *,
    source: str = "adsense",
    amount_cents: int = 1500,
    event_date: str = "2026-03-01",
    external_id: str | None = None,
) -> dict:
    """Helper to create a revenue event and return its JSON."""
    body: dict = {
        "source": source,
        "amount_cents": amount_cents,
        "event_date": event_date,
    }
    if external_id:
        body["external_id"] = external_id

    resp = await client.post(
        "/revenue/events",
        json=body,
        headers=_auth(token),
    )
    return resp.json(), resp.status_code


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag gating
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_revenue_403_when_flag_off(client_flag_off: AsyncClient):
    token = await _signup_and_login(client_flag_off)
    resp = await client_flag_off.get("/revenue/summary", headers=_auth(token))
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 2. Revenue service unit tests
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_service_record_event(client: AsyncClient):
    """record_revenue_event creates a DB row with correct fields."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.revenue_service import record_revenue_event

    async with async_session_factory() as db:
        event = await record_revenue_event(
            channel_id=channel_id,
            source="adsense",
            amount_cents=2500,
            event_date="2026-03-01",
            external_id="adsense-001",
            db=db,
        )
        await db.commit()

    assert event.source == "adsense"
    assert event.amount_cents == 2500
    assert event.channel_id == channel_id
    assert event.external_id == "adsense-001"


@pytest.mark.anyio
async def test_service_record_event_dedup(client: AsyncClient):
    """Duplicate (source, external_id) raises ValueError."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.revenue_service import record_revenue_event

    async with async_session_factory() as db:
        await record_revenue_event(
            channel_id=channel_id,
            source="stripe",
            amount_cents=999,
            event_date="2026-03-01",
            external_id="pi_test_123",
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="Duplicate"):
            await record_revenue_event(
                channel_id=channel_id,
                source="stripe",
                amount_cents=999,
                event_date="2026-03-01",
                external_id="pi_test_123",
                db=db,
            )


@pytest.mark.anyio
async def test_service_invalid_source(client: AsyncClient):
    """Invalid source raises ValueError."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.revenue_service import record_revenue_event

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="Invalid revenue source"):
            await record_revenue_event(
                channel_id=channel_id,
                source="bitcoin",
                amount_cents=100,
                event_date="2026-03-01",
                db=db,
            )


@pytest.mark.anyio
async def test_service_negative_amount(client: AsyncClient):
    """Negative amount raises ValueError."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.revenue_service import record_revenue_event

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="non-negative"):
            await record_revenue_event(
                channel_id=channel_id,
                source="manual",
                amount_cents=-100,
                event_date="2026-03-01",
                db=db,
            )


@pytest.mark.anyio
async def test_service_aggregate_daily(client: AsyncClient):
    """aggregate_daily_revenue computes correct totals by source."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.revenue_service import (
        aggregate_daily_revenue,
        record_revenue_event,
    )

    async with async_session_factory() as db:
        await record_revenue_event(
            channel_id=channel_id, source="adsense",
            amount_cents=1000, event_date="2026-03-01", db=db,
        )
        await record_revenue_event(
            channel_id=channel_id, source="affiliate",
            amount_cents=500, event_date="2026-03-01", db=db,
        )
        await record_revenue_event(
            channel_id=channel_id, source="stripe",
            amount_cents=2000, event_date="2026-03-01", db=db,
        )
        await db.flush()

        agg = await aggregate_daily_revenue(
            channel_id=channel_id,
            agg_date="2026-03-01",
            db=db,
        )
        await db.commit()

    assert agg.total_cents == 3500
    assert agg.adsense_cents == 1000
    assert agg.affiliate_cents == 500
    assert agg.stripe_cents == 2000


@pytest.mark.anyio
async def test_service_summary(client: AsyncClient):
    """compute_revenue_summary returns correct breakdown."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)

    from backend.database import async_session_factory
    from backend.services.revenue_service import (
        compute_revenue_summary,
        record_revenue_event,
    )

    async with async_session_factory() as db:
        await record_revenue_event(
            channel_id=channel_id, source="adsense",
            amount_cents=5000, event_date="2026-03-01", db=db,
        )
        await record_revenue_event(
            channel_id=channel_id, source="manual",
            amount_cents=1200, event_date="2026-03-02", db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        summary = await compute_revenue_summary(
            channel_id=channel_id,
            days=30,
            db=db,
        )

    assert summary["total_cents"] == 6200
    assert summary["adsense_cents"] == 5000
    assert summary["manual_cents"] == 1200
    assert summary["days_covered"] == 2
    assert summary["daily_average_cents"] == 3100  # 6200 / 2


# ═══════════════════════════════════════════════════════════════════════
# 3. Router: POST /revenue/events
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_event_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    data, status_code = await _create_event(
        client, token,
        source="adsense", amount_cents=2500, event_date="2026-03-01",
    )

    assert status_code == 201
    assert data["source"] == "adsense"
    assert data["amount_cents"] == 2500
    assert data["event_date"] == "2026-03-01"
    assert data["currency"] == "USD"


@pytest.mark.anyio
async def test_create_event_requires_channel(client: AsyncClient):
    token = await _signup_and_login(client)
    # No channel created
    resp = await client.post(
        "/revenue/events",
        json={"source": "manual", "amount_cents": 100, "event_date": "2026-03-01"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "channel" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_create_event_invalid_source_422(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/revenue/events",
        json={"source": "bitcoin", "amount_cents": 100, "event_date": "2026-03-01"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_event_invalid_date_422(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/revenue/events",
        json={"source": "manual", "amount_cents": 100, "event_date": "not-a-date"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_event_negative_amount_422(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/revenue/events",
        json={"source": "manual", "amount_cents": -100, "event_date": "2026-03-01"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# 4. Router: GET /revenue/events
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_events_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get("/revenue/events", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["events"] == []


@pytest.mark.anyio
async def test_list_events_after_create(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _create_event(client, token, source="adsense", amount_cents=1000, event_date="2026-03-01")
    await _create_event(client, token, source="affiliate", amount_cents=500, event_date="2026-03-02")

    resp = await client.get("/revenue/events", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


@pytest.mark.anyio
async def test_list_events_filter_by_source(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _create_event(client, token, source="adsense", amount_cents=1000, event_date="2026-03-01")
    await _create_event(client, token, source="affiliate", amount_cents=500, event_date="2026-03-02")

    resp = await client.get(
        "/revenue/events?source=adsense",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["events"][0]["source"] == "adsense"


# ═══════════════════════════════════════════════════════════════════════
# 5. Router: GET /revenue/summary
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_summary_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get("/revenue/summary", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cents"] == 0
    assert data["period_days"] == 30


@pytest.mark.anyio
async def test_summary_with_data(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _create_event(client, token, source="adsense", amount_cents=3000, event_date="2026-03-01")
    await _create_event(client, token, source="stripe", amount_cents=2000, event_date="2026-03-02")

    resp = await client.get("/revenue/summary", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cents"] == 5000
    assert data["adsense_cents"] == 3000
    assert data["stripe_cents"] == 2000


@pytest.mark.anyio
async def test_summary_custom_days(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _create_event(client, token, source="manual", amount_cents=100, event_date="2026-03-01")

    resp = await client.get("/revenue/summary?days=7", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


# ═══════════════════════════════════════════════════════════════════════
# 6. Router: GET /revenue/daily
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_daily_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get("/revenue/daily", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.anyio
async def test_daily_after_aggregation(client: AsyncClient):
    """After creating events and triggering aggregation, daily shows data."""
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _create_event(client, token, source="adsense", amount_cents=1500, event_date="2026-03-01")
    await _create_event(client, token, source="affiliate", amount_cents=800, event_date="2026-03-01")

    # Trigger aggregation
    resp = await client.post(
        "/revenue/daily/2026-03-01/agg",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    agg = resp.json()
    assert agg["total_cents"] == 2300
    assert agg["adsense_cents"] == 1500
    assert agg["affiliate_cents"] == 800

    # Now the daily list should show it
    resp = await client.get("/revenue/daily", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["daily"][0]["agg_date"] == "2026-03-01"


# ═══════════════════════════════════════════════════════════════════════
# 7. Router: POST /revenue/daily/{date}/agg
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_agg_trigger_bad_date(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/revenue/daily/not-a-date/agg",
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "YYYY-MM-DD" in resp.json()["detail"]


@pytest.mark.anyio
async def test_agg_trigger_empty_date(client: AsyncClient):
    """Aggregation for a date with no events returns zeros."""
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/revenue/daily/2026-01-15/agg",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total_cents"] == 0


@pytest.mark.anyio
async def test_agg_re_aggregation_updates(client: AsyncClient):
    """Running aggregation twice updates the existing row."""
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    await _create_event(client, token, source="adsense", amount_cents=1000, event_date="2026-03-01")

    # First aggregation
    resp1 = await client.post("/revenue/daily/2026-03-01/agg", headers=_auth(token))
    assert resp1.json()["total_cents"] == 1000

    # Add more events
    await _create_event(client, token, source="manual", amount_cents=500, event_date="2026-03-01")

    # Re-aggregate
    resp2 = await client.post("/revenue/daily/2026-03-01/agg", headers=_auth(token))
    assert resp2.json()["total_cents"] == 1500

    # Daily list should show 1 entry (upserted, not duplicated)
    resp = await client.get("/revenue/daily", headers=_auth(token))
    assert resp.json()["count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 8. Deduplication via external_id
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_event_dedup_external_id(client: AsyncClient):
    """Creating two events with same (source, external_id) returns 400."""
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    _, status1 = await _create_event(
        client, token, source="stripe",
        amount_cents=999, event_date="2026-03-01",
        external_id="pi_dedup_test_001",
    )
    assert status1 == 201

    resp = await client.post(
        "/revenue/events",
        json={
            "source": "stripe",
            "amount_cents": 999,
            "event_date": "2026-03-01",
            "external_id": "pi_dedup_test_001",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "Duplicate" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════
# 9. Schema / import tests
# ═══════════════════════════════════════════════════════════════════════

class TestRevenueSchemas:

    def test_schemas_import(self):
        from backend.schemas import (
            RevenueEventCreateRequest,
            RevenueEventResponse,
            RevenueEventListResponse,
            RevenueDailyAggResponse,
            RevenueDailyListResponse,
            RevenueSummaryResponse,
            RevenueTopVideoResponse,
        )
        assert RevenueEventCreateRequest
        assert RevenueSummaryResponse

    def test_service_import(self):
        from backend.services.revenue_service import (
            record_revenue_event,
            aggregate_daily_revenue,
            compute_revenue_summary,
            VALID_SOURCES,
        )
        assert callable(record_revenue_event)
        assert callable(aggregate_daily_revenue)
        assert callable(compute_revenue_summary)
        assert "adsense" in VALID_SOURCES

    def test_worker_import(self):
        from backend.workers.revenue_worker import revenue_loop
        assert callable(revenue_loop)
