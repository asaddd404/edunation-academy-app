from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.schemas.auth import AuthResponse, ChangePasswordIn, LoginIn, RefreshIn, RegisterIn, TokenPair
from app.schemas.user import UserOut
from app.security import (
    consume_refresh_token,
    create_access_token,
    hash_password,
    issue_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    verify_password,
    verify_password_dummy,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, payload: RegisterIn, db: AsyncSession = Depends(get_db)) -> AuthResponse:
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

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = await issue_refresh_token(user.id)
    return AuthResponse(access_token=access_token, refresh_token=refresh_token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenPair)
async def login(request: Request, payload: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenPair:
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

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = await issue_refresh_token(user.id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(request: Request, payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> TokenPair:
    await REFRESH_BY_IP.enforce(request_ip(request))

    user_id = await consume_refresh_token(payload.refresh_token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный refresh-токен")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или деактивирован")

    access_token = create_access_token(user.id, user.role.value)
    new_refresh_token = await issue_refresh_token(user.id)
    return TokenPair(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshIn) -> None:
    await revoke_refresh_token(payload.refresh_token)


@router.post("/change-password", response_model=TokenPair)
async def change_password(
    payload: ChangePasswordIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TokenPair:
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
    # a fresh pair so the caller stays signed in.
    await revoke_all_refresh_tokens(user.id)
    access_token = create_access_token(user.id, user.role.value)
    refresh_token = await issue_refresh_token(user.id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
