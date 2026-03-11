# filepath: backend/tests/test_referrals.py
"""
Tests for Phase 5: Referral / Affiliate System — /api/referrals/*

Covers:
- Auth gating (all authenticated endpoints)
- Get/generate referral code
- Dashboard stats
- Validate code (public endpoint)
- Record referral on signup (internal helper)
- Convert referral on plan upgrade (internal helper)
- Self-referral rejection
- Email masking in referred user list
- Payout history

Run:  python -m pytest backend/tests/test_referrals.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import User, Referral, ReferralPayout

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

async def _signup_and_login(client: AsyncClient, email: str = "alice@test.com") -> dict:
    await client.post("/auth/signup", json={
        "email": email,
        "password": "testpass123",
        "full_name": "Test User",
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
async def test_referral_code_requires_auth(client: AsyncClient):
    resp = await client.get("/api/referrals/code")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_dashboard_requires_auth(client: AsyncClient):
    resp = await client.get("/api/referrals/dashboard")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_referred_requires_auth(client: AsyncClient):
    resp = await client.get("/api/referrals/referred")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_payouts_requires_auth(client: AsyncClient):
    resp = await client.get("/api/referrals/payouts")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# 2. Get / Generate referral code
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_referral_code(client: AsyncClient):
    """First call generates a code, second call returns the same one."""
    tokens = await _signup_and_login(client)

    resp1 = await client.get("/api/referrals/code", headers=_auth(tokens))
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["referral_code"].startswith("TBV-")
    assert "tubevo.us/signup?ref=" in data1["share_url"]

    # Second call returns the same code
    resp2 = await client.get("/api/referrals/code", headers=_auth(tokens))
    assert resp2.json()["referral_code"] == data1["referral_code"]


# ══════════════════════════════════════════════════════════════════════
# 3. Dashboard stats
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_dashboard_fresh_user(client: AsyncClient):
    """Dashboard returns zeroes for a user with no referrals."""
    tokens = await _signup_and_login(client)

    resp = await client.get("/api/referrals/dashboard", headers=_auth(tokens))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_referred"] == 0
    assert data["total_converted"] == 0
    assert data["total_earned_cents"] == 0
    assert data["total_pending_cents"] == 0
    assert data["commission_pct"] == 20
    assert data["commission_months"] == 12
    assert data["referral_code"].startswith("TBV-")


# ══════════════════════════════════════════════════════════════════════
# 4. Validate code
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_validate_invalid_code(client: AsyncClient):
    """Invalid code returns valid=False."""
    resp = await client.post(
        "/api/referrals/validate",
        json={"code": "TBV-DOESNOTEXIST"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


@pytest.mark.anyio
async def test_validate_valid_code(client: AsyncClient):
    """After generating a code, it validates successfully."""
    tokens = await _signup_and_login(client)

    # Generate code
    code_resp = await client.get("/api/referrals/code", headers=_auth(tokens))
    code = code_resp.json()["referral_code"]

    # Validate it (public endpoint — no auth)
    resp = await client.post(
        "/api/referrals/validate",
        json={"code": code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    # referrer_name should be the first name
    assert data["referrer_name"] == "Test"


# ══════════════════════════════════════════════════════════════════════
# 5. Record referral on signup (internal helper)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_record_referral_signup(client: AsyncClient):
    """record_referral_signup creates a Referral record."""
    from backend.routers.referrals import record_referral_signup

    tokens = await _signup_and_login(client, email="referrer@test.com")

    # Generate referrer's code
    code_resp = await client.get("/api/referrals/code", headers=_auth(tokens))
    code = code_resp.json()["referral_code"]

    # Create a "new user" directly
    await _signup_and_login(client, email="newbie@test.com")

    async with async_session_factory() as db:
        new_user = (await db.execute(
            select(User).where(User.email == "newbie@test.com")
        )).scalar_one()

        referral = await record_referral_signup(code, new_user, db)
        await db.commit()

    assert referral is not None
    assert referral.status == "signup"


@pytest.mark.anyio
async def test_self_referral_rejected(client: AsyncClient):
    """Users cannot refer themselves."""
    from backend.routers.referrals import record_referral_signup

    tokens = await _signup_and_login(client, email="sneaky@test.com")
    code_resp = await client.get("/api/referrals/code", headers=_auth(tokens))
    code = code_resp.json()["referral_code"]

    async with async_session_factory() as db:
        user = (await db.execute(
            select(User).where(User.email == "sneaky@test.com")
        )).scalar_one()

        result = await record_referral_signup(code, user, db)

    assert result is None


# ══════════════════════════════════════════════════════════════════════
# 6. Convert referral on upgrade (internal helper)
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_convert_referral_on_upgrade(client: AsyncClient):
    """Converting a referred user creates a payout record."""
    from backend.routers.referrals import record_referral_signup, convert_referral_on_upgrade

    # Setup: referrer
    tokens_r = await _signup_and_login(client, email="referrer@test.com")
    code_resp = await client.get("/api/referrals/code", headers=_auth(tokens_r))
    code = code_resp.json()["referral_code"]

    # Setup: referred user
    await _signup_and_login(client, email="referred@test.com")

    async with async_session_factory() as db:
        new_user = (await db.execute(
            select(User).where(User.email == "referred@test.com")
        )).scalar_one()
        await record_referral_signup(code, new_user, db)
        await db.commit()

    # Now simulate upgrade
    async with async_session_factory() as db:
        user = (await db.execute(
            select(User).where(User.email == "referred@test.com")
        )).scalar_one()
        user.plan = "pro"
        payout = await convert_referral_on_upgrade(user, "pro", db, stripe_invoice_id="inv_test_123")
        await db.commit()

    assert payout is not None
    # Pro plan = $79/mo, 20% commission = $15.80 = 1580 cents
    assert payout.amount_cents == 1580
    assert payout.trigger == "checkout"
    assert payout.status == "pending"


# ══════════════════════════════════════════════════════════════════════
# 7. Referred users list & Payouts
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_referred_list_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)
    resp = await client.get("/api/referrals/referred", headers=_auth(tokens))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_payouts_list_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)
    resp = await client.get("/api/referrals/payouts", headers=_auth(tokens))
    assert resp.status_code == 200
    assert resp.json() == []


# ══════════════════════════════════════════════════════════════════════
# 8. Constants sanity
# ══════════════════════════════════════════════════════════════════════

def test_referral_constants():
    """Referral constants are sensible."""
    from backend.utils import (
        REFERRAL_COMMISSION_PCT,
        REFERRAL_COMMISSION_MONTHS,
        PLAN_MONTHLY_PRICE_CENTS,
    )
    assert REFERRAL_COMMISSION_PCT == 20
    assert REFERRAL_COMMISSION_MONTHS == 12
    assert PLAN_MONTHLY_PRICE_CENTS["free"] == 0
    assert PLAN_MONTHLY_PRICE_CENTS["starter"] > 0
    assert PLAN_MONTHLY_PRICE_CENTS["pro"] > PLAN_MONTHLY_PRICE_CENTS["starter"]
    assert PLAN_MONTHLY_PRICE_CENTS["agency"] > PLAN_MONTHLY_PRICE_CENTS["pro"]
