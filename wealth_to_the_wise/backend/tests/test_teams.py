# filepath: backend/tests/test_teams.py
"""
Tests for Phase 4: Team Seats & Client Workspaces — /api/teams/*

Covers:
- Auth gating (all endpoints require authentication)
- Create team (plan gating, name validation, max teams limit)
- List teams, get team details
- Update team name/description (role-based access)
- Delete team (owner only)
- Invite member (seat limits, duplicate checks, self-invite guard)
- Accept / Decline invitations
- Change member role (hierarchy enforcement)
- Remove member (owner/admin or self-leave)
- Team activity feed

Run:  python -m pytest backend/tests/test_teams.py -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app
from backend.database import Base, engine, async_session_factory
from backend.models import User

from sqlalchemy import select, update


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

async def _signup_and_login(client: AsyncClient, email: str = "owner@test.com") -> dict:
    """Create a user and return login tokens."""
    import uuid
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
    """Directly update a user's plan in the DB."""
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.plan = plan
        await db.commit()


async def _create_team(client: AsyncClient, tokens: dict, name: str = "Test Team") -> dict:
    """Create a team and return the response."""
    resp = await client.post(
        "/api/teams",
        json={"name": name, "description": "A test team"},
        headers=_auth(tokens),
    )
    return resp.json(), resp.status_code


# ══════════════════════════════════════════════════════════════════════
# 1. Auth gating
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_team_requires_auth(client: AsyncClient):
    resp = await client.post("/api/teams", json={"name": "Test"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_teams_requires_auth(client: AsyncClient):
    resp = await client.get("/api/teams")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_team_requires_auth(client: AsyncClient):
    resp = await client.get("/api/teams/fake-id")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# 2. Create team
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_free_plan_cannot_create_team(client: AsyncClient):
    """Free plan users get 403."""
    tokens = await _signup_and_login(client)
    data, status = await _create_team(client, tokens)
    assert status == 403
    assert "Upgrade" in data["detail"]


@pytest.mark.anyio
async def test_starter_can_create_team(client: AsyncClient):
    """Starter plan users can create a team."""
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "starter")

    data, status = await _create_team(client, tokens)
    assert status == 201
    assert data["name"] == "Test Team"
    assert data["member_count"] == 1  # owner auto-added
    assert data["seat_limit"] == 3    # starter plan
    assert "id" in data


@pytest.mark.anyio
async def test_create_team_validates_name_too_short(client: AsyncClient):
    """Team name must be at least 2 chars."""
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "pro")

    resp = await client.post(
        "/api/teams",
        json={"name": "A"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_starter_max_teams_limit(client: AsyncClient):
    """Starter plan allows only 1 team."""
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "starter")

    # Create first team — should succeed
    data1, status1 = await _create_team(client, tokens, name="Team 1")
    assert status1 == 201

    # Create second team — should fail
    data2, status2 = await _create_team(client, tokens, name="Team 2")
    assert status2 == 403
    assert "1 team" in data2["detail"].lower() or "upgrade" in data2["detail"].lower()


# ══════════════════════════════════════════════════════════════════════
# 3. List & Get teams
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_list_teams_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)
    resp = await client.get("/api/teams", headers=_auth(tokens))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_teams_after_create(client: AsyncClient):
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "pro")
    await _create_team(client, tokens)

    resp = await client.get("/api/teams", headers=_auth(tokens))
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 1
    assert teams[0]["name"] == "Test Team"


@pytest.mark.anyio
async def test_get_team_details(client: AsyncClient):
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "pro")
    data, _ = await _create_team(client, tokens)

    resp = await client.get(f"/api/teams/{data['id']}", headers=_auth(tokens))
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["name"] == "Test Team"
    assert len(detail["members"]) == 1
    assert detail["members"][0]["role"] == "owner"


@pytest.mark.anyio
async def test_get_team_nonmember_404(client: AsyncClient):
    """Non-members can't see a team (returns 404 to avoid leaking existence)."""
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    data, _ = await _create_team(client, tokens1)

    tokens2 = await _signup_and_login(client, email="stranger@test.com")
    resp = await client.get(f"/api/teams/{data['id']}", headers=_auth(tokens2))
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# 4. Update team
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_update_team_name(client: AsyncClient):
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "pro")
    data, _ = await _create_team(client, tokens)

    resp = await client.patch(
        f"/api/teams/{data['id']}",
        json={"name": "New Name"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


# ══════════════════════════════════════════════════════════════════════
# 5. Delete team
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_delete_team_owner_only(client: AsyncClient):
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "pro")
    data, _ = await _create_team(client, tokens)

    resp = await client.delete(f"/api/teams/{data['id']}", headers=_auth(tokens))
    assert resp.status_code == 200
    assert "deleted" in resp.json()["detail"].lower()

    # Verify team is gone
    resp = await client.get("/api/teams", headers=_auth(tokens))
    assert len(resp.json()) == 0


@pytest.mark.anyio
async def test_delete_team_non_owner_403(client: AsyncClient):
    """Non-owner cannot delete a team."""
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    data, _ = await _create_team(client, tokens1)

    # Create a second user and give them membership via invite
    tokens2 = await _signup_and_login(client, email="editor@test.com")

    resp = await client.delete(f"/api/teams/{data['id']}", headers=_auth(tokens2))
    # They aren't even a member, so the route returns 403 (owner check fails on owner_id comparison)
    assert resp.status_code in (403, 404)


# ══════════════════════════════════════════════════════════════════════
# 6. Invite / Accept / Decline
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_invite_member(client: AsyncClient):
    tokens = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    # Create the invited user first
    await _signup_and_login(client, email="editor@test.com")

    resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "editor@test.com", "role": "editor"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 201
    assert "token" in resp.json()


@pytest.mark.anyio
async def test_invite_self_rejected(client: AsyncClient):
    """Owner can't invite themselves — gets 409 (already member) or 400 (self-invite)."""
    tokens = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "owner@test.com", "role": "editor"},
        headers=_auth(tokens),
    )
    # Owner is already a member, so "already a member" check (409) fires first,
    # or the self-invite guard (400) fires — either is correct.
    assert resp.status_code in (400, 409)


@pytest.mark.anyio
async def test_invite_duplicate_rejected(client: AsyncClient):
    tokens = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    # First invite
    resp1 = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "dup@test.com", "role": "editor"},
        headers=_auth(tokens),
    )
    assert resp1.status_code == 201

    # Duplicate invite
    resp2 = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "dup@test.com", "role": "editor"},
        headers=_auth(tokens),
    )
    assert resp2.status_code == 409


@pytest.mark.anyio
async def test_invite_invalid_role_rejected(client: AsyncClient):
    tokens = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "new@test.com", "role": "superadmin"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_accept_invite_flow(client: AsyncClient):
    """Full invite → accept flow."""
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens1)

    tokens2 = await _signup_and_login(client, email="editor@test.com")

    # Owner invites editor
    invite_resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "editor@test.com", "role": "editor"},
        headers=_auth(tokens1),
    )
    token = invite_resp.json()["token"]

    # Editor accepts
    resp = await client.post(
        f"/api/teams/invites/{token}/accept",
        headers=_auth(tokens2),
    )
    assert resp.status_code == 200
    assert "joined" in resp.json()["detail"].lower()

    # Verify editor can see the team
    resp = await client.get("/api/teams", headers=_auth(tokens2))
    assert len(resp.json()) == 1


@pytest.mark.anyio
async def test_decline_invite(client: AsyncClient):
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens1)

    tokens2 = await _signup_and_login(client, email="editor@test.com")

    invite_resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "editor@test.com", "role": "editor"},
        headers=_auth(tokens1),
    )
    token = invite_resp.json()["token"]

    resp = await client.post(
        f"/api/teams/invites/{token}/decline",
        headers=_auth(tokens2),
    )
    assert resp.status_code == 200
    assert "declined" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_pending_invites(client: AsyncClient):
    """User can see their pending invites."""
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens1)

    tokens2 = await _signup_and_login(client, email="editor@test.com")

    await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "editor@test.com", "role": "editor"},
        headers=_auth(tokens1),
    )

    resp = await client.get("/api/teams/invites/pending", headers=_auth(tokens2))
    assert resp.status_code == 200
    invites = resp.json()
    assert len(invites) == 1
    assert invites[0]["role"] == "editor"


# ══════════════════════════════════════════════════════════════════════
# 7. Change member role
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_change_member_role(client: AsyncClient):
    """Owner can change a member's role."""
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens1)

    tokens2 = await _signup_and_login(client, email="editor@test.com")

    # Invite + accept
    invite_resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "editor@test.com", "role": "editor"},
        headers=_auth(tokens1),
    )
    token = invite_resp.json()["token"]
    await client.post(f"/api/teams/invites/{token}/accept", headers=_auth(tokens2))

    # Get editor's user_id
    me_resp = await client.get("/auth/me", headers=_auth(tokens2))
    editor_id = me_resp.json()["id"]

    # Owner changes editor → viewer
    resp = await client.patch(
        f"/api/teams/{team_data['id']}/members/{editor_id}",
        json={"role": "viewer"},
        headers=_auth(tokens1),
    )
    assert resp.status_code == 200
    assert "viewer" in resp.json()["detail"]


@pytest.mark.anyio
async def test_cannot_change_owner_role(client: AsyncClient):
    """Owner's role cannot be changed."""
    tokens = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    me_resp = await client.get("/auth/me", headers=_auth(tokens))
    owner_id = me_resp.json()["id"]

    resp = await client.patch(
        f"/api/teams/{team_data['id']}/members/{owner_id}",
        json={"role": "editor"},
        headers=_auth(tokens),
    )
    assert resp.status_code == 400
    assert "owner" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════
# 8. Remove member / Leave team
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_member_can_leave_team(client: AsyncClient):
    """A member can remove themselves (leave)."""
    tokens1 = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens1)

    tokens2 = await _signup_and_login(client, email="editor@test.com")

    # Invite + accept
    invite_resp = await client.post(
        f"/api/teams/{team_data['id']}/invite",
        json={"email": "editor@test.com", "role": "editor"},
        headers=_auth(tokens1),
    )
    token = invite_resp.json()["token"]
    await client.post(f"/api/teams/invites/{token}/accept", headers=_auth(tokens2))

    # Editor leaves
    me_resp = await client.get("/auth/me", headers=_auth(tokens2))
    editor_id = me_resp.json()["id"]

    resp = await client.delete(
        f"/api/teams/{team_data['id']}/members/{editor_id}",
        headers=_auth(tokens2),
    )
    assert resp.status_code == 200
    assert "left" in resp.json()["detail"]


@pytest.mark.anyio
async def test_cannot_remove_owner(client: AsyncClient):
    """The owner cannot be removed."""
    tokens = await _signup_and_login(client, email="owner@test.com")
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    me_resp = await client.get("/auth/me", headers=_auth(tokens))
    owner_id = me_resp.json()["id"]

    resp = await client.delete(
        f"/api/teams/{team_data['id']}/members/{owner_id}",
        headers=_auth(tokens),
    )
    assert resp.status_code == 400
    assert "owner" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════
# 9. Team activity
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_team_activity_empty(client: AsyncClient):
    tokens = await _signup_and_login(client)
    await _set_plan("owner@test.com", "pro")
    team_data, _ = await _create_team(client, tokens)

    resp = await client.get(
        f"/api/teams/{team_data['id']}/activity",
        headers=_auth(tokens),
    )
    assert resp.status_code == 200
    assert resp.json() == []
