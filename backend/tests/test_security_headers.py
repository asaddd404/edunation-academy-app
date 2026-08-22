"""Response headers and the request-body ceiling.

These run against /health, which needs no database -- the point is the
middleware stack, not the route.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.fixture
async def bare_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_every_response_carries_the_baseline_headers(bare_client):
    response = await bare_client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    # The API serves JSON and files; nothing it returns should be able to
    # load a script or be framed.
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


async def test_error_responses_carry_them_too(bare_client):
    """A 404 is still a response a browser renders, and headers that only
    appear on the happy path are headers an attacker routes around."""
    response = await bare_client.get("/no-such-route")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_hsts_is_absent_outside_production(bare_client):
    """Sent over plain http in development it would pin localhost to https
    in the developer's browser for a year, across every project on that port."""
    assert settings.is_production is False
    response = await bare_client.get("/health")
    assert "strict-transport-security" not in response.headers


async def test_hsts_is_sent_in_production(bare_client, monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    response = await bare_client.get("/health")
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


async def test_oversized_body_is_rejected_before_the_route_runs(bare_client):
    """The edge cap has to stay at ~2 GB for lesson video uploads, which
    leaves every JSON endpoint willing to read a two-gigabyte body into
    memory. This is the small default that actually applies to them."""
    oversized = settings.max_request_body_bytes + 1
    response = await bare_client.post(
        "/api/v1/auth/login",
        content=b"x",
        headers={"content-length": str(oversized), "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_normal_sized_body_passes_the_gate(bare_client):
    """The ceiling must not be so eager that ordinary traffic is caught by
    it -- a limit that blocks real requests gets removed rather than tuned.
    Posted at a route that needs no database: what is under test is the gate,
    not the handler behind it."""
    response = await bare_client.post("/no-such-route", json={"answers": [1, 2, 3]})
    assert response.status_code == 404


async def test_video_upload_route_is_exempt_from_the_small_ceiling(bare_client):
    """Lesson videos legitimately run to gigabytes and are streamed to disk
    in bounded chunks by their own handler. If the generic ceiling applied
    here, uploading a lesson video would fail outright."""
    response = await bare_client.post(
        "/api/v1/teacher/lessons/1/video",
        content=b"x",
        headers={"content-length": str(settings.max_request_body_bytes + 1)},
    )
    assert response.status_code != 413
