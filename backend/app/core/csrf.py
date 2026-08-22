"""Origin checking for the two endpoints that authenticate by cookie alone.

Moving the refresh token into a cookie buys XSS resistance and takes on CSRF
in exchange: the browser now attaches the credential to a request whether or
not the page that triggered it belongs to this app. That trade is only worth
making if the second half is actually paid for.

The exposure is smaller than it looks. Every other endpoint authenticates
with `Authorization: Bearer`, and a cross-site page cannot set that header --
doing so makes the request preflighted, and CORS refuses it. So only
`/auth/refresh` and `/auth/logout`, which have nothing but the cookie to go
on, are reachable this way, and the refresh cookie's `Path` keeps the browser
from sending it anywhere else at all.

Two independent things now have to hold for a cross-site POST to land:
`SameSite=Lax` has to fail (it withholds the cookie on cross-site POSTs), and
the request has to carry an `Origin` this app answers to. Origin is checked
rather than a double-submit token because these two endpoints are used by one
first-party SPA and nothing else: there is no client that legitimately posts
to them without an Origin, and a token would add a value the page must fetch,
store and echo -- more moving parts, in the flow that must not break.
"""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from app.config import settings


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def assert_same_origin(request: Request) -> None:
    """Rejects a cookie-authenticated request that did not come from the app.

    `Referer` is consulted only when `Origin` is missing. Browsers send
    `Origin` on every POST, same-site or not, so in practice the fallback
    covers privacy tooling that strips it rather than any normal request --
    and a request with neither header is refused rather than trusted.
    """
    allowed = {origin for origin in (_origin_of(o) for o in settings.cors_origins_list) if origin}

    stated = request.headers.get("origin") or ""
    if not stated or stated.lower() == "null":
        referer = request.headers.get("referer") or ""
        stated = _origin_of(referer) or ""

    if not stated:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Запрос отклонён: не указан источник",
        )
    if stated not in allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Запрос отклонён: недопустимый источник",
        )
