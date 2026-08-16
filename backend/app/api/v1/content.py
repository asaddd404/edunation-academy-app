import random
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import (
    assert_student_has_category_access,
    get_category_id_for_lesson,
    get_category_id_for_section,
)
from app.core.progress import (
    get_lesson_progress,
    get_lessons_without_questions,
    get_passed_section_ids,
    is_section_test_unlocked,
)
from app.database import get_db
from app.deps import require_role
from app.models.homework import HomeworkSubmission
from app.models.lesson import Lesson, VideoStatusEnum
from app.models.question import Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.homework import HomeworkSubmissionOut
from app.schemas.lesson import ChoiceOut, LessonDetailOut, MatchItemOut, QuestionOut, VideoTicketOut
from app.core.storage import resolve_upload_path
from app.schemas.section import SectionOut
from app.schemas.test_attempt import SectionTestOut
from app.security import set_video_ticket_cookie

router = APIRouter(tags=["content"], dependencies=[Depends(require_role(RoleEnum.student))])

# Separate router so the image route escapes the student-only dependency
# above -- same reasoning as the ЕНТ question images (see ent.py): a plain
# <img src> can't attach the bearer token, and teachers need to see the very
# same file while composing the lesson. Filenames are uuids, so the URL is
# unguessable, but anyone holding the link can fetch it without logging in.
public_router = APIRouter(tags=["content"])


@public_router.get("/lesson-content/images/{filename}")
async def get_lesson_content_image(filename: str) -> FileResponse:
    # `filename` is templated into a filesystem path, so it must be exactly a
    # stored upload name and nothing else -- no separators, no traversal.
    if Path(filename).name != filename or not filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")

    path = resolve_upload_path(f"lesson-content/{filename}")
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")
    return FileResponse(path)


_QUESTION_LOAD_OPTIONS = (
    selectinload(Question.choices),
    selectinload(Question.match_pairs),
    selectinload(Question.answer_variants),
)


def build_student_question(question: Question) -> QuestionOut:
    """Never exposes which choice/pair is correct. For matching, the answer
    side is shuffled so its order can't leak the pairing."""
    match_prompts: list[MatchItemOut] = []
    match_answers: list[MatchItemOut] = []
    if question.match_pairs:
        match_prompts = [MatchItemOut(id=p.id, text=p.prompt_text) for p in question.match_pairs]
        shuffled = list(question.match_pairs)
        random.shuffle(shuffled)
        match_answers = [MatchItemOut(id=p.id, text=p.answer_text) for p in shuffled]

    return QuestionOut(
        id=question.id,
        qtype=question.qtype,
        text=question.text,
        max_score=question.max_score,
        order_index=question.order_index,
        choices=[ChoiceOut(id=c.id, text=c.text) for c in question.choices],
        match_prompts=match_prompts,
        match_answers=match_answers,
    )


@router.get("/categories/{category_id}/sections", response_model=list[SectionOut])
async def list_sections(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> list[SectionOut]:
    await assert_student_has_category_access(db, student, category_id)

    sections = (
        await db.scalars(
            select(Section)
            .where(Section.category_id == category_id)
            .options(selectinload(Section.lessons), selectinload(Section.test_questions))
            .order_by(Section.order_index)
        )
    ).all()

    unlocked, passed = await get_lesson_progress(db, student.id, category_id)
    auto_passed = await get_lessons_without_questions(db, category_id)
    effectively_passed = passed | auto_passed
    passed_sections = await get_passed_section_ids(db, student.id, category_id)

    result = []
    for section in sections:
        out = SectionOut.model_validate(section)
        for lesson_out, lesson in zip(out.lessons, section.lessons):
            lesson_out.is_unlocked = lesson.id in unlocked
            lesson_out.is_passed = lesson.id in passed
        lesson_ids = [lesson.id for lesson in section.lessons]
        out.has_test = len(section.test_questions) > 0
        out.is_test_unlocked = bool(lesson_ids) and all(lid in effectively_passed for lid in lesson_ids)
        out.is_test_passed = section.id in passed_sections
        result.append(out)
    return result


@router.get("/sections/{section_id}/test", response_model=SectionTestOut)
async def get_section_test(
    section_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> SectionTestOut:
    category_id = await get_category_id_for_section(db, section_id)
    await assert_student_has_category_access(db, student, category_id)

    section = await db.scalar(
        select(Section)
        .where(Section.id == section_id)
        .options(selectinload(Section.test_questions).options(*_QUESTION_LOAD_OPTIONS))
    )
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")

    unlocked = await is_section_test_unlocked(db, student.id, section_id, category_id)
    if not unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Тест раздела ещё заблокирован")

    passed_sections = await get_passed_section_ids(db, student.id, category_id)

    return SectionTestOut(
        section_id=section_id,
        is_unlocked=True,
        is_passed=section_id in passed_sections,
        questions=[build_student_question(q) for q in section.test_questions],
    )


@router.get("/lessons/{lesson_id}", response_model=LessonDetailOut)
async def get_lesson(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> LessonDetailOut:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)

    lesson = await db.scalar(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(selectinload(Lesson.questions).options(*_QUESTION_LOAD_OPTIONS))
    )
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")

    unlocked, passed = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")

    submission = await db.scalar(
        select(HomeworkSubmission).where(
            HomeworkSubmission.lesson_id == lesson_id, HomeworkSubmission.student_id == student.id
        )
    )

    return LessonDetailOut(
        id=lesson.id,
        section_id=lesson.section_id,
        title=lesson.title,
        description=lesson.description,
        video_url=lesson.video_url,
        homework_assignment=lesson.homework_assignment,
        order_index=lesson.order_index,
        created_at=lesson.created_at,
        is_unlocked=True,
        is_passed=lesson_id in passed,
        questions=[build_student_question(q) for q in lesson.questions],
        my_homework=HomeworkSubmissionOut.model_validate(submission) if submission else None,
        video_status=lesson.video_status,
        video_duration_seconds=lesson.video_duration_seconds,
    )


@router.post("/lessons/{lesson_id}/video/ticket", response_model=VideoTicketOut)
async def get_lesson_video_ticket(
    lesson_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> VideoTicketOut:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)

    unlocked, _ = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")

    lesson = await db.get(Lesson, lesson_id)
    if lesson is None or lesson.video_status != VideoStatusEnum.ready:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Видео ещё не готово")

    set_video_ticket_cookie(response, lesson_id)
    return VideoTicketOut(playback_path=f"/video/lessons/{lesson_id}/master.m3u8")
