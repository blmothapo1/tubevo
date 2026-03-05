# filepath: backend/tests/test_voice_clones.py
"""
Tests for Empire OS Phase 6: Voice Cloning Workflow.

Covers:
  - Voice clone service (create, list, get, transitions, delete, retry)
  - Router endpoints (list, create, get, delete, retry)
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
    """Fresh app + DB with voice clone ON."""
    with patch.dict(os.environ, {
        "FF_EMPIRE_MULTI_CHANNEL": "1",
        "FF_EMPIRE_VOICE_CLONE": "1",
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
    """Voice clone flag OFF."""
    with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}, clear=False):
        os.environ.pop("FF_EMPIRE_VOICE_CLONE", None)
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
    "email": "voice-test@example.com",
    "password": "strongpass123",
    "full_name": "Voice Tester",
}

CLONE_BODY = {
    "name": "My Professional Voice",
    "description": "A clear, authoritative narrator voice.",
    "sample_file_key": "uploads/voice_sample_123.mp3",
    "sample_duration_secs": 30,
    "labels": {"accent": "american", "gender": "male"},
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


async def _get_user_id(email: str) -> str:
    from backend.database import async_session_factory
    from backend.models import User
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one().id


async def _create_clone(client: AsyncClient, token: str) -> tuple[dict, int]:
    resp = await client.post(
        "/voice-clones",
        json=CLONE_BODY,
        headers=_auth(token),
    )
    return resp.json(), resp.status_code


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag gating
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_voice_clones_403_when_flag_off(client_flag_off: AsyncClient):
    token = await _signup_and_login(client_flag_off)
    resp = await client_flag_off.get("/voice-clones", headers=_auth(token))
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 2. Service unit tests
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_service_create_clone(client: AsyncClient):
    """create_voice_clone creates a clone in pending status."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import create_voice_clone

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Test Voice",
            description="A test voice clone.",
            sample_file_key="test/sample.mp3",
            sample_duration_secs=45,
            labels={"accent": "british"},
            db=db,
        )
        await db.commit()

    assert clone.name == "Test Voice"
    assert clone.status == "pending"
    assert clone.description == "A test voice clone."
    assert clone.sample_file_key == "test/sample.mp3"
    assert clone.sample_duration_secs == 45
    assert '"accent"' in (clone.labels_json or "")


@pytest.mark.anyio
async def test_service_create_rejects_empty_name(client: AsyncClient):
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import create_voice_clone

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="name is required"):
            await create_voice_clone(
                user_id=user_id,
                name="   ",
                db=db,
            )


@pytest.mark.anyio
async def test_service_create_rejects_over_limit(client: AsyncClient):
    """Cannot exceed MAX_CLONES_PER_USER."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        MAX_CLONES_PER_USER,
    )

    async with async_session_factory() as db:
        for i in range(MAX_CLONES_PER_USER):
            await create_voice_clone(
                user_id=user_id,
                name=f"Voice {i}",
                db=db,
            )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="Maximum"):
            await create_voice_clone(
                user_id=user_id,
                name="One Too Many",
                db=db,
            )


@pytest.mark.anyio
async def test_service_status_transitions(client: AsyncClient):
    """pending → processing → ready flow."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        mark_processing,
        mark_ready,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Transition Test",
            db=db,
        )
        assert clone.status == "pending"

        processing = await mark_processing(clone_id=clone.id, db=db)
        assert processing.status == "processing"

        ready = await mark_ready(
            clone_id=clone.id,
            elevenlabs_voice_id="el_voice_abc123",
            preview_url="https://cdn.elevenlabs.io/preview/abc.mp3",
            db=db,
        )
        assert ready.status == "ready"
        assert ready.elevenlabs_voice_id == "el_voice_abc123"
        assert ready.preview_url == "https://cdn.elevenlabs.io/preview/abc.mp3"
        await db.commit()


@pytest.mark.anyio
async def test_service_mark_failed(client: AsyncClient):
    """pending → processing → failed flow."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        mark_failed,
        mark_processing,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Fail Test",
            db=db,
        )
        await mark_processing(clone_id=clone.id, db=db)
        failed = await mark_failed(
            clone_id=clone.id,
            error_message="ElevenLabs quota exceeded",
            db=db,
        )
        await db.commit()

    assert failed.status == "failed"
    assert failed.error_message == "ElevenLabs quota exceeded"


@pytest.mark.anyio
async def test_service_mark_processing_rejects_wrong_status(client: AsyncClient):
    """Cannot mark_processing a clone that's already processing."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        mark_processing,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Double Process",
            db=db,
        )
        await mark_processing(clone_id=clone.id, db=db)

        with pytest.raises(ValueError, match="expected 'pending'"):
            await mark_processing(clone_id=clone.id, db=db)


@pytest.mark.anyio
async def test_service_delete_clone(client: AsyncClient):
    """Soft-delete sets status to 'deleted'."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        delete_voice_clone,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Delete Me",
            db=db,
        )
        await db.flush()

        deleted = await delete_voice_clone(
            clone_id=clone.id,
            user_id=user_id,
            db=db,
        )
        await db.commit()

    assert deleted.status == "deleted"


@pytest.mark.anyio
async def test_service_delete_already_deleted_rejects(client: AsyncClient):
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        delete_voice_clone,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Double Delete",
            db=db,
        )
        await db.flush()
        await delete_voice_clone(clone_id=clone.id, user_id=user_id, db=db)
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="already deleted"):
            await delete_voice_clone(
                clone_id=clone.id,
                user_id=user_id,
                db=db,
            )


@pytest.mark.anyio
async def test_service_retry_clone(client: AsyncClient):
    """Retry resets failed → pending."""
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        mark_failed,
        retry_voice_clone,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Retry Test",
            db=db,
        )
        await mark_failed(
            clone_id=clone.id,
            error_message="Temporary error",
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        retried = await retry_voice_clone(
            clone_id=clone.id,
            user_id=user_id,
            db=db,
        )
        await db.commit()

    assert retried.status == "pending"
    assert retried.error_message is None


@pytest.mark.anyio
async def test_service_retry_non_failed_rejects(client: AsyncClient):
    token = await _signup_and_login(client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])

    from backend.database import async_session_factory
    from backend.services.voice_clone_service import (
        create_voice_clone,
        retry_voice_clone,
    )

    async with async_session_factory() as db:
        clone = await create_voice_clone(
            user_id=user_id,
            name="Not Failed",
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="only retry failed"):
            await retry_voice_clone(
                clone_id=clone.id,
                user_id=user_id,
                db=db,
            )


# ═══════════════════════════════════════════════════════════════════════
# 3. Router: POST /voice-clones
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_clone_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    data, status_code = await _create_clone(client, token)

    assert status_code == 201
    assert data["name"] == CLONE_BODY["name"]
    assert data["status"] == "pending"
    assert data["sample_file_key"] == CLONE_BODY["sample_file_key"]


@pytest.mark.anyio
async def test_create_clone_422_empty_name(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/voice-clones",
        json={"name": "", "description": "No name"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# 4. Router: GET /voice-clones
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_clones_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.get("/voice-clones", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.anyio
async def test_list_clones_after_create(client: AsyncClient):
    token = await _signup_and_login(client)
    await _create_clone(client, token)

    resp = await client.get("/voice-clones", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["voice_clones"][0]["name"] == CLONE_BODY["name"]


# ═══════════════════════════════════════════════════════════════════════
# 5. Router: GET /voice-clones/{id}
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_clone_by_id(client: AsyncClient):
    token = await _signup_and_login(client)
    data, _ = await _create_clone(client, token)
    clone_id = data["id"]

    resp = await client.get(f"/voice-clones/{clone_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == clone_id


@pytest.mark.anyio
async def test_get_clone_404(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.get("/voice-clones/nonexistent-id", headers=_auth(token))
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 6. Router: DELETE /voice-clones/{id}
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_delete_clone_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    data, _ = await _create_clone(client, token)
    clone_id = data["id"]

    resp = await client.delete(f"/voice-clones/{clone_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()

    # Should not appear in default list
    list_resp = await client.get("/voice-clones", headers=_auth(token))
    assert list_resp.json()["count"] == 0


@pytest.mark.anyio
async def test_delete_clone_not_found(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.delete("/voice-clones/nonexistent-id", headers=_auth(token))
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# 7. Router: POST /voice-clones/{id}/retry
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_retry_clone_endpoint(client: AsyncClient):
    """Retry a failed clone via the API."""
    token = await _signup_and_login(client)
    data, _ = await _create_clone(client, token)
    clone_id = data["id"]

    # Manually fail the clone via service
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    from backend.database import async_session_factory
    from backend.services.voice_clone_service import mark_failed

    async with async_session_factory() as db:
        await mark_failed(
            clone_id=clone_id,
            error_message="Simulated failure",
            db=db,
        )
        await db.commit()

    # Now retry via API
    resp = await client.post(
        f"/voice-clones/{clone_id}/retry",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"
    assert resp.json()["error_message"] is None


@pytest.mark.anyio
async def test_retry_non_failed_rejects(client: AsyncClient):
    token = await _signup_and_login(client)
    data, _ = await _create_clone(client, token)
    clone_id = data["id"]

    resp = await client.post(
        f"/voice-clones/{clone_id}/retry",
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "failed" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 8. Include deleted filter
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_include_deleted(client: AsyncClient):
    token = await _signup_and_login(client)
    data, _ = await _create_clone(client, token)
    clone_id = data["id"]

    await client.delete(f"/voice-clones/{clone_id}", headers=_auth(token))

    # Without include_deleted — 0
    resp = await client.get("/voice-clones", headers=_auth(token))
    assert resp.json()["count"] == 0

    # With include_deleted — 1
    resp = await client.get(
        "/voice-clones?include_deleted=true",
        headers=_auth(token),
    )
    assert resp.json()["count"] == 1
    assert resp.json()["voice_clones"][0]["status"] == "deleted"


# ═══════════════════════════════════════════════════════════════════════
# 9. Schema / import tests
# ═══════════════════════════════════════════════════════════════════════

class TestVoiceCloneSchemas:

    def test_schemas_import(self):
        from backend.schemas import (
            VoiceCloneCreateRequest,
            VoiceCloneListResponse,
            VoiceCloneResponse,
        )
        assert VoiceCloneCreateRequest
        assert VoiceCloneListResponse
        assert VoiceCloneResponse

    def test_service_import(self):
        from backend.services.voice_clone_service import (
            create_voice_clone,
            delete_voice_clone,
            get_voice_clone,
            list_voice_clones,
            mark_failed,
            mark_processing,
            mark_ready,
            retry_voice_clone,
            MAX_CLONES_PER_USER,
        )
        assert callable(create_voice_clone)
        assert MAX_CLONES_PER_USER == 5

    def test_worker_import(self):
        from backend.workers.voice_clone_worker import voice_clone_loop
        assert callable(voice_clone_loop)

    def test_app_imports_ff_voice_clone(self):
        """Verify app.py imports FF_VOICE_CLONE."""
        from backend.app import create_app
        # Just verify no import error
        assert callable(create_app)
