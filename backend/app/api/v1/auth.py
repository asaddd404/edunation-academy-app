from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csrf import assert_same_origin
from app.core.rate_limit import (
    CHANGE_PASSWORD_BY_USER,
    LOGIN_BY_ACCOUNT,
    LOGIN_BY_IP,
    REFRESH_BY_IP,
    REGISTER_BY_IP,
    request_ip,
)
from app.database import get_db
from app.deps import get_current_user
from app.models.user import RoleEnum, User
from app.schemas.auth import (
    AccessTokenOut,
    AuthResponse,
    ChangePasswordIn,
    LegacyRefreshIn,
    LoginIn,
    RegisterIn,
)
from app.schemas.user import UserOut
from app.security import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    consume_refresh_token,
    create_access_token,
    hash_password,
    issue_refresh_token,
    refresh_cookie_clear_header,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    set_refresh_cookie,
    verify_password,
    verify_password_dummy,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_session(response: Response, user: User) -> str:
    """Starts a session: the refresh token goes to the browser as an httpOnly
    cookie, and only the short-lived access token is returned to JavaScript.

    Every path that signs someone in goes through here, so there is one place
    where the split is decided rather than four that have to agree."""
    refresh_token = await issue_refresh_token(user.id)
    set_refresh_cookie(response, refresh_token)
    return create_access_token(user.id, user.role.value)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    payload: RegisterIn,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    await REGISTER_BY_IP.enforce(request_ip(request))

    existing = await db.scalar(select(User).where(User.phone == payload.phone))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким номером уже зарегистрирован")

    user = User(
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=RoleEnum.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = await _issue_session(response, user)
    return AuthResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/login", response_model=AccessTokenOut)
async def login(
    request: Request,
    response: Response,
    payload: LoginIn,
    db: AsyncSession = Depends(get_db),
) -> AccessTokenOut:
    """Both limits are deliberate and asymmetric.

    The strict one is keyed on the phone number, because guessing a password
    is an attack on an *account*: keying it on the address instead would lock
    out a whole school computer lab, which shares one external IP, the moment
    a few pupils fumbled their passwords. The IP limit is loose and only
    catches someone spraying one password across many accounts.
    """
    await LOGIN_BY_IP.enforce(request_ip(request))
    await LOGIN_BY_ACCOUNT.enforce(payload.phone)

    user = await db.scalar(select(User).where(User.phone == payload.phone))
    if user is None or not user.is_active:
        # Same message, same status, and the same argon2 cost as a real
        # check -- otherwise the response time alone says whether the
        # account exists.
        verify_password_dummy()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный номер телефона или пароль")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный номер телефона или пароль")

    # A successful sign-in clears the window: a pupil who mistyped twice and
    # then got in shouldn't carry those attempts into the rest of the lesson.
    await LOGIN_BY_ACCOUNT.reset(payload.phone)

    access_token = await _issue_session(response, user)
    return AccessTokenOut(access_token=access_token)


@router.post("/refresh", response_model=AccessTokenOut)
async def refresh(
    request: Request,
    response: Response,
    payload: LegacyRefreshIn | None = None,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> AccessTokenOut:
    """Trades a refresh token for a new access token, rotating both.

    The token comes from the cookie. It is not readable by script, which is
    the point, so this endpoint has nothing but the cookie to authenticate
    with -- and that is exactly what makes it the one place CSRF could reach.
    Hence the origin check; see app.core.csrf for why it is an origin check
    and not a token.
    """
    await REFRESH_BY_IP.enforce(request_ip(request))
    assert_same_origin(request)

    # Transitional: a session issued before the cookie switch exists only in
    # the old client's localStorage, and this is the one request that can
    # convert it. Remove with LegacyRefreshIn once the migrating frontend has
    # been live for a release.
    token = refresh_cookie or (payload.refresh_token if payload else None)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия не найдена")

    user_id = await consume_refresh_token(token)
    if user_id is None:
        # The cookie is stale or forged; taking it back stops the browser
        # replaying it on every navigation for the next thirty days. The
        # header goes on the exception rather than on `response`, which
        # FastAPI discards as soon as this handler raises.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Недействительный refresh-токен",
            headers=refresh_cookie_clear_header(),
        )

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Пользователь не найден или деактивирован",
            headers=refresh_cookie_clear_header(),
        )

    access_token = await _issue_session(response, user)
    return AccessTokenOut(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> None:
    """Ends the session on the server and takes the cookie back.

    Deliberately idempotent: logging out with no cookie, or with one the
    server has already forgotten, is a success. The client has no way to
    inspect the cookie first, and an error here would only ever be reported
    to someone who is already leaving.
    """
    assert_same_origin(request)

    if refresh_cookie:
        await revoke_refresh_token(refresh_cookie)
    clear_refresh_cookie(response)


@router.post("/change-password", response_model=AccessTokenOut)
async def change_password(
    payload: ChangePasswordIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AccessTokenOut:
    await CHANGE_PASSWORD_BY_USER.enforce(str(user.id))

    # 400 rather than 401: a 401 here would send the frontend's axios
    # interceptor off to refresh the session over a simple typo.
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль указан неверно")
    if payload.old_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Новый пароль совпадает с текущим")

    user.password_hash = hash_password(payload.new_password)
    await db.commit()

    # Someone changing their password may be locking an intruder out, so every
    # existing session dies -- including this one, which is immediately handed
    # a fresh cookie so the caller stays signed in.
    #
    # No origin check here, and none needed: this endpoint authenticates with
    # the bearer header, which a cross-site page cannot set.
    await revoke_all_refresh_tokens(user.id)
    access_token = await _issue_session(response, user)
    return AccessTokenOut(access_token=access_token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
