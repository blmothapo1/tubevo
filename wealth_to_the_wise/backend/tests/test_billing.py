# filepath: backend/tests/test_billing.py
"""
Tests for the billing router (Stripe integration).
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
        "email": f"billing-{unique}@test.com",
        "password": "testpass123",
        "full_name": "Billing Test",
    })
    resp = await client.post("/auth/login", json={
        "email": f"billing-{unique}@test.com",
        "password": "testpass123",
    })
    return resp.json()


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_checkout_requires_auth(client: AsyncClient):
    """Checkout endpoint requires authentication."""
    resp = await client.post("/billing/create-checkout-session", json={"plan": "pro"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_checkout_graceful_failure(client: AsyncClient):
    """Checkout fails gracefully — 503 if Stripe key missing, 502 if key
    is present but price IDs are placeholders (no real Stripe product)."""
    tokens = await _signup_and_login(client)
    resp = await client.post(
        "/billing/create-checkout-session",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    # 503 = key not configured, 502 = key present but placeholder price ID
    assert resp.status_code in (502, 503)


@pytest.mark.anyio
async def test_portal_requires_auth(client: AsyncClient):
    """Portal endpoint requires authentication."""
    resp = await client.get("/billing/portal")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_webhook_accepts_post(client: AsyncClient):
    """Webhook endpoint accepts POST (even with empty/invalid payload in test).
    Returns 200 when Stripe is configured, or 503 when it isn't (e.g. in CI)."""
    resp = await client.post(
        "/billing/webhook",
        content=b'{"type": "test.event", "data": {"object": {}}}',
        headers={"Content-Type": "application/json"},
    )
    # 200 = normal response, 503 = Stripe not configured (CI)
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        assert resp.json()["received"] is True
