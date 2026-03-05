# filepath: backend/tests/test_auth.py
"""
Tests for the auth system (Item 2).

Run:  python -m pytest backend/tests/test_auth.py -v
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

    # Clean up tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Helpers ──────────────────────────────────────────────────────────

SIGNUP_BODY = {
    "email": "alice@example.com",
    "password": "strongpass123",
    "full_name": "Alice Test",
}


async def _signup(client: AsyncClient, body: dict | None = None) -> tuple[dict, int]:
    resp = await client.post("/auth/signup", json=body or SIGNUP_BODY)
    return resp.json(), resp.status_code



async def _login(client: AsyncClient, email: str = "alice@example.com", password: str = "strongpass123") -> tuple[dict, int]:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    # Propagate Set-Cookie into the client cookie jar so subsequent
    # requests (e.g. /auth/refresh) include the httpOnly refresh cookie.
    for cookie_header in resp.headers.get_list("set-cookie"):
        # parse "name=value; ..." — we only need the name=value part
        name_value = cookie_header.split(";")[0]
        if "=" in name_value:
            name, value = name_value.split("=", 1)
            client.cookies.set(name.strip(), value.strip())
    return resp.json(), resp.status_code


def _extract_refresh_cookie(client: AsyncClient) -> str | None:
    """Pull the refresh_token value from the test client's cookie jar."""
    for cookie in client.cookies.jar:
        if cookie.name == "refresh_token":
            return cookie.value
    return None


# ── Signup ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_signup_success(client: AsyncClient):
    data, status = await _signup(client)
    assert status == 201
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Test"
    assert data["plan"] == "free"
    assert "id" in data


@pytest.mark.anyio
async def test_signup_duplicate_email(client: AsyncClient):
    await _signup(client)
    data, status = await _signup(client)
    assert status == 409
    assert "already exists" in data["detail"]


@pytest.mark.anyio
async def test_signup_short_password(client: AsyncClient):
    resp = await client.post("/auth/signup", json={
        "email": "bob@example.com",
        "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_signup_invalid_email(client: AsyncClient):
    resp = await client.post("/auth/signup", json={
        "email": "not-an-email",
        "password": "strongpass123",
    })
    assert resp.status_code == 422


# ── Login ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_login_success(client: AsyncClient):
    await _signup(client)
    data, status = await _login(client)
    assert status == 200
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # refresh_token is now in an httpOnly cookie, not in the body
    assert "refresh_token" not in data


@pytest.mark.anyio
async def test_login_wrong_password(client: AsyncClient):
    await _signup(client)
    data, status = await _login(client, password="wrongpassword")
    assert status == 401
    assert "Invalid email or password" in data["detail"]


@pytest.mark.anyio
async def test_login_nonexistent_user(client: AsyncClient):
    data, status = await _login(client, email="nobody@example.com")
    assert status == 401


# ── GET /auth/me ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_me_authenticated(client: AsyncClient):
    await _signup(client)
    tokens, _ = await _login(client)

    resp = await client.get("/auth/me", headers={
        "Authorization": f"Bearer {tokens['access_token']}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Test"
    assert data["plan"] == "free"
    assert data["is_active"] is True


@pytest.mark.anyio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_me_bad_token(client: AsyncClient):
    resp = await client.get("/auth/me", headers={
        "Authorization": "Bearer invalid.token.here",
    })
    assert resp.status_code == 401


# ── PATCH /auth/me ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_update_profile(client: AsyncClient):
    await _signup(client)
    tokens, _ = await _login(client)

    resp = await client.patch("/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"full_name": "Alice Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Alice Updated"


# ── Token refresh ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_refresh_token(client: AsyncClient):
    await _signup(client)
    tokens, _ = await _login(client)

    # The refresh token now lives in an httpOnly cookie set by login.
    # httpx's AsyncClient captures Set-Cookie automatically in its jar,
    # so subsequent requests send it back.
    refresh_cookie = _extract_refresh_cookie(client)
    assert refresh_cookie, "Login should set a refresh_token cookie"

    resp = await client.post("/auth/refresh", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # refresh_token is rotated in the cookie, not in the body
    assert "refresh_token" not in data


@pytest.mark.anyio
async def test_refresh_with_access_token_fails(client: AsyncClient):
    await _signup(client)
    tokens, _ = await _login(client)

    # Manually set the cookie to the access token (wrong token type)
    client.cookies.set("refresh_token", tokens["access_token"])
    resp = await client.post("/auth/refresh", json={})
    assert resp.status_code == 401


# ── Forgot / Reset password ─────────────────────────────────────────

@pytest.mark.anyio
async def test_forgot_password_always_200(client: AsyncClient):
    # Even for non-existent emails (no info leak)
    resp = await client.post("/auth/forgot-password", json={
        "email": "nobody@example.com",
    })
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_reset_password_bad_token(client: AsyncClient):
    resp = await client.post("/auth/reset-password", json={
        "token": "nonexistent",
        "new_password": "newpassword123",
    })
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_full_reset_flow(client: AsyncClient):
    """Forgot → reset → login with new password."""
    await _signup(client)

    # Request reset
    resp = await client.post("/auth/forgot-password", json={
        "email": "alice@example.com",
    })
    assert resp.status_code == 200

    # Extract token from DB directly (in production it would be emailed)
    from sqlalchemy import select
    from backend.database import async_session_factory
    from backend.models import User

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "alice@example.com")
        )
        user = result.scalar_one()
        reset_token = user.reset_token
        assert reset_token is not None

    # Reset password
    resp = await client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": "brandnewpass456",
    })
    assert resp.status_code == 200

    # Login with new password works
    data, status = await _login(client, password="brandnewpass456")
    assert status == 200
    assert "access_token" in data

    # Login with old password fails
    data, status = await _login(client, password="strongpass123")
    assert status == 401
