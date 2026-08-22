"""The refresh token as an httpOnly cookie.

Before this change the refresh token was returned in the response body and
kept in localStorage, where any script running on the page could read it --
so one XSS bug anywhere in the app bought a thirty-day session on every
device the victim had used. The tests that matter most here are therefore
the negative ones: that no response hands the token back to JavaScript, and
that the cookie carries the flags that make it unreadable.

The first half needs no database at all. The endpoint tests below need one;
see tests/conftest.py for running them without Docker.
"""

from http.cookies import SimpleCookie
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from app.config import settings
from app.core.csrf import assert_same_origin
from app.security import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    clear_refresh_cookie,
    set_refresh_cookie,
)

# Matches the default CORS_ORIGINS the test settings are built with.
APP_ORIGIN = "http://localhost"


def _set_cookie_attrs(response: Response) -> dict:
    jar = SimpleCookie()
    for header, value in response.raw_headers:
        if header.decode().lower() == "set-cookie":
            jar.load(value.decode())
    morsel = jar[REFRESH_COOKIE_NAME]
    return {"value": morsel.value, **{k: v for k, v in morsel.items() if v != ""}}


# --- cookie flags -----------------------------------------------------------

def test_refresh_cookie_is_not_readable_by_script():
    """httpOnly is the entire reason for this change. Without it the token is
    back in reach of any injected script and nothing has been gained."""
    response = Response()
    set_refresh_cookie(response, "token-value")
    assert _set_cookie_attrs(response)["httponly"] is True


def test_refresh_cookie_is_scoped_to_the_auth_path():
    """Scoping is most of the CSRF defence: the browser attaches the cookie
    to /auth/refresh and /auth/logout and to nothing else the API serves."""
    response = Response()
    set_refresh_cookie(response, "token-value")
    assert _set_cookie_attrs(response)["path"] == REFRESH_COOKIE_PATH == "/api/v1/auth"


def test_refresh_cookie_is_samesite_lax():
    """Lax blocks the cross-site POST that CSRF needs, while still surviving
    a pupil following a link into the app from a chat or an email -- which
    Strict would break."""
    response = Response()
    set_refresh_cookie(response, "token-value")
    assert _set_cookie_attrs(response)["samesite"].lower() == "lax"


def test_refresh_cookie_lives_as_long_as_the_session():
    response = Response()
    set_refresh_cookie(response, "token-value")
    expected = settings.jwt_refresh_ttl_days * 24 * 60 * 60
    assert int(_set_cookie_attrs(response)["max-age"]) == expected


def test_refresh_cookie_is_secure_in_production(monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    response = Response()
    set_refresh_cookie(response, "token-value")
    assert _set_cookie_attrs(response)["secure"] is True


def test_refresh_cookie_is_not_secure_in_development():
    """Not a relaxation to apologise for: a Secure cookie is dropped outright
    over plain http, so setting it unconditionally would break login on a
    developer's machine -- and the usual fix for that is to turn the flag off
    in production too."""
    assert settings.is_production is False
    response = Response()
    set_refresh_cookie(response, "token-value")
    assert "secure" not in _set_cookie_attrs(response)


def test_clearing_uses_the_same_path_it_was_set_with():
    """A delete-cookie on a different path deletes nothing, and the session
    would quietly outlive the logout that appeared to succeed."""
    response = Response()
    clear_refresh_cookie(response)
    attrs = _set_cookie_attrs(response)
    assert attrs["path"] == REFRESH_COOKIE_PATH
    assert attrs["value"] == ""


# --- origin check -----------------------------------------------------------

def _request(headers: dict):
    return SimpleNamespace(headers=headers)


def test_request_from_the_app_is_allowed():
    assert_same_origin(_request({"origin": APP_ORIGIN}))
    assert_same_origin(_request({"origin": "http://localhost:5173"}))


def test_request_from_another_site_is_refused():
    """The CSRF case: an attacker's page posting to /auth/refresh while the
    victim's cookie rides along."""
    with pytest.raises(HTTPException) as excinfo:
        assert_same_origin(_request({"origin": "https://evil.example"}))
    assert excinfo.value.status_code == 403


def test_lookalike_origin_is_refused():
    """Substring matching would accept this; the check compares whole
    origins."""
    with pytest.raises(HTTPException):
        assert_same_origin(_request({"origin": "http://localhost.evil.example"}))


def test_referer_is_used_only_when_origin_is_absent():
    assert_same_origin(_request({"referer": f"{APP_ORIGIN}/lessons/70"}))
    with pytest.raises(HTTPException):
        assert_same_origin(_request({"referer": "https://evil.example/page"}))


def test_origin_wins_over_referer():
    """A forged Referer must not talk its way past a hostile Origin."""
    with pytest.raises(HTTPException):
        assert_same_origin(
            _request({"origin": "https://evil.example", "referer": f"{APP_ORIGIN}/"})
        )


def test_request_with_no_origin_at_all_is_refused():
    """Browsers send Origin on every POST, so a request without one is not a
    browser doing normal work -- refused rather than trusted."""
    with pytest.raises(HTTPException):
        assert_same_origin(_request({}))
    with pytest.raises(HTTPException):
        assert_same_origin(_request({"origin": "null"}))


# --- endpoints (need a database) --------------------------------------------

PASSWORD = "correct-horse-battery"
ORIGIN_HEADER = {"Origin": APP_ORIGIN}


async def _login(client, user):
    return await client.post(
        "/api/v1/auth/login",
        json={"phone": user.phone, "password": PASSWORD},
        headers=ORIGIN_HEADER,
    )


async def test_login_returns_no_refresh_token_in_the_body(client, make_password_user):
    """The regression that matters. If this field ever comes back, the token
    is reachable from JavaScript again and everything else here is theatre."""
    user = await make_password_user(PASSWORD)
    response = await _login(client, user)

    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    assert set(response.json()) == {"access_token", "token_type"}


async def test_login_sets_the_refresh_cookie(client, make_password_user):
    user = await make_password_user(PASSWORD)
    response = await _login(client, user)

    assert REFRESH_COOKIE_NAME in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()


async def test_register_also_withholds_the_refresh_token(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": "+77015550001",
            "password": PASSWORD,
            "first_name": "Аян",
            "last_name": "Тест",
        },
        headers=ORIGIN_HEADER,
    )
    assert response.status_code == 201
    assert "refresh_token" not in response.json()
    assert REFRESH_COOKIE_NAME in response.cookies


async def test_refresh_works_from_the_cookie_alone(client, make_password_user):
    """No body, no header, nothing the page had to remember -- which is the
    point: the client cannot read this credential."""
    user = await make_password_user(PASSWORD)
    await _login(client, user)

    response = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" not in response.json()


async def test_refresh_rotates_and_retires_the_old_token(client, make_password_user):
    """A stolen cookie must not stay useful after the real user refreshes."""
    user = await make_password_user(PASSWORD)
    await _login(client, user)
    stolen = client.cookies[REFRESH_COOKIE_NAME]

    assert (await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)).status_code == 200
    assert client.cookies[REFRESH_COOKIE_NAME] != stolen

    client.cookies.set(REFRESH_COOKIE_NAME, stolen)
    replayed = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)
    assert replayed.status_code == 401


async def test_refresh_from_a_foreign_origin_is_refused(client, make_password_user):
    """Moving the credential into a cookie is what creates this exposure, so
    it gets its own end-to-end test rather than only a unit one."""
    user = await make_password_user(PASSWORD)
    await _login(client, user)

    response = await client.post(
        "/api/v1/auth/refresh", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    # The session survives: a refused cross-site request must not cost the
    # user the tab they had open.
    assert (await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)).status_code == 200


async def test_invalid_cookie_is_cleared_not_just_rejected(client):
    """Left in place, a stale cookie is replayed on every navigation for the
    next thirty days."""
    client.cookies.set(REFRESH_COOKIE_NAME, "not-a-real-token")
    response = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)

    assert response.status_code == 401
    # The delete has to ride on the error response itself. FastAPI throws away
    # the injected Response object the moment the handler raises, so setting
    # the cookie there and then raising would look right and do nothing.
    set_cookie = response.headers.get("set-cookie", "")
    assert REFRESH_COOKIE_NAME in set_cookie
    assert f"{REFRESH_COOKIE_NAME}=;" in set_cookie or f'{REFRESH_COOKIE_NAME}=""' in set_cookie


async def test_logout_revokes_the_session_server_side(client, make_password_user):
    """Clearing the cookie alone would leave a copied token working."""
    user = await make_password_user(PASSWORD)
    await _login(client, user)
    token = client.cookies[REFRESH_COOKIE_NAME]

    assert (await client.post("/api/v1/auth/logout", headers=ORIGIN_HEADER)).status_code == 204

    client.cookies.set(REFRESH_COOKIE_NAME, token)
    replayed = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)
    assert replayed.status_code == 401


async def test_logout_without_a_session_is_still_a_success(client):
    """The client cannot inspect an httpOnly cookie, so it cannot know
    whether there is anything to log out of."""
    assert (await client.post("/api/v1/auth/logout", headers=ORIGIN_HEADER)).status_code == 204


async def test_change_password_hands_back_a_working_session(client, make_password_user):
    """Every session dies on a password change, including the caller's, so
    the replacement cookie has to arrive in the same response."""
    user = await make_password_user(PASSWORD)
    login = await _login(client, user)
    access = login.json()["access_token"]

    response = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "a-different-password"},
        headers={"Authorization": f"Bearer {access}", **ORIGIN_HEADER},
    )

    assert response.status_code == 200
    assert "refresh_token" not in response.json()
    assert (await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)).status_code == 200


async def test_legacy_body_token_is_still_accepted(client, make_password_user):
    """Transitional. Sessions issued before the switch exist only in the old
    client's localStorage; refusing them would sign out every pupil and
    teacher at whatever moment they next opened the app.

    Delete this test together with LegacyRefreshIn.
    """
    from app.security import issue_refresh_token

    user = await make_password_user(PASSWORD)
    legacy = await issue_refresh_token(user.id)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": legacy}, headers=ORIGIN_HEADER
    )

    assert response.status_code == 200
    # ...and it comes back as a cookie, so this browser never needs the body
    # path again.
    assert REFRESH_COOKIE_NAME in response.cookies
