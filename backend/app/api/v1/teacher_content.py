import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import audit_log
from app.core.concurrency import VIDEO_TRANSCODE_GATE
from app.core.rate_limit import UPLOAD_BY_USER
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
    await UPLOAD_BY_USER.enforce(str(teacher.id))
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

    # One grouped query for the whole course rather than a count per lesson:
    # a course with 11 lessons would otherwise fire 11 extra round-trips just
    # to render the builder's readiness chips.
    lesson_ids = [lesson.id for section in sections for lesson in section.lessons]
    counts: dict[int, int] = {}
    if lesson_ids:
        rows = await db.execute(
            select(Question.lesson_id, func.count())
            .where(Question.lesson_id.in_(lesson_ids))
            .group_by(Question.lesson_id)
        )
        counts = {lesson_id: total for lesson_id, total in rows}

    out: list[SectionOut] = []
    for section in sections:
        payload = SectionOut.model_validate(section)
        by_id = {lesson.id: lesson for lesson in section.lessons}
        for summary in payload.lessons:
            summary.question_count = counts.get(summary.id, 0)
            summary.has_homework = bool((by_id[summary.id].homework_assignment or "").strip())
        out.append(payload)
    return out


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

    # Re-fetched with lessons eager-loaded, the same as update_section.
    # Assigning `section.lessons = []` instead -- what this used to do --
    # is itself a lazy load: SQLAlchemy reads the old collection to diff
    # the new one against it, outside an awaited context, and the request
    # died with MissingGreenlet. Every section created from the course
    # builder was a 500.
    section = await db.scalar(
        select(Section).where(Section.id == section.id).options(selectinload(Section.lessons))
    )
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
    request: Request,
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
    audit_log(
        "content.section.delete",
        actor_id=teacher.id,
        actor_role=teacher.role.value,
        request=request,
        section_id=section_id,
        cascaded_lesson_ids=lesson_ids,
    )
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
        video_url=payload.video_url or None,
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
    if payload.video_url is not None:
        lesson.video_url = payload.video_url or None
    await db.commit()
    await db.refresh(lesson)

    # Only after the commit -- if the write failed, the rows still reference
    # these files and deleting them would leave broken images behind.
    for path in dropped_images:
        delete_upload(path)

    return LessonTeacherOut.model_validate(lesson)


@router.delete("/teacher/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    request: Request,
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
    audit_log(
        "content.lesson.delete",
        actor_id=teacher.id,
        actor_role=teacher.role.value,
        request=request,
        lesson_id=lesson_id,
    )
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
    since the request-scoped one is already closed by the time this fires.

    Serialized through a gate: ffmpeg saturates a core for minutes, and
    nothing stopped a teacher queueing five uploads back to back. Five
    concurrent transcodes on the production box (one vCPU) is not a slow
    site, it is an unavailable one -- and unlike a request flood it would be
    self-inflicted, by a teacher doing exactly what the UI invites."""
    async with VIDEO_TRANSCODE_GATE:
        await _transcode_and_record(lesson_id, raw_path)


async def _transcode_and_record(lesson_id: int, raw_path: Path) -> None:
    # No session is held while ffmpeg runs. Reading the lesson opens a
    # transaction, and a transcode takes minutes, while Postgres ends any
    # connection idle in a transaction after db_idle_tx_timeout_ms (30 s).
    # Holding it across the transcode meant the closing commit always hit a
    # dead connection: every real video stayed "processing" forever.
    async with async_session_factory() as db:
        exists = await db.get(Lesson, lesson_id) is not None
    if not exists:
        raw_path.unlink(missing_ok=True)
        return

    status, duration, error = VideoStatusEnum.ready, None, None
    try:
        duration = await transcode_to_hls(lesson_id, raw_path)
    except VideoProcessingError as exc:
        logger.warning("Video transcode failed for lesson %s: %s", lesson_id, exc)
        status, error = VideoStatusEnum.failed, str(exc)[:2000]
    finally:
        raw_path.unlink(missing_ok=True)

    async with async_session_factory() as db:
        lesson = await db.get(Lesson, lesson_id)
        if lesson is None:  # deleted while transcoding
            delete_video_assets(lesson_id)
            return
        lesson.video_status = status
        lesson.video_duration_seconds = duration
        lesson.video_error = error
        await db.commit()


@router.post("/teacher/lesson-content/image", response_model=LessonContentImageOut)
async def upload_lesson_content_image(
    file: UploadFile = File(...),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> LessonContentImageOut:
    """Stores an image for embedding in a lesson's rich description/homework.

    Deliberately not scoped to a lesson id: the teacher can be composing a
    brand-new lesson that has no row yet, and requiring a save first would
    break the editor's paste/drag flow. Unreferenced files are reaped later
    by the description diff in `update_lesson` / `delete_lesson`."""
    await UPLOAD_BY_USER.enforce(str(teacher.id))
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
    await UPLOAD_BY_USER.enforce(str(teacher.id))
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
    out = LessonTeacherOut.model_validate(lesson)
    # The refresh began a new transaction, and the request's session would
    # otherwise stay open -- idle in it -- until the background transcode
    # below finishes, and be killed by the idle-transaction timeout.
    await db.close()

    background_tasks.add_task(_run_video_processing, lesson_id, raw_path)
    return out


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


def _reuse_rows(existing: list, wanted: int, make) -> list:
    """The first `wanted` existing child rows, topped up with new ones.

    Rows are updated in place by position rather than replaced wholesale, so
    an edit keeps their ids. That matters to a student sitting the test while
    the teacher edits it: their answer references choice ids, and their
    matching tokens are minted from pair ids (core.match_tokens). Replacing
    every row on each save -- fixing a typo, say -- would silently turn
    every in-flight answer to that question into a wrong one.
    """
    rows = list(existing[:wanted])
    rows.extend(make() for _ in range(wanted - len(rows)))
    return rows


def _apply_question_payload(question: Question, payload: QuestionIn) -> None:
    question.qtype = payload.qtype
    question.text = payload.text
    question.max_score = payload.max_score

    choices = _reuse_rows(question.choices, len(payload.choices), Choice)
    for i, (row, choice) in enumerate(zip(choices, payload.choices)):
        row.text, row.is_correct, row.order_index = choice.text, choice.is_correct, i
    question.choices = choices

    pairs = _reuse_rows(question.match_pairs, len(payload.match_pairs), MatchPair)
    for i, (row, pair) in enumerate(zip(pairs, payload.match_pairs)):
        row.prompt_text, row.answer_text, row.order_index = pair.prompt_text, pair.answer_text, i
    question.match_pairs = pairs

    texts = [v.strip() for v in payload.answer_variants if v.strip()]
    variants = _reuse_rows(question.answer_variants, len(texts), AnswerVariant)
    for row, text in zip(variants, texts):
        row.text = text
    question.answer_variants = variants


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


@router.put("/teacher/questions/{question_id}", response_model=QuestionTeacherOut)
# PATCH predates PUT here and is kept for clients still sending it; the
# semantics were always a full replace, which is what PUT says.
@router.patch("/teacher/questions/{question_id}", response_model=QuestionTeacherOut, deprecated=True)
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
