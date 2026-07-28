from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import RoleEnum, User
from app.schemas.auth import AuthResponse, LoginIn, RefreshIn, RegisterIn, TokenPair
from app.schemas.user import UserOut
from app.security import (
    consume_refresh_token,
    create_access_token,
    hash_password,
    issue_refresh_token,
    revoke_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)) -> AuthResponse:
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
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await db.scalar(select(User).where(User.phone == payload.phone))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный номер телефона или пароль")

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = await issue_refresh_token(user.id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> TokenPair:
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


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
