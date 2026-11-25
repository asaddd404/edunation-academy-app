from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.category_stats import lesson_stats
from app.core.pagination import PageParams, fetch_page, page_params
from app.core.storage import image_response, resolve_upload_path
from app.database import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.category import Category
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut
from app.schemas.pagination import Page

router = APIRouter(prefix="/categories", tags=["categories"])


# Which status the catalog shows when a student has several applications to
# one course (re-applied after a rejection, say): access granted beats one
# still waiting, which beats a refusal.
_STATUS_RANK = {"approved": 3, "pending": 2, "rejected": 1}


def _best_status(applications) -> dict[int, str]:
    best: dict[int, str] = {}
    for app_ in applications:
        value = app_.status.value
        if _STATUS_RANK.get(value, 0) > _STATUS_RANK.get(best.get(app_.category_id, ""), 0):
            best[app_.category_id] = value
    return best


@router.get("", response_model=Page[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    params: PageParams = Depends(page_params),
) -> Page[CategoryOut]:
    query = select(Category).where(Category.is_active.is_(True)).order_by(Category.name, Category.id)
    categories, total = await fetch_page(db, query, params)

    status_by_category: dict[int, str] = {}
    if user.role == RoleEnum.student:
        applications = (
            await db.scalars(select(Application).where(Application.student_id == user.id))
        ).all()
        status_by_category = _best_status(applications)

    stats = await lesson_stats(db, [c.id for c in categories])

    result = []
    for category in categories:
        out = CategoryOut.model_validate(category)
        out.my_application_status = status_by_category.get(category.id)
        out.lesson_count, out.total_duration_seconds = stats.get(category.id, (0, 0))
        result.append(out)
    return Page.of(result, total, params.page, params.per_page)


@router.get("/{category_id}/image")
async def get_category_image(
    category_id: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    # Public and unauthenticated on purpose: it's a decorative cover image,
    # and a plain <img src> can't attach the app's bearer token the way
    # axios does for every other request.
    category = await db.get(Category, category_id)
    if category is None or not category.image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")

    path = resolve_upload_path(category.image_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")
    return image_response(path)


@router.get("/{category_id}", response_model=CategoryOut)
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CategoryOut:
    category = await db.get(Category, category_id)
    # A switched-off course is gone from a student's point of view, the same
    # as it is gone from the catalog list.
    if category is None or (user.role == RoleEnum.student and not category.is_active):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    out = CategoryOut.model_validate(category)
    if user.role == RoleEnum.student:
        applications = (
            await db.scalars(
                select(Application).where(Application.student_id == user.id, Application.category_id == category_id)
            )
        ).all()
        out.my_application_status = _best_status(applications).get(category_id)

    stats = await lesson_stats(db, [category_id])
    out.lesson_count, out.total_duration_seconds = stats.get(category_id, (0, 0))
    return out
