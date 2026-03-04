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
    """Checkout returns a meaningful response depending on Stripe config.

    - 503 = Stripe key not configured at all
    - 502 = Stripe key present but API call failed (e.g. bad price ID)
    - 200 = Stripe key AND valid price IDs configured → checkout URL returned
    """
    tokens = await _signup_and_login(client)
    resp = await client.post(
        "/billing/create-checkout-session",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    # Any of these is acceptable depending on the environment's Stripe config
    assert resp.status_code in (200, 502, 503)


@pytest.mark.anyio
async def test_portal_requires_auth(client: AsyncClient):
    """Portal endpoint requires authentication."""
    resp = await client.get("/billing/portal")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_webhook_accepts_post(client: AsyncClient):
    """Webhook endpoint accepts POST and responds appropriately.

    - 400 = signature verification failed (expected without a real Stripe sig)
    - 503 = Stripe not configured at all
    - 200 = event processed (only possible with a valid signature)
    """
    resp = await client.post(
        "/billing/webhook",
        content=b'{"type": "test.event", "data": {"object": {}}}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (200, 400, 503)
    if resp.status_code == 200:
        assert resp.json()["received"] is True
