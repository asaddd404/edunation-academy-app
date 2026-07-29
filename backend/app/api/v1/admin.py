from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.slug import slugify
from app.database import get_db
from app.deps import require_role
from app.models.category import Category, teacher_categories
from app.models.user import RoleEnum, User
from app.schemas.category import AssignTeacherIn, CategoryAdminOut, CategoryIn, CategoryOut, CategoryUpdateIn
from app.schemas.user import UserOut, UserUpdateIn

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(RoleEnum.admin))])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    role: RoleEnum | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    query = select(User).order_by(User.created_at.desc())
    if role is not None:
        query = query.where(User.role == role)
    users = (await db.scalars(query)).all()
    return [UserOut.model_validate(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, payload: UserUpdateIn, db: AsyncSession = Depends(get_db)) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/categories", response_model=list[CategoryAdminOut])
async def list_categories_for_admin(db: AsyncSession = Depends(get_db)) -> list[CategoryAdminOut]:
    categories = (
        await db.scalars(
            select(Category).options(selectinload(Category.teachers)).order_by(Category.created_at.desc())
        )
    ).all()
    return [CategoryAdminOut.model_validate(c) for c in categories]


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
