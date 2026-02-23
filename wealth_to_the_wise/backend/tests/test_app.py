# filepath: backend/tests/test_app.py
"""
Smoke tests for the FastAPI backend (Item 1).

Run:  python -m pytest backend/tests/ -v
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Health endpoint ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_health_returns_200(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data


@pytest.mark.anyio
async def test_health_has_request_id_header(client: AsyncClient):
    resp = await client.get("/health")
    assert "x-request-id" in resp.headers


# ── 404 for unknown routes ──────────────────────────────────────────

@pytest.mark.anyio
async def test_unknown_route_returns_404(client: AsyncClient):
    resp = await client.get("/nonexistent")
    assert resp.status_code == 404


# ── CORS headers present ────────────────────────────────────────────

@pytest.mark.anyio
async def test_cors_headers_on_preflight(client: AsyncClient):
    resp = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


# ── OpenAPI docs available ───────────────────────────────────────────

@pytest.mark.anyio
async def test_docs_page_available(client: AsyncClient):
    resp = await client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_openapi_json_available(client: AsyncClient):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["info"]["title"] == "Tubevo"
