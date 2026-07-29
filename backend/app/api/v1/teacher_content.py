import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_teacher_owns_category, assert_teacher_owns_lesson, assert_teacher_owns_section
from app.core.video import VideoProcessingError, delete_video_assets, save_raw_video, transcode_to_hls
from app.database import async_session_factory, get_db
from app.deps import require_role
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson, VideoStatusEnum
from app.models.question import Choice, Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut, TeacherCategoryUpdateIn
from app.schemas.lesson import LessonIn, LessonTeacherOut, LessonUpdateIn, VideoTicketOut
from app.schemas.question import QuestionIn, QuestionTeacherOut
from app.schemas.section import SectionIn, SectionOut, SectionUpdateIn
from app.security import set_video_ticket_cookie

logger = logging.getLogger(__name__)

router = APIRouter(tags=["teacher-content"], dependencies=[Depends(require_role(RoleEnum.teacher, RoleEnum.admin))])


@router.get("/teacher/categories", response_model=list[CategoryOut])
async def list_my_categories(
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[CategoryOut]:
    query = select(Category)
    if teacher.role != RoleEnum.admin:
        query = query.join(teacher_categories, teacher_categories.c.category_id == Category.id).where(
            teacher_categories.c.teacher_id == teacher.id
        )
    categories = (await db.scalars(query)).all()
    return [CategoryOut.model_validate(c) for c in categories]


@router.get("/teacher/categories/{category_id}", response_model=CategoryOut)
async def get_teacher_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> CategoryOut:
    await assert_teacher_owns_category(db, teacher, category_id)
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")
    return CategoryOut.model_validate(category)


@router.patch("/teacher/categories/{category_id}", response_model=CategoryOut)
async def update_teacher_category(
    category_id: int,
    payload: TeacherCategoryUpdateIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> CategoryOut:
    await assert_teacher_owns_category(db, teacher, category_id)
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    if payload.description is not None:
        category.description = payload.description

    await db.commit()
    await db.refresh(category)
    return CategoryOut.model_validate(category)


@router.get("/teacher/categories/{category_id}/sections", response_model=list[SectionOut])
async def list_category_sections(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[SectionOut]:
    await assert_teacher_owns_category(db, teacher, category_id)

    sections = (
        await db.scalars(
            select(Section)
            .where(Section.category_id == category_id)
            .options(selectinload(Section.lessons))
            .order_by(Section.order_index)
        )
    ).all()
    return [SectionOut.model_validate(s) for s in sections]


@router.post("/teacher/categories/{category_id}/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
async def create_section(
    category_id: int,
    payload: SectionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> SectionOut:
    await assert_teacher_owns_category(db, teacher, category_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Section.order_index), -1) + 1).where(Section.category_id == category_id))
    )
    section = Section(category_id=category_id, title=payload.title, description=payload.description, order_index=next_order)
    db.add(section)
    await db.commit()
    await db.refresh(section)
    # A brand-new section has no lessons yet -- set this explicitly rather
    # than letting SectionOut.model_validate touch the unloaded relationship,
    # which would trigger a lazy load outside an awaited context.
    section.lessons = []
    return SectionOut.model_validate(section)


@router.patch("/teacher/sections/{section_id}", response_model=SectionOut)
async def update_section(
    section_id: int,
    payload: SectionUpdateIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> SectionOut:
    await assert_teacher_owns_section(db, teacher, section_id)
    section = await db.get(Section, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")

    if payload.title is not None:
        section.title = payload.title
    if payload.description is not None:
        section.description = payload.description
    await db.commit()

    # Re-fetch with lessons eager-loaded rather than db.refresh(), which
    # would expire the relationship and force an unsafe lazy load in
    # SectionOut.model_validate.
    section = await db.scalar(
        select(Section).where(Section.id == section_id).options(selectinload(Section.lessons))
    )
    return SectionOut.model_validate(section)


@router.delete("/teacher/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    section_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> None:
    await assert_teacher_owns_section(db, teacher, section_id)
    section = await db.get(Section, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")

    # The DB cascade-deletes lesson/question rows, but not the on-disk HLS
    # files for any lesson videos -- clean those up ourselves afterward.
    lesson_ids = (await db.scalars(select(Lesson.id).where(Lesson.section_id == section_id))).all()
    await db.delete(section)
    await db.commit()
    for lesson_id in lesson_ids:
        delete_video_assets(lesson_id)


@router.post("/teacher/sections/{section_id}/lessons", response_model=LessonTeacherOut, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    section_id: int,
    payload: LessonIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonTeacherOut:
    await assert_teacher_owns_section(db, teacher, section_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Lesson.order_index), -1) + 1).where(Lesson.section_id == section_id))
    )
    lesson = Lesson(
        section_id=section_id,
        title=payload.title,
        description=payload.description,
        video_url=payload.video_url,
        homework_assignment=payload.homework_assignment,
        order_index=next_order,
    )
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    return LessonTeacherOut.model_validate(lesson)


@router.patch("/teacher/lessons/{lesson_id}", response_model=LessonTeacherOut)
async def update_lesson(
    lesson_id: int,
    payload: LessonUpdateIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonTeacherOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")

    if payload.title is not None:
        lesson.title = payload.title
    if payload.description is not None:
        lesson.description = payload.description
    if payload.homework_assignment is not None:
        lesson.homework_assignment = payload.homework_assignment
    await db.commit()
    await db.refresh(lesson)
    return LessonTeacherOut.model_validate(lesson)


@router.delete("/teacher/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> None:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")

    await db.delete(lesson)
    await db.commit()
    delete_video_assets(lesson_id)


@router.get("/teacher/lessons/{lesson_id}", response_model=LessonTeacherOut)
async def get_teacher_lesson(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonTeacherOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")
    return LessonTeacherOut.model_validate(lesson)


async def _run_video_processing(lesson_id: int, raw_path: Path) -> None:
    """Runs after the upload response has been sent. Owns its own DB session
    since the request-scoped one is already closed by the time this fires."""
    async with async_session_factory() as db:
        lesson = await db.get(Lesson, lesson_id)
        if lesson is None:
            return
        try:
            duration = await transcode_to_hls(lesson_id, raw_path)
        except VideoProcessingError as exc:
            logger.warning("Video transcode failed for lesson %s: %s", lesson_id, exc)
            lesson.video_status = VideoStatusEnum.failed
            lesson.video_error = str(exc)[:2000]
        else:
            lesson.video_status = VideoStatusEnum.ready
            lesson.video_duration_seconds = duration
            lesson.video_error = None
        finally:
            raw_path.unlink(missing_ok=True)
        await db.commit()


@router.post("/teacher/lessons/{lesson_id}/video", response_model=LessonTeacherOut)
async def upload_lesson_video(
    lesson_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonTeacherOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")

    raw_path = await save_raw_video(lesson_id, file)

    lesson.video_status = VideoStatusEnum.processing
    lesson.video_error = None
    lesson.video_duration_seconds = None
    await db.commit()
    await db.refresh(lesson)

    background_tasks.add_task(_run_video_processing, lesson_id, raw_path)
    return LessonTeacherOut.model_validate(lesson)


@router.delete("/teacher/lessons/{lesson_id}/video", response_model=LessonTeacherOut)
async def delete_lesson_video(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonTeacherOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")

    delete_video_assets(lesson_id)
    lesson.video_status = VideoStatusEnum.none
    lesson.video_duration_seconds = None
    lesson.video_error = None
    await db.commit()
    await db.refresh(lesson)
    return LessonTeacherOut.model_validate(lesson)


@router.post("/teacher/lessons/{lesson_id}/video/ticket", response_model=VideoTicketOut)
async def get_teacher_video_ticket(
    lesson_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> VideoTicketOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None or lesson.video_status != VideoStatusEnum.ready:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Видео ещё не готово")

    set_video_ticket_cookie(response, lesson_id)
    return VideoTicketOut(playback_path=f"/video/lessons/{lesson_id}/master.m3u8")


@router.post("/teacher/lessons/{lesson_id}/questions", response_model=QuestionTeacherOut, status_code=status.HTTP_201_CREATED)
async def create_question(
    lesson_id: int,
    payload: QuestionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> QuestionTeacherOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Question.order_index), -1) + 1).where(Question.lesson_id == lesson_id))
    )
    question = Question(lesson_id=lesson_id, text=payload.text, order_index=next_order)
    question.choices = [
        Choice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(payload.choices)
    ]
    db.add(question)
    await db.commit()

    question = await db.scalar(
        select(Question).where(Question.id == question.id).options(selectinload(Question.choices))
    )
    return QuestionTeacherOut.model_validate(question)


@router.post("/teacher/sections/{section_id}/questions", response_model=QuestionTeacherOut, status_code=status.HTTP_201_CREATED)
async def create_section_question(
    section_id: int,
    payload: QuestionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> QuestionTeacherOut:
    await assert_teacher_owns_section(db, teacher, section_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Question.order_index), -1) + 1).where(Question.section_id == section_id))
    )
    question = Question(section_id=section_id, text=payload.text, order_index=next_order)
    question.choices = [
        Choice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(payload.choices)
    ]
    db.add(question)
    await db.commit()

    question = await db.scalar(
        select(Question).where(Question.id == question.id).options(selectinload(Question.choices))
    )
    return QuestionTeacherOut.model_validate(question)
