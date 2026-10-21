from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.category_stats import lesson_stats
from app.core.pagination import PageParams, fetch_page, page_params
from app.core.storage import image_response, resolve_upload_path
from app.database import get_db
from app.deps import get_current_user
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut
from app.schemas.pagination import Page

router = APIRouter(prefix="/categories", tags=["categories"])

# Which of a student's applications to a category speaks for it. Approved
# wins outright -- the access check only asks whether *any* approved row
# exists, so showing "rejected" or "pending" next to it would lock the
# catalog UI out of a course the API serves. Rows arrive in no particular
# order, so this has to be decided, not left to whichever came last.
_STATUS_PRIORITY = {
    ApplicationStatusEnum.approved.value: 3,
    ApplicationStatusEnum.pending.value: 2,
    ApplicationStatusEnum.rejected.value: 1,
}


def _most_relevant(current: str | None, candidate: str) -> str:
    if current is None or _STATUS_PRIORITY[candidate] > _STATUS_PRIORITY[current]:
        return candidate
    return current


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
        for app_ in applications:
            status_by_category[app_.category_id] = _most_relevant(
                status_by_category.get(app_.category_id), app_.status.value
            )

    stats = await lesson_stats(db, [c.id for c in categories])

    result = []
    for category in categories:
        out = CategoryOut.model_validate(category)
        status_value = status_by_category.get(category.id)
        out.my_application_status = ApplicationStatusEnum(status_value) if status_value else None
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
    # A deactivated course is hidden from students, as in the listing above;
    # staff still see it so they can manage it.
    if category is None or (not category.is_active and user.role == RoleEnum.student):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    out = CategoryOut.model_validate(category)
    if user.role == RoleEnum.student:
        statuses = (
            await db.scalars(
                select(Application.status).where(
                    Application.student_id == user.id, Application.category_id == category_id
                )
            )
        ).all()
        best: str | None = None
        for status_ in statuses:
            best = _most_relevant(best, status_.value)
        out.my_application_status = ApplicationStatusEnum(best) if best else None

    stats = await lesson_stats(db, [category_id])
    out.lesson_count, out.total_duration_seconds = stats.get(category_id, (0, 0))
    return out
