from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_can_decide_application
from app.core.notifications import notify
from app.core.pagination import PageParams, fetch_page, page_params
from app.database import get_db
from app.deps import require_role
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.user import RoleEnum, User
from app.schemas.application import ApplicationCreateIn, ApplicationOut
from app.schemas.pagination import Page

router = APIRouter(prefix="/applications", tags=["applications"])


def _serialize(application: Application, *, with_student: bool = False, with_category: bool = False) -> ApplicationOut:
    """Builds the response DTO. Only touches application.student/.category when
    the caller guarantees they were eager-loaded (selectinload) on the query
    that produced this object — otherwise SQLAlchemy would attempt a lazy
    load outside of an awaited context and raise MissingGreenlet."""
    out = ApplicationOut.model_validate(application)
    if with_student:
        out.student_name = f"{application.student.first_name} {application.student.last_name}"
        out.student_phone = application.student.phone
    if with_category:
        out.category_name = application.category.name
    return out


async def _get_application_or_404(db: AsyncSession, application_id: int) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    return application


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreateIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> ApplicationOut:
    existing = await db.scalar(
        select(Application).where(
            Application.student_id == student.id,
            Application.category_id == payload.category_id,
            Application.status == ApplicationStatusEnum.pending,
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Заявка на эту категорию уже подана и ожидает решения")

    category = await db.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    application = Application(student_id=student.id, category_id=payload.category_id)
    db.add(application)

    teacher_ids = (
        await db.scalars(
            select(teacher_categories.c.teacher_id).where(teacher_categories.c.category_id == payload.category_id)
        )
    ).all()
    for teacher_id in teacher_ids:
        notify(
            db,
            teacher_id,
            "new_application",
            f"Новая заявка от {student.first_name} {student.last_name} на курс «{category.name}»",
            link="/teacher",
        )

    await db.commit()
    await db.refresh(application)
    return ApplicationOut.model_validate(application)


@router.get("/me", response_model=Page[ApplicationOut])
async def list_my_applications(
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
    params: PageParams = Depends(page_params),
) -> Page[ApplicationOut]:
    query = (
        select(Application)
        .where(Application.student_id == student.id)
        .options(selectinload(Application.category))
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    applications, total = await fetch_page(db, query, params)
    return Page.of(
        [_serialize(a, with_category=True) for a in applications], total, params.page, params.per_page
    )


@router.get("/pending", response_model=Page[ApplicationOut])
async def list_pending_for_teacher(
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
    params: PageParams = Depends(page_params),
) -> Page[ApplicationOut]:
    query = select(Application).where(Application.status == ApplicationStatusEnum.pending)
    if teacher.role != RoleEnum.admin:
        query = query.join(teacher_categories, teacher_categories.c.category_id == Application.category_id).where(
            teacher_categories.c.teacher_id == teacher.id
        )
    query = query.options(selectinload(Application.student), selectinload(Application.category)).order_by(
        Application.created_at.asc(), Application.id.asc()
    )
    applications, total = await fetch_page(db, query, params)
    return Page.of(
        [_serialize(a, with_student=True, with_category=True) for a in applications], total, params.page, params.per_page
    )


@router.post("/{application_id}/approve", response_model=ApplicationOut)
async def approve_application(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> ApplicationOut:
    application = await _get_application_or_404(db, application_id)
    await assert_can_decide_application(db, teacher, application)

    application.status = ApplicationStatusEnum.approved
    application.decided_by = teacher.id
    application.decided_at = datetime.now(timezone.utc)

    category_name = await db.scalar(select(Category.name).where(Category.id == application.category_id))
    notify(
        db,
        application.student_id,
        "application_approved",
        f"Заявка на курс «{category_name}» одобрена",
        link="/my-applications",
    )

    await db.commit()
    await db.refresh(application)
    return ApplicationOut.model_validate(application)


@router.post("/{application_id}/reject", response_model=ApplicationOut)
async def reject_application(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> ApplicationOut:
    application = await _get_application_or_404(db, application_id)
    await assert_can_decide_application(db, teacher, application)

    application.status = ApplicationStatusEnum.rejected
    application.decided_by = teacher.id
    application.decided_at = datetime.now(timezone.utc)

    category_name = await db.scalar(select(Category.name).where(Category.id == application.category_id))
    notify(
        db,
        application.student_id,
        "application_rejected",
        f"Заявка на курс «{category_name}» отклонена",
        link="/my-applications",
    )

    await db.commit()
    await db.refresh(application)
    return ApplicationOut.model_validate(application)


@router.get("", response_model=Page[ApplicationOut])
async def list_all_applications(
    status_filter: ApplicationStatusEnum | None = Query(default=None, alias="status"),
    category_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(RoleEnum.admin)),
    params: PageParams = Depends(page_params),
) -> Page[ApplicationOut]:
    query = (
        select(Application)
        .options(selectinload(Application.student), selectinload(Application.category))
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    if status_filter is not None:
        query = query.where(Application.status == status_filter)
    if category_id is not None:
        query = query.where(Application.category_id == category_id)

    applications, total = await fetch_page(db, query, params)
    return Page.of(
        [_serialize(a, with_student=True, with_category=True) for a in applications], total, params.page, params.per_page
    )
