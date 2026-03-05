# filepath: backend/tests/test_thumb_ab.py
"""
Tests for Empire OS Phase 4: Auto A/B Thumbnail Testing.

Covers:
  - Thumb A/B service (create, rotate, conclude, cancel, record metrics)
  - Router endpoints (list, create, get, conclude, cancel, rotate)
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
    """Fresh app + DB with multi-channel and thumb A/B ON."""
    with patch.dict(os.environ, {
        "FF_EMPIRE_MULTI_CHANNEL": "1",
        "FF_EMPIRE_THUMB_AB": "1",
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
    """Thumb A/B flag OFF."""
    with patch.dict(os.environ, {"FF_EMPIRE_MULTI_CHANNEL": "1"}, clear=False):
        os.environ.pop("FF_EMPIRE_THUMB_AB", None)
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
    "email": "thumb-test@example.com",
    "password": "strongpass123",
    "full_name": "Thumb Tester",
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
        json={"name": "Thumb Test Channel", "platform": "youtube"},
        headers=_auth(token),
    )
    return resp.json()["id"]


async def _create_video(channel_id: str, user_id: str) -> str:
    """Insert a VideoRecord directly and return its ID."""
    from backend.database import async_session_factory
    from backend.models import VideoRecord, _new_uuid, _utcnow

    video_id = _new_uuid()
    async with async_session_factory() as db:
        video = VideoRecord(
            id=video_id,
            user_id=user_id,
            channel_id=channel_id,
            topic="Test Thumbnail Video",
            title="Test Thumbnail Video Title",
            status="completed",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(video)
        await db.commit()
    return video_id


async def _get_user_id(email: str) -> str:
    """Look up user ID by email."""
    from backend.database import async_session_factory
    from backend.models import User
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one().id


VARIANTS_BODY = [
    {"concept": "bold_curiosity", "file_path": "/tmp/thumb_bold.jpg"},
    {"concept": "contrarian_dramatic", "file_path": "/tmp/thumb_contra.jpg"},
    {"concept": "clean_authority", "file_path": "/tmp/thumb_clean.jpg"},
]


async def _create_experiment(
    client: AsyncClient,
    token: str,
    video_id: str,
) -> dict:
    """Create an experiment via the API and return the JSON."""
    resp = await client.post(
        "/thumbnails/experiments",
        json={
            "video_record_id": video_id,
            "variants": VARIANTS_BODY,
        },
        headers=_auth(token),
    )
    return resp.json(), resp.status_code


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag gating
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_thumb_403_when_flag_off(client_flag_off: AsyncClient):
    token = await _signup_and_login(client_flag_off)
    resp = await client_flag_off.get("/thumbnails/experiments", headers=_auth(token))
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════
# 2. Service unit tests
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_service_create_experiment(client: AsyncClient):
    """create_experiment returns an experiment with 3 variants."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import create_experiment

    async with async_session_factory() as db:
        exp, variants = await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )
        await db.commit()

    assert exp.status == "running"
    assert exp.channel_id == channel_id
    assert len(variants) == 3
    assert variants[0].is_active is True
    assert variants[1].is_active is False


@pytest.mark.anyio
async def test_service_create_rejects_single_variant(client: AsyncClient):
    """An experiment needs at least 2 variants."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import create_experiment

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="at least 2"):
            await create_experiment(
                channel_id=channel_id,
                video_record_id=video_id,
                variants=[VARIANTS_BODY[0]],
                db=db,
            )


@pytest.mark.anyio
async def test_service_create_rejects_duplicate_experiment(client: AsyncClient):
    """A video can only have one running experiment."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import create_experiment

    async with async_session_factory() as db:
        await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="already has a running"):
            await create_experiment(
                channel_id=channel_id,
                video_record_id=video_id,
                variants=VARIANTS_BODY,
                db=db,
            )


@pytest.mark.anyio
async def test_service_rotate_variant(client: AsyncClient):
    """rotate_active_variant cycles through variants."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import create_experiment, rotate_active_variant

    async with async_session_factory() as db:
        exp, variants = await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )
        # Initially variant 0 is active
        assert variants[0].is_active is True

        # Rotate → variant 1 should become active
        new = await rotate_active_variant(experiment_id=exp.id, db=db)
        await db.commit()

    assert new is not None
    assert new.concept == "contrarian_dramatic"


@pytest.mark.anyio
async def test_service_record_metrics(client: AsyncClient):
    """record_variant_metrics updates impressions, clicks, CTR."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import create_experiment, record_variant_metrics

    async with async_session_factory() as db:
        _, variants = await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )
        await db.flush()

        updated = await record_variant_metrics(
            variant_id=variants[0].id,
            impressions=1000,
            clicks=50,
            db=db,
        )
        await db.commit()

    assert updated.impressions == 1000
    assert updated.clicks == 50
    assert updated.ctr_pct == "5.00"


@pytest.mark.anyio
async def test_service_conclude_force(client: AsyncClient):
    """conclude_experiment with force=True works even with low impressions."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import (
        conclude_experiment,
        create_experiment,
        record_variant_metrics,
    )

    async with async_session_factory() as db:
        exp, variants = await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )
        # Give one variant some clicks
        await record_variant_metrics(
            variant_id=variants[0].id, impressions=10, clicks=5, db=db,
        )
        await record_variant_metrics(
            variant_id=variants[1].id, impressions=10, clicks=2, db=db,
        )
        await record_variant_metrics(
            variant_id=variants[2].id, impressions=10, clicks=1, db=db,
        )

        concluded_exp, winner = await conclude_experiment(
            experiment_id=exp.id, db=db, force=True,
        )
        await db.commit()

    assert concluded_exp.status == "concluded"
    assert winner is not None
    assert winner.concept == "bold_curiosity"  # Highest CTR (5/10)


@pytest.mark.anyio
async def test_service_conclude_rejects_low_impressions(client: AsyncClient):
    """Without force, conclude rejects if impressions < threshold."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import conclude_experiment, create_experiment

    async with async_session_factory() as db:
        exp, _ = await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )

        with pytest.raises(ValueError, match="impressions"):
            await conclude_experiment(experiment_id=exp.id, db=db, force=False)


@pytest.mark.anyio
async def test_service_cancel_experiment(client: AsyncClient):
    """cancel_experiment sets status to cancelled."""
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    from backend.database import async_session_factory
    from backend.services.thumb_ab_service import cancel_experiment, create_experiment

    async with async_session_factory() as db:
        exp, _ = await create_experiment(
            channel_id=channel_id,
            video_record_id=video_id,
            variants=VARIANTS_BODY,
            db=db,
        )

        cancelled = await cancel_experiment(experiment_id=exp.id, db=db)
        await db.commit()

    assert cancelled.status == "cancelled"


# ═══════════════════════════════════════════════════════════════════════
# 3. Router: POST /thumbnails/experiments
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_experiment_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, status_code = await _create_experiment(client, token, video_id)

    assert status_code == 201
    assert data["status"] == "running"
    assert len(data["variants"]) == 3
    assert data["variants"][0]["is_active"] is True


@pytest.mark.anyio
async def test_create_experiment_requires_channel(client: AsyncClient):
    token = await _signup_and_login(client)
    resp = await client.post(
        "/thumbnails/experiments",
        json={
            "video_record_id": "nonexistent",
            "variants": VARIANTS_BODY,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "channel" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_create_experiment_requires_video(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/thumbnails/experiments",
        json={
            "video_record_id": "nonexistent-video-id",
            "variants": VARIANTS_BODY,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_create_experiment_min_variants_422(client: AsyncClient):
    """Request with < 2 variants gets 422 from Pydantic."""
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.post(
        "/thumbnails/experiments",
        json={
            "video_record_id": "vid",
            "variants": [{"concept": "a", "file_path": "/a.jpg"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# 4. Router: GET /thumbnails/experiments
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_experiments_empty(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get("/thumbnails/experiments", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.anyio
async def test_list_experiments_after_create(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    await _create_experiment(client, token, video_id)

    resp = await client.get("/thumbnails/experiments", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 5. Router: GET /thumbnails/experiments/{id}
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_experiment_by_id(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    resp = await client.get(
        f"/thumbnails/experiments/{exp_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == exp_id
    assert len(resp.json()["variants"]) == 3


@pytest.mark.anyio
async def test_get_experiment_404(client: AsyncClient):
    token = await _signup_and_login(client)
    await _setup_channel(token, client)

    resp = await client.get(
        "/thumbnails/experiments/nonexistent-id",
        headers=_auth(token),
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 6. Router: POST /thumbnails/experiments/{id}/conclude
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_conclude_experiment_force(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    resp = await client.post(
        f"/thumbnails/experiments/{exp_id}/conclude",
        json={"force": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "concluded"


@pytest.mark.anyio
async def test_conclude_without_force_rejects(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    resp = await client.post(
        f"/thumbnails/experiments/{exp_id}/conclude",
        json={"force": False},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "impressions" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 7. Router: POST /thumbnails/experiments/{id}/cancel
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_cancel_experiment_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    resp = await client.post(
        f"/thumbnails/experiments/{exp_id}/cancel",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.anyio
async def test_cancel_already_concluded_rejects(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    # Conclude first
    await client.post(
        f"/thumbnails/experiments/{exp_id}/conclude",
        json={"force": True},
        headers=_auth(token),
    )

    # Cancel should fail
    resp = await client.post(
        f"/thumbnails/experiments/{exp_id}/cancel",
        headers=_auth(token),
    )
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# 8. Router: POST /thumbnails/experiments/{id}/rotate
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_rotate_variant_endpoint(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    # First variant should be active initially
    assert data["variants"][0]["is_active"] is True

    # Rotate
    resp = await client.post(
        f"/thumbnails/experiments/{exp_id}/rotate",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["rotation_count"] == 1

    # Second variant should now be active
    active = [v for v in result["variants"] if v["is_active"]]
    assert len(active) == 1
    assert active[0]["concept"] == "contrarian_dramatic"


# ═══════════════════════════════════════════════════════════════════════
# 9. Status filter
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_experiments_status_filter(client: AsyncClient):
    token = await _signup_and_login(client)
    channel_id = await _setup_channel(token, client)
    user_id = await _get_user_id(SIGNUP_BODY["email"])
    video_id = await _create_video(channel_id, user_id)

    data, _ = await _create_experiment(client, token, video_id)
    exp_id = data["id"]

    # Running filter should show 1
    resp = await client.get(
        "/thumbnails/experiments?status=running",
        headers=_auth(token),
    )
    assert resp.json()["count"] == 1

    # Conclude it
    await client.post(
        f"/thumbnails/experiments/{exp_id}/conclude",
        json={"force": True},
        headers=_auth(token),
    )

    # Running filter should show 0
    resp = await client.get(
        "/thumbnails/experiments?status=running",
        headers=_auth(token),
    )
    assert resp.json()["count"] == 0

    # Concluded filter should show 1
    resp = await client.get(
        "/thumbnails/experiments?status=concluded",
        headers=_auth(token),
    )
    assert resp.json()["count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 10. Schema / import tests
# ═══════════════════════════════════════════════════════════════════════

class TestThumbSchemas:

    def test_schemas_import(self):
        from backend.schemas import (
            ThumbConcludeRequest,
            ThumbExperimentCreateRequest,
            ThumbExperimentListResponse,
            ThumbExperimentResponse,
            ThumbVariantInput,
            ThumbVariantResponse,
        )
        assert ThumbExperimentCreateRequest
        assert ThumbVariantResponse

    def test_service_import(self):
        from backend.services.thumb_ab_service import (
            cancel_experiment,
            conclude_experiment,
            create_experiment,
            record_variant_metrics,
            rotate_active_variant,
            get_experiment_with_variants,
            MIN_IMPRESSIONS_PER_VARIANT,
        )
        assert callable(create_experiment)
        assert MIN_IMPRESSIONS_PER_VARIANT == 100

    def test_worker_import(self):
        from backend.workers.thumb_ab_worker import thumb_ab_loop
        assert callable(thumb_ab_loop)
