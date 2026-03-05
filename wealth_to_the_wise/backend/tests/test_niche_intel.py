# filepath: backend/tests/test_niche_intel.py
"""
Tests for Empire OS Phase 2: Niche Intelligence Engine.

Covers:
  - Niche service (analyse_niche, save_niche_snapshot)
  - Router endpoints (list snapshots, scan, topics, get snapshot)
  - Feature flag gating
  - Schema validation
  - Worker importability
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

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
    """Fresh app + DB with both multi-channel and niche intel ON."""
    with patch.dict(os.environ, {
        "FF_EMPIRE_MULTI_CHANNEL": "1",
        "FF_EMPIRE_NICHE_INTEL": "1",
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
    """Niche intel flag OFF."""
    with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}, clear=False):
        os.environ.pop("FF_EMPIRE_NICHE_INTEL", None)
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
    "email": "niche-test@example.com",
    "password": "strongpass123",
    "full_name": "Niche Tester",
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


async def _setup_channel_and_keys(token: str, client: AsyncClient) -> str:
    """Create a channel and store a fake OpenAI key. Returns channel_id."""
    # Create channel
    resp = await client.post(
        "/channels",
        json={"name": "Niche Test Channel", "platform": "youtube"},
        headers=_auth(token),
    )
    channel_id = resp.json()["id"]

    # Store a fake OpenAI key
    from backend.database import async_session_factory
    from backend.encryption import encrypt
    from backend.models import User, UserApiKeys, _new_uuid
    from sqlalchemy import select

    async with async_session_factory() as db:
        user_result = await db.execute(
            select(User).where(User.email == SIGNUP_BODY["email"])
        )
        user = user_result.scalar_one()

        keys = UserApiKeys(
            id=_new_uuid(),
            user_id=user.id,
            openai_api_key=encrypt("sk-test-fake-key-for-niche-testing-12345678"),
        )
        db.add(keys)
        await db.commit()

    return channel_id


# Fake GPT response for mocking
FAKE_ANALYSIS = {
    "saturation_score": 65,
    "trending_score": 78,
    "search_volume_est": 150000,
    "competitor_count": 340,
    "topics": [
        {
            "topic": "Why Most People Lose Money in Index Funds",
            "estimated_demand": 9,
            "competition_level": "medium",
            "source": "gpt_analysis",
        },
        {
            "topic": "The Hidden Fees Eating Your Returns",
            "estimated_demand": 8,
            "competition_level": "low",
            "source": "gpt_analysis",
        },
        {
            "topic": "Dollar Cost Averaging vs Lump Sum in 2026",
            "estimated_demand": 7,
            "competition_level": "high",
            "source": "gpt_analysis",
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag gating
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_niche_403_when_flag_off(client_flag_off: AsyncClient):
    token = await _signup_and_login(client_flag_off)
    resp = await client_flag_off.get("/niche/snapshots", headers=_auth(token))
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 2. Niche service unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestNicheService:

    def test_analyse_niche_parses_valid_response(self):
        """Mock httpx.post to return valid JSON and verify parsing."""
        from backend.services.niche_service import analyse_niche

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(FAKE_ANALYSIS)}}]
        }

        with patch("backend.services.niche_service.httpx.post", return_value=mock_response):
            result = analyse_niche(
                niche="Personal Finance",
                openai_api_key="sk-test-key-12345678901234567890",
            )

        assert result["saturation_score"] == 65
        assert result["trending_score"] == 78
        assert len(result["topics"]) == 3

    def test_analyse_niche_strips_code_fences(self):
        """Model sometimes wraps JSON in ```json ... ```."""
        from backend.services.niche_service import analyse_niche

        wrapped = f"```json\n{json.dumps(FAKE_ANALYSIS)}\n```"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": wrapped}}]
        }

        with patch("backend.services.niche_service.httpx.post", return_value=mock_response):
            result = analyse_niche(
                niche="Personal Finance",
                openai_api_key="sk-test-key-12345678901234567890",
            )

        assert result["saturation_score"] == 65

    def test_analyse_niche_raises_on_api_error(self):
        """Non-200 from OpenAI → ValueError."""
        from backend.services.niche_service import analyse_niche

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "rate limited"

        with patch("backend.services.niche_service.httpx.post", return_value=mock_response):
            with pytest.raises(ValueError, match="OpenAI API error"):
                analyse_niche(
                    niche="Test",
                    openai_api_key="sk-test-key-12345678901234567890",
                )

    def test_analyse_niche_raises_on_invalid_json(self):
        from backend.services.niche_service import analyse_niche

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not valid json at all"}}]
        }

        with patch("backend.services.niche_service.httpx.post", return_value=mock_response):
            with pytest.raises(ValueError, match="Invalid JSON"):
                analyse_niche(
                    niche="Test",
                    openai_api_key="sk-test-key-12345678901234567890",
                )

    def test_analyse_niche_raises_on_missing_fields(self):
        from backend.services.niche_service import analyse_niche

        incomplete = {"saturation_score": 50}  # missing other required fields
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(incomplete)}}]
        }

        with patch("backend.services.niche_service.httpx.post", return_value=mock_response):
            with pytest.raises(ValueError, match="Missing required field"):
                analyse_niche(
                    niche="Test",
                    openai_api_key="sk-test-key-12345678901234567890",
                )


# ═══════════════════════════════════════════════════════════════════════
# 3. Save snapshot (DB persistence)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_save_niche_snapshot(client: AsyncClient):
    """Verify save_niche_snapshot creates DB rows correctly."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel_and_keys(token, client)

    from backend.database import async_session_factory
    from backend.services.niche_service import save_niche_snapshot

    async with async_session_factory() as db:
        snapshot, topics = await save_niche_snapshot(
            channel_id=channel_id,
            niche="Personal Finance",
            analysis=FAKE_ANALYSIS,
            db_session=db,
        )
        await db.commit()

    assert snapshot.niche == "Personal Finance"
    assert snapshot.saturation_score == 65
    assert snapshot.channel_id == channel_id
    assert len(topics) == 3
    assert topics[0].topic == "Why Most People Lose Money in Index Funds"


# ═══════════════════════════════════════════════════════════════════════
# 4. Router: POST /niche/scan (mocked OpenAI)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_niche_scan_endpoint(client: AsyncClient):
    """POST /niche/scan creates a snapshot via mocked OpenAI."""
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    with patch("backend.services.niche_service.analyse_niche", return_value=FAKE_ANALYSIS):
        resp = await client.post(
            "/niche/scan",
            json={"niche": "Personal Finance"},
            headers=_auth(token),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["niche"] == "Personal Finance"
    assert data["saturation_score"] == 65
    assert data["trending_score"] == 78
    assert len(data["topics"]) == 3


@pytest.mark.anyio
async def test_niche_scan_requires_openai_key(client: AsyncClient):
    """Scan without OpenAI key returns 400."""
    token = await _signup_and_login(client)

    # Create channel but NO api keys
    await client.post(
        "/channels",
        json={"name": "No Keys Channel", "platform": "youtube"},
        headers=_auth(token),
    )

    resp = await client.post(
        "/niche/scan",
        json={"niche": "Test Niche"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "openai" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_niche_scan_requires_channel(client: AsyncClient):
    """Scan without any channel returns 400."""
    token = await _signup_and_login(client)

    resp = await client.post(
        "/niche/scan",
        json={"niche": "Test Niche"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "channel" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 5. Router: GET /niche/snapshots
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_snapshots_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    resp = await client.get("/niche/snapshots", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["snapshots"] == []


@pytest.mark.anyio
async def test_list_snapshots_after_scan(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    with patch("backend.services.niche_service.analyse_niche", return_value=FAKE_ANALYSIS):
        await client.post(
            "/niche/scan",
            json={"niche": "Personal Finance"},
            headers=_auth(token),
        )

    resp = await client.get("/niche/snapshots", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["snapshots"][0]["niche"] == "Personal Finance"
    assert len(data["snapshots"][0]["topics"]) == 3


# ═══════════════════════════════════════════════════════════════════════
# 6. Router: GET /niche/snapshots/{id}
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_snapshot_by_id(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    with patch("backend.services.niche_service.analyse_niche", return_value=FAKE_ANALYSIS):
        scan_resp = await client.post(
            "/niche/scan",
            json={"niche": "Real Estate"},
            headers=_auth(token),
        )

    snapshot_id = scan_resp.json()["id"]

    resp = await client.get(f"/niche/snapshots/{snapshot_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["niche"] == "Real Estate"
    assert len(resp.json()["topics"]) == 3


@pytest.mark.anyio
async def test_get_snapshot_404(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    resp = await client.get("/niche/snapshots/nonexistent-id", headers=_auth(token))
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 7. Router: GET /niche/topics
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_topics_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    resp = await client.get("/niche/topics", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.anyio
async def test_list_topics_after_scan(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel_and_keys(token, client)

    with patch("backend.services.niche_service.analyse_niche", return_value=FAKE_ANALYSIS):
        await client.post(
            "/niche/scan",
            json={"niche": "Personal Finance"},
            headers=_auth(token),
        )

    resp = await client.get("/niche/topics", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    # Sorted by demand desc
    demands = [t["estimated_demand"] for t in data["topics"]]
    assert demands == sorted(demands, reverse=True)


# ═══════════════════════════════════════════════════════════════════════
# 8. Validation
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_scan_rejects_empty_niche(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/niche/scan",
        json={"niche": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_scan_rejects_single_char_niche(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/niche/scan",
        json={"niche": "X"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# 9. Schema imports
# ═══════════════════════════════════════════════════════════════════════

class TestNicheSchemas:

    def test_schemas_import(self):
        from backend.schemas import (
            NicheScanRequest,
            NicheSnapshotResponse,
            NicheSnapshotListResponse,
            NicheTopicResponse,
            NicheTopicListResponse,
        )
        assert NicheScanRequest
        assert NicheSnapshotResponse

    def test_service_import(self):
        from backend.services.niche_service import analyse_niche, save_niche_snapshot
        assert callable(analyse_niche)
        assert callable(save_niche_snapshot)

    def test_worker_import(self):
        from backend.workers.niche_worker import niche_loop
        assert callable(niche_loop)
