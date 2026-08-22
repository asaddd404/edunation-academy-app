from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import secrets
import string

from app.core.audit import audit_log
from app.core.category_stats import lesson_stats
from app.core.pagination import PageParams, fetch_page, page_params
from app.core.slug import slugify
from app.database import get_db
from app.deps import require_role
from app.models.category import Category, teacher_categories
from app.models.user import RoleEnum, User
from app.models.user_activity import UserDailyActivity
from app.schemas.category import AssignTeacherIn, CategoryAdminOut, CategoryIn, CategoryOut, CategoryUpdateIn
from app.schemas.pagination import Page
from app.schemas.user import PasswordResetOut, UserOut, UserUpdateIn
from app.security import hash_password, revoke_all_refresh_tokens

# Excludes visually-confusable characters (0/O, 1/l/I) -- this password is
# read off a screen and retyped by someone else, often over the phone.
_TEMP_PASSWORD_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(RoleEnum.admin))])


@router.get("/users", response_model=Page[UserOut])
async def list_users(
    role: RoleEnum | None = None,
    db: AsyncSession = Depends(get_db),
    params: PageParams = Depends(page_params),
) -> Page[UserOut]:
    query = select(User).order_by(User.created_at.desc(), User.id.desc())
    if role is not None:
        query = query.where(User.role == role)
    users, total = await fetch_page(db, query, params)

    today_seconds: dict[int, int] = {}
    if users:
        rows = await db.execute(
            select(UserDailyActivity.user_id, UserDailyActivity.total_seconds).where(
                UserDailyActivity.date == date.today(),
                UserDailyActivity.user_id.in_([u.id for u in users]),
            )
        )
        today_seconds = dict(rows.all())

    items = [
        UserOut.model_validate(u).model_copy(update={"today_activity_seconds": today_seconds.get(u.id, 0)})
        for u in users
    ]
    return Page.of(items, total, params.page, params.per_page)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    request: Request,
    user_id: int,
    payload: UserUpdateIn,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(RoleEnum.admin)),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    # An admin removing their own admin rights, or deactivating their own
    # account, can leave the installation with no way back in -- there is no
    # console tool to restore it. Blocked outright rather than warned about.
    if user.id == admin.id:
        if payload.role is not None and payload.role != user.role:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя изменить собственную роль")
        if payload.is_active is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя деактивировать собственную учётную запись")

    previous_role = user.role.value
    previous_active = user.is_active

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    await db.commit()
    await db.refresh(user)

    # Losing access is the point of a deactivation, so the sessions the
    # account already holds have to end with it -- otherwise a deactivated
    # user keeps working until their refresh token expires, up to 30 days.
    if previous_active and not user.is_active:
        await revoke_all_refresh_tokens(user.id)
    # A role change rewrites what the access token is allowed to do, and the
    # token carries the old role until it expires. Ending the sessions makes
    # the change take effect now rather than in fifteen minutes.
    if previous_role != user.role.value:
        await revoke_all_refresh_tokens(user.id)

    if previous_role != user.role.value or previous_active != user.is_active:
        audit_log(
            "admin.user.update",
            actor_id=admin.id,
            actor_role=admin.role.value,
            request=request,
            target_user_id=user.id,
            role_from=previous_role,
            role_to=user.role.value,
            active_from=previous_active,
            active_to=user.is_active,
        )

    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetOut)
async def reset_user_password(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(RoleEnum.admin)),
) -> PasswordResetOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    temporary_password = "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(10))
    user.password_hash = hash_password(temporary_password)
    await db.commit()

    # A password reset should end every session the old password was
    # logged into, not just stop working the next time it's typed.
    await revoke_all_refresh_tokens(user_id)

    audit_log(
        "admin.user.reset_password",
        actor_id=admin.id,
        actor_role=admin.role.value,
        request=request,
        target_user_id=user.id,
    )

    return PasswordResetOut(temporary_password=temporary_password)


@router.get("/categories", response_model=Page[CategoryAdminOut])
async def list_categories_for_admin(
    db: AsyncSession = Depends(get_db),
    params: PageParams = Depends(page_params),
) -> Page[CategoryAdminOut]:
    query = (
        select(Category)
        .options(selectinload(Category.teachers))
        .order_by(Category.created_at.desc(), Category.id.desc())
    )
    categories, total = await fetch_page(db, query, params)

    stats = await lesson_stats(db, [c.id for c in categories])
    result = []
    for category in categories:
        out = CategoryAdminOut.model_validate(category)
        out.lesson_count, out.total_duration_seconds = stats.get(category.id, (0, 0))
        result.append(out)
    return Page.of(result, total, params.page, params.per_page)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryIn, db: AsyncSession = Depends(get_db)) -> CategoryOut:
    slug = payload.slug.strip() if payload.slug else slugify(payload.name)

    existing = await db.scalar(select(Category).where(Category.slug == slug))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Категория с таким slug уже существует")

    category = Category(name=payload.name, slug=slug, description=payload.description)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return CategoryOut.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int, payload: CategoryUpdateIn, db: AsyncSession = Depends(get_db)
) -> CategoryOut:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    if payload.name is not None:
        category.name = payload.name
    if payload.description is not None:
        category.description = payload.description
    if payload.is_active is not None:
        category.is_active = payload.is_active

    await db.commit()
    await db.refresh(category)
    return CategoryOut.model_validate(category)


@router.post("/categories/{category_id}/assign-teacher", status_code=status.HTTP_204_NO_CONTENT)
async def assign_teacher(category_id: int, payload: AssignTeacherIn, db: AsyncSession = Depends(get_db)) -> None:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    teacher = await db.get(User, payload.teacher_id)
    if teacher is None or teacher.role != RoleEnum.teacher:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не является учителем")

    existing = await db.execute(
        select(teacher_categories).where(
            teacher_categories.c.teacher_id == teacher.id,
            teacher_categories.c.category_id == category.id,
        )
    )
    if existing.first() is not None:
        return

    await db.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    await db.commit()


@router.delete("/categories/{category_id}/teachers/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_teacher(category_id: int, teacher_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await db.execute(
        teacher_categories.delete().where(
            teacher_categories.c.teacher_id == teacher_id,
            teacher_categories.c.category_id == category_id,
        )
    )
    await db.commit()
