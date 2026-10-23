"""Response headers and a body-size ceiling applied to every request."""

import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.core.rate_limit import API_BY_IP, request_ip

logger = logging.getLogger(__name__)

# Applied by the app itself rather than only at the edge: the API is also
# reachable directly (compose network, a future second front-end, curl during
# an incident), and a header that only exists in the proxy config is a header
# that isn't there on any of those paths.
_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    # The API returns JSON and files, never a document that should run script
    # or be framed. The SPA's own (much longer) policy lives in the Caddyfile.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, value in _BASE_HEADERS.items():
            response.headers.setdefault(header, value)

        # Almost everything under /api is scoped to one user: a lesson, a
        # homework submission, somebody's own profile. Put a caching proxy or
        # a CDN in front of this -- which the availability work recommends --
        # and an unmarked response is one it may serve to the next person who
        # asks for the same URL. Leaking another pupil's answers out of a
        # shared cache is a worse outcome than any cache miss.
        #
        # `setdefault`, so the handful of routes that genuinely are cacheable
        # (uploaded images, video segments) can say so themselves.
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "private, no-store")
        if settings.is_production:
            # Only in production: sent over plain HTTP during local
            # development it would pin localhost to https in the developer's
            # browser, for a year, across every project on that port.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects an over-sized body before the route handler reads it.

    The edge cap (2100 MB, sized for lesson videos) has to stay large enough
    for the largest legitimate upload, which leaves every JSON endpoint
    willing to accept a two-gigabyte body. This one is the small default;
    the handful of genuinely large routes are exempted by path prefix.
    """

    # Lesson video uploads only: streamed to disk in bounded chunks by their
    # own handler, which enforces its own (much larger) cap -- see
    # app/core/video.py. This used to exempt the whole /teacher/lessons/
    # prefix, so lesson edits and question saves -- plain JSON, parsed in
    # memory -- accepted bodies up to the 2 GB edge limit.
    @staticmethod
    def _is_exempt(path: str) -> bool:
        return path.startswith("/api/v1/teacher/lessons/") and path.endswith("/video")

    async def dispatch(self, request: Request, call_next):
        if not self._is_exempt(request.url.path):
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > settings.max_request_body_bytes:
                        return JSONResponse(
                            {"detail": "Тело запроса слишком большое"},
                            status_code=413,
                            headers=dict(_BASE_HEADERS),
                        )
                except ValueError:
                    return JSONResponse(
                        {"detail": "Некорректный заголовок Content-Length"},
                        status_code=400,
                        headers=dict(_BASE_HEADERS),
                    )
        return await call_next(request)


class LoadSheddingMiddleware:
    """Per-address rate limit and a per-worker in-flight ceiling for /api.

    Plain ASGI rather than BaseHTTPMiddleware: it runs on every request, and
    a rejection here should cost a dictionary lookup, not a task and a
    response wrapper.
    """

    def __init__(self, app) -> None:
        self.app = app
        self.inflight = 0

    @staticmethod
    def _exempt(path: str) -> bool:
        # Health checks must answer while the API is shedding, or the
        # orchestrator restarts a worker that is merely busy. Video uploads
        # are long single requests with their own concurrency gate.
        return not path.startswith("/api/") or (
            path.startswith("/api/v1/teacher/lessons/") and path.endswith("/video")
        )

    async def _reject(self, scope, receive, send, status_code: int, detail: str, retry_after: int) -> None:
        response = JSONResponse(
            {"detail": detail},
            status_code=status_code,
            # X-Load-Shed: the handler never ran, so even a write is safe to
            # repeat -- the client retries those (see api/http.ts).
            headers={**_BASE_HEADERS, "Retry-After": str(retry_after), "Cache-Control": "no-store", "X-Load-Shed": "1"},
        )
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self._exempt(scope["path"]):
            await self.app(scope, receive, send)
            return

        if self.inflight >= settings.max_inflight_requests:
            logger.warning("Shedding %s: %d requests in flight", scope["path"], self.inflight)
            await self._reject(scope, receive, send, 503, "Сервер перегружен. Повторите через пару секунд.", 2)
            return

        allowed, retry_after = await API_BY_IP.hit(request_ip(Request(scope)))
        if not allowed:
            await self._reject(scope, receive, send, 429, "Слишком много запросов. Попробуйте позже.", retry_after)
            return

        self.inflight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.inflight -= 1
