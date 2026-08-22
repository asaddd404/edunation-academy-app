from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import resolve_upload_path, save_avatar_image
from app.core.rate_limit import UPLOAD_BY_USER
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.user import ProfileUpdateIn, UserOut

router = APIRouter(tags=["profile"])


@router.patch("/me", response_model=UserOut)
async def update_my_profile(
    payload: ProfileUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    if payload.phone is not None and payload.phone != user.phone:
        existing = await db.scalar(select(User).where(User.phone == payload.phone, User.id != user.id))
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Этот номер телефона уже занят")
        user.phone = payload.phone

    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/me/avatar", response_model=UserOut)
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    await UPLOAD_BY_USER.enforce(str(user.id))

    old_path = user.avatar_path
    user.avatar_path = await save_avatar_image(file)
    await db.commit()
    await db.refresh(user)
    if old_path:
        resolve_upload_path(old_path).unlink(missing_ok=True)
    return UserOut.model_validate(user)


@router.delete("/me/avatar", response_model=UserOut)
async def delete_my_avatar(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    if user.avatar_path:
        resolve_upload_path(user.avatar_path).unlink(missing_ok=True)
        user.avatar_path = None
        await db.commit()
        await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/users/{user_id}/avatar")
async def get_user_avatar(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    # Public and unauthenticated on purpose, like the category cover image
    # route: a plain <img src> can't attach the app's bearer token.
    user = await db.get(User, user_id)
    if user is None or not user.avatar_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аватар не найден")

    path = resolve_upload_path(user.avatar_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аватар не найден")
    return FileResponse(path)
