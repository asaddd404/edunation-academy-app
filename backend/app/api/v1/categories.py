from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import resolve_upload_path
from app.database import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.category import Category
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


async def _lesson_stats(db: AsyncSession, category_ids: list[int]) -> dict[int, tuple[int, int]]:
    """category_id -> (lesson_count, total_video_duration_seconds), real counts from Section/Lesson."""
    if not category_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Section.category_id,
                func.count(Lesson.id),
                func.coalesce(func.sum(Lesson.video_duration_seconds), 0),
            )
            .join(Lesson, Lesson.section_id == Section.id)
            .where(Section.category_id.in_(category_ids))
            .group_by(Section.category_id)
        )
    ).all()
    return {row[0]: (row[1], int(row[2])) for row in rows}


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

    stats = await _lesson_stats(db, [c.id for c in categories])

    result = []
    for category in categories:
        out = CategoryOut.model_validate(category)
        out.my_application_status = status_by_category.get(category.id)
        out.lesson_count, out.total_duration_seconds = stats.get(category.id, (0, 0))
        result.append(out)
    return result


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
    return FileResponse(path)


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

    stats = await _lesson_stats(db, [category_id])
    out.lesson_count, out.total_duration_seconds = stats.get(category_id, (0, 0))
    return out
