from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.category import Category
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CategoryOut]:
    categories = (await db.scalars(select(Category).where(Category.is_active.is_(True)))).all()

    status_by_category: dict[int, str] = {}
    if user.role == RoleEnum.student:
        applications = (
            await db.scalars(select(Application).where(Application.student_id == user.id))
        ).all()
        for app_ in applications:
            # Keep the most relevant status per category (an approved/rejected
            # decision takes precedence over an older pending row if re-applied).
            status_by_category[app_.category_id] = app_.status.value

    result = []
    for category in categories:
        out = CategoryOut.model_validate(category)
        out.my_application_status = status_by_category.get(category.id)
        result.append(out)
    return result


@router.get("/{category_id}", response_model=CategoryOut)
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CategoryOut:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    out = CategoryOut.model_validate(category)
    if user.role == RoleEnum.student:
        application = await db.scalar(
            select(Application)
            .where(Application.student_id == user.id, Application.category_id == category_id)
            .order_by(Application.created_at.desc())
        )
        if application is not None:
            out.my_application_status = application.status.value
    return out
