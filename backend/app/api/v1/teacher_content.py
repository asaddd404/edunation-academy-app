import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import (
    assert_teacher_owns_category,
    assert_teacher_owns_lesson,
    assert_teacher_owns_question,
    assert_teacher_owns_section,
)
from app.core.rich_content import extract_image_paths, orphaned_image_paths
from app.core.storage import delete_upload, resolve_upload_path, save_category_image, save_lesson_content_image
from app.core.video import VideoProcessingError, delete_video_assets, save_raw_video, transcode_to_hls
from app.database import async_session_factory, get_db
from app.deps import require_role
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson, VideoStatusEnum
from app.models.question import AnswerVariant, Choice, MatchPair, Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut, TeacherCategoryUpdateIn
from app.schemas.lesson import (
    LessonContentImageOut,
    LessonIn,
    LessonTeacherOut,
    LessonUpdateIn,
    VideoTicketOut,
)
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


@router.post("/teacher/categories/{category_id}/image", response_model=CategoryOut)
async def upload_category_image(
    category_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> CategoryOut:
    await assert_teacher_owns_category(db, teacher, category_id)
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    old_path = category.image_path
    category.image_path = await save_category_image(file)
    await db.commit()
    await db.refresh(category)
    if old_path:
        resolve_upload_path(old_path).unlink(missing_ok=True)
    return CategoryOut.model_validate(category)


@router.delete("/teacher/categories/{category_id}/image", response_model=CategoryOut)
async def delete_category_image(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> CategoryOut:
    await assert_teacher_owns_category(db, teacher, category_id)
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Категория не найдена")

    if category.image_path:
        resolve_upload_path(category.image_path).unlink(missing_ok=True)
        category.image_path = None
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
    # files for any lesson videos, nor the images embedded in lesson bodies --
    # clean both up ourselves afterward.
    rows = (
        await db.execute(
            select(Lesson.id, Lesson.description, Lesson.homework_assignment).where(
                Lesson.section_id == section_id
            )
        )
    ).all()
    lesson_ids = [row.id for row in rows]
    images: set[str] = set()
    for row in rows:
        images |= extract_image_paths(row.description) | extract_image_paths(row.homework_assignment)

    await db.delete(section)
    await db.commit()
    for lesson_id in lesson_ids:
        delete_video_assets(lesson_id)
    for path in images:
        delete_upload(path)


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

    # Collected before the fields are overwritten: an image the teacher just
    # deleted from the text would otherwise sit on disk forever.
    dropped_images: set[str] = set()

    if payload.title is not None:
        lesson.title = payload.title
    if payload.description is not None:
        dropped_images |= orphaned_image_paths(lesson.description, payload.description)
        lesson.description = payload.description
    if payload.homework_assignment is not None:
        dropped_images |= orphaned_image_paths(lesson.homework_assignment, payload.homework_assignment)
        lesson.homework_assignment = payload.homework_assignment
    await db.commit()
    await db.refresh(lesson)

    # Only after the commit -- if the write failed, the rows still reference
    # these files and deleting them would leave broken images behind.
    for path in dropped_images:
        delete_upload(path)

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

    images = extract_image_paths(lesson.description) | extract_image_paths(lesson.homework_assignment)

    await db.delete(lesson)
    await db.commit()
    delete_video_assets(lesson_id)
    for path in images:
        delete_upload(path)


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


@router.post("/teacher/lesson-content/image", response_model=LessonContentImageOut)
async def upload_lesson_content_image(
    file: UploadFile = File(...),
    _teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonContentImageOut:
    """Stores an image for embedding in a lesson's rich description/homework.

    Deliberately not scoped to a lesson id: the teacher can be composing a
    brand-new lesson that has no row yet, and requiring a save first would
    break the editor's paste/drag flow. Unreferenced files are reaped later
    by the description diff in `update_lesson` / `delete_lesson`."""
    path = await save_lesson_content_image(file)
    return LessonContentImageOut(path=path)


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


_QUESTION_LOAD_OPTIONS = (
    selectinload(Question.choices),
    selectinload(Question.match_pairs),
    selectinload(Question.answer_variants),
)


def _apply_question_payload(question: Question, payload: QuestionIn) -> None:
    question.qtype = payload.qtype
    question.text = payload.text
    question.max_score = payload.max_score
    question.choices = [
        Choice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(payload.choices)
    ]
    question.match_pairs = [
        MatchPair(prompt_text=p.prompt_text, answer_text=p.answer_text, order_index=i)
        for i, p in enumerate(payload.match_pairs)
    ]
    question.answer_variants = [AnswerVariant(text=v.strip()) for v in payload.answer_variants if v.strip()]


@router.get("/teacher/lessons/{lesson_id}/questions", response_model=list[QuestionTeacherOut])
async def list_lesson_questions(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[QuestionTeacherOut]:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    questions = (
        await db.scalars(
            select(Question)
            .where(Question.lesson_id == lesson_id)
            .options(*_QUESTION_LOAD_OPTIONS)
            .order_by(Question.order_index)
        )
    ).all()
    return [QuestionTeacherOut.model_validate(q) for q in questions]


@router.get("/teacher/sections/{section_id}/questions", response_model=list[QuestionTeacherOut])
async def list_section_questions(
    section_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[QuestionTeacherOut]:
    await assert_teacher_owns_section(db, teacher, section_id)
    questions = (
        await db.scalars(
            select(Question)
            .where(Question.section_id == section_id)
            .options(*_QUESTION_LOAD_OPTIONS)
            .order_by(Question.order_index)
        )
    ).all()
    return [QuestionTeacherOut.model_validate(q) for q in questions]


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
    question = Question(lesson_id=lesson_id, order_index=next_order)
    _apply_question_payload(question, payload)
    db.add(question)
    await db.commit()

    question = await db.scalar(
        select(Question).where(Question.id == question.id).options(*_QUESTION_LOAD_OPTIONS)
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
    question = Question(section_id=section_id, order_index=next_order)
    _apply_question_payload(question, payload)
    db.add(question)
    await db.commit()

    question = await db.scalar(
        select(Question).where(Question.id == question.id).options(*_QUESTION_LOAD_OPTIONS)
    )
    return QuestionTeacherOut.model_validate(question)


@router.patch("/teacher/questions/{question_id}", response_model=QuestionTeacherOut)
async def update_question(
    question_id: int,
    payload: QuestionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> QuestionTeacherOut:
    # Full replace, not a partial patch: choices/match_pairs/answer_variants
    # are qtype-specific, so validating (and swapping) anything less than
    # the whole set risks leaving mismatched leftovers from the old qtype.
    await assert_teacher_owns_question(db, teacher, question_id)

    question = await db.scalar(
        select(Question).where(Question.id == question_id).options(*_QUESTION_LOAD_OPTIONS)
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вопрос не найден")
    _apply_question_payload(question, payload)
    await db.commit()

    question = await db.scalar(
        select(Question).where(Question.id == question_id).options(*_QUESTION_LOAD_OPTIONS)
    )
    return QuestionTeacherOut.model_validate(question)


@router.delete("/teacher/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> None:
    await assert_teacher_owns_question(db, teacher, question_id)
    question = await db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вопрос не найден")
    await db.delete(question)
    await db.commit()
