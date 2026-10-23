"""The blanket guards in front of /api: a per-address request limit and a
per-worker ceiling on requests in flight."""

import asyncio

import httpx

from app.config import settings
from app.core.middleware import LoadSheddingMiddleware


def _app(gate: asyncio.Event | None = None):
    async def inner(scope, receive, send):
        if gate is not None:
            await gate.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return LoadSheddingMiddleware(inner)


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_requests_past_the_per_address_limit_get_429(monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.API_BY_IP.limit", 3)
    async with _client(_app()) as client:
        codes = [(await client.get("/api/v1/categories")).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


async def test_the_limit_covers_only_the_api():
    async with _client(_app()) as client:
        for _ in range(settings.api_rate_limit_per_minute + 5):
            assert (await client.get("/health")).status_code == 200


async def test_requests_past_the_in_flight_ceiling_are_shed_with_503(monkeypatch):
    monkeypatch.setattr(settings, "max_inflight_requests", 2)
    gate = asyncio.Event()
    app = _app(gate)
    async with _client(app) as client:
        held = [asyncio.create_task(client.get("/api/v1/lessons/1")) for _ in range(2)]
        while app.inflight < 2:
            await asyncio.sleep(0)
        shed = await client.get("/api/v1/lessons/1")
        assert shed.status_code == 503
        assert shed.headers["Retry-After"]
        # Marks "the handler never ran", which is what lets the client resend a write.
        assert shed.headers["X-Load-Shed"] == "1"

        gate.set()
        assert [(await t).status_code for t in held] == [200, 200]
        assert app.inflight == 0
        assert (await client.get("/api/v1/lessons/1")).status_code == 200


async def test_an_exhausted_db_pool_is_a_503_not_a_500(client):
    """Under saturation every request in the backlog used to end in a 500
    and a traceback. No connection means nothing was done: a retryable 503."""
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError

    from app.database import get_db
    from app.main import app

    async def exhausted():
        raise PoolTimeoutError("QueuePool limit of size 5 overflow 5 reached")
        yield  # pragma: no cover -- makes this a dependency generator like get_db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = exhausted
    try:
        response = await client.get("/api/v1/categories")
    finally:
        app.dependency_overrides[get_db] = previous
    assert response.status_code == 503
    assert response.headers["Retry-After"]
    assert "X-Load-Shed" not in response.headers
