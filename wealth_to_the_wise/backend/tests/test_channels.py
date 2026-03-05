# filepath: backend/tests/test_channels.py
"""
Tests for Empire OS Phase 1: Multi-Channel Management.

Covers:
  - Full CRUD for /channels
  - Default channel promotion
  - YouTube linking
  - Channel limit enforcement
  - Feature flag gating (403 when off)
  - channel_context dependency
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
    """Fresh app + DB for every test (multi-channel flag ON)."""
    with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}):
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
    """Same as above but with multi-channel flag OFF."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FF_EMPIRE_MULTI_CHANNEL", None)
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
    "email": "channel-test@example.com",
    "password": "strongpass123",
    "full_name": "Channel Tester",
}


async def _signup_and_login(client: AsyncClient) -> str:
    """Create user and return Bearer token."""
    await client.post("/auth/signup", json=SIGNUP_BODY)
    resp = await client.post(
        "/auth/login",
        json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_channel(
    client: AsyncClient,
    token: str,
    name: str = "Test Channel",
) -> dict:
    resp = await client.post(
        "/channels",
        json={"name": name, "platform": "youtube"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag gating
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_channels_403_when_flag_off(client_flag_off: AsyncClient):
    """Endpoints return 401/403 when FF_MULTI_CHANNEL is off."""
    token = await _signup_and_login(client_flag_off)
    resp = await client_flag_off.get("/channels", headers=_auth(token))
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 2. Channel CRUD
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_channel_returns_201(client: AsyncClient):
    token = await _signup_and_login(client)
    data = await _create_channel(client, token, "My First Channel")
    assert data["name"] == "My First Channel"
    assert data["platform"] == "youtube"
    assert data["is_default"] is True  # first channel is auto-default
    assert data["id"]


@pytest.mark.anyio
async def test_list_channels(client: AsyncClient):
    token = await _signup_and_login(client)
    await _create_channel(client, token, "Channel A")
    await _create_channel(client, token, "Channel B")

    resp = await client.get("/channels", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    names = {ch["name"] for ch in data["channels"]}
    assert "Channel A" in names
    assert "Channel B" in names


@pytest.mark.anyio
async def test_get_channel_by_id(client: AsyncClient):
    token = await _signup_and_login(client)
    created = await _create_channel(client, token, "Solo Channel")

    resp = await client.get(f"/channels/{created['id']}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "Solo Channel"


@pytest.mark.anyio
async def test_get_channel_404_for_wrong_user(client: AsyncClient):
    """User A cannot see User B's channel."""
    token_a = await _signup_and_login(client)
    created = await _create_channel(client, token_a, "A's Channel")

    # Create a second user
    await client.post("/auth/signup", json={
        "email": "other@example.com", "password": "strongpass123",
    })
    resp = await client.post("/auth/login", json={
        "email": "other@example.com", "password": "strongpass123",
    })
    token_b = resp.json()["access_token"]

    resp = await client.get(f"/channels/{created['id']}", headers=_auth(token_b))
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_channel_name(client: AsyncClient):
    token = await _signup_and_login(client)
    created = await _create_channel(client, token)

    resp = await client.patch(
        f"/channels/{created['id']}",
        json={"name": "Renamed Channel"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Channel"


@pytest.mark.anyio
async def test_delete_channel(client: AsyncClient):
    token = await _signup_and_login(client)
    ch_a = await _create_channel(client, token, "Channel A")
    await _create_channel(client, token, "Channel B")

    resp = await client.delete(f"/channels/{ch_a['id']}", headers=_auth(token))
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()

    # Only 1 channel left
    resp = await client.get("/channels", headers=_auth(token))
    assert resp.json()["count"] == 1


@pytest.mark.anyio
async def test_cannot_delete_only_channel(client: AsyncClient):
    token = await _signup_and_login(client)
    ch = await _create_channel(client, token, "Only Channel")

    resp = await client.delete(f"/channels/{ch['id']}", headers=_auth(token))
    assert resp.status_code == 400
    assert "only channel" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 3. Default channel logic
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_first_channel_is_default(client: AsyncClient):
    token = await _signup_and_login(client)
    first = await _create_channel(client, token, "First")
    assert first["is_default"] is True

    second = await _create_channel(client, token, "Second")
    assert second["is_default"] is False


@pytest.mark.anyio
async def test_set_default_channel(client: AsyncClient):
    token = await _signup_and_login(client)
    await _create_channel(client, token, "Original Default")
    second = await _create_channel(client, token, "New Default")

    resp = await client.post(
        f"/channels/{second['id']}/set-default",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    # Verify old default is no longer default
    resp = await client.get("/channels", headers=_auth(token))
    channels = resp.json()["channels"]
    defaults = [ch for ch in channels if ch["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "New Default"


@pytest.mark.anyio
async def test_delete_default_promotes_oldest(client: AsyncClient):
    """Deleting the default channel auto-promotes the oldest remaining."""
    token = await _signup_and_login(client)
    first = await _create_channel(client, token, "First (default)")
    second = await _create_channel(client, token, "Second")
    third = await _create_channel(client, token, "Third")

    # Delete the default (first)
    resp = await client.delete(f"/channels/{first['id']}", headers=_auth(token))
    assert resp.status_code == 200

    # Check new default
    resp = await client.get("/channels", headers=_auth(token))
    channels = resp.json()["channels"]
    defaults = [ch for ch in channels if ch["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Second"


# ═══════════════════════════════════════════════════════════════════════
# 4. Channel limit
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_channel_limit_enforced(client: AsyncClient):
    """Cannot create more than MAX_CHANNELS_PER_USER channels."""
    from backend.routers.channels import MAX_CHANNELS_PER_USER
    from backend.database import async_session_factory
    from backend.models import Channel, User, _new_uuid, _utcnow
    from sqlalchemy import select

    token = await _signup_and_login(client)

    # Insert channels directly via DB to avoid rate limits
    async with async_session_factory() as db:
        user_result = await db.execute(
            select(User).where(User.email == SIGNUP_BODY["email"])
        )
        user = user_result.scalar_one()

        for i in range(MAX_CHANNELS_PER_USER):
            ch = Channel(
                id=_new_uuid(),
                user_id=user.id,
                name=f"Channel {i}",
                platform="youtube",
                is_default=(i == 0),
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(ch)
        await db.commit()

    # One more via API should fail
    resp = await client.post(
        "/channels",
        json={"name": "One Too Many", "platform": "youtube"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "maximum" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 5. YouTube linking
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_link_youtube_requires_oauth(client: AsyncClient):
    """Linking without a YouTube connection returns 400."""
    token = await _signup_and_login(client)
    ch = await _create_channel(client, token, "Unlinked")

    resp = await client.post(
        f"/channels/{ch['id']}/link-youtube",
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "no youtube connection" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_link_youtube_success(client: AsyncClient):
    """With an OAuthToken present, link-youtube populates the channel."""
    token = await _signup_and_login(client)
    ch = await _create_channel(client, token, "My Channel")

    # Manually insert an OAuthToken for this user
    from backend.database import async_session_factory
    from backend.encryption import encrypt
    from backend.models import OAuthToken, _new_uuid, _utcnow
    from sqlalchemy import select
    from backend.models import User

    async with async_session_factory() as db:
        user_result = await db.execute(
            select(User).where(User.email == SIGNUP_BODY["email"])
        )
        user = user_result.scalar_one()

        oauth = OAuthToken(
            id=_new_uuid(),
            user_id=user.id,
            provider="google",
            access_token=encrypt("fake-access-token"),
            refresh_token=encrypt("fake-refresh-token"),
            channel_id="UC1234567890",
            channel_title="My YT Channel",
            provider_email="test@gmail.com",
        )
        db.add(oauth)
        await db.commit()

    resp = await client.post(
        f"/channels/{ch['id']}/link-youtube",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["youtube_channel_id"] == "UC1234567890"
    assert data["youtube_connected"] is True
    assert data["channel_title"] == "My YT Channel"


# ═══════════════════════════════════════════════════════════════════════
# 6. Patch set-default via PATCH endpoint
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_patch_set_default(client: AsyncClient):
    token = await _signup_and_login(client)
    await _create_channel(client, token, "First")
    second = await _create_channel(client, token, "Second")

    resp = await client.patch(
        f"/channels/{second['id']}",
        json={"is_default": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True


# ═══════════════════════════════════════════════════════════════════════
# 7. Channel context dependency
# ═══════════════════════════════════════════════════════════════════════

class TestChannelContext:
    """Test the get_active_channel dependency logic."""

    def test_module_imports(self):
        from backend.channel_context import get_active_channel
        assert callable(get_active_channel)

    def test_schemas_import(self):
        from backend.schemas import (
            ChannelCreateRequest,
            ChannelUpdateRequest,
            ChannelResponse,
            ChannelListResponse,
        )
        assert ChannelCreateRequest
        assert ChannelUpdateRequest
        assert ChannelResponse
        assert ChannelListResponse


# ═══════════════════════════════════════════════════════════════════════
# 8. Validation
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_channel_empty_name_rejected(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/channels",
        json={"name": "", "platform": "youtube"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_channel_invalid_platform_rejected(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/channels",
        json={"name": "Test", "platform": "tiktok"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
