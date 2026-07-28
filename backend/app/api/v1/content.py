from fastapi import APIRouter, Depends, HTTPException, status
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
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.homework import HomeworkSubmissionOut
from app.schemas.lesson import LessonDetailOut
from app.schemas.section import SectionOut
from app.schemas.test_attempt import SectionTestOut

router = APIRouter(tags=["content"], dependencies=[Depends(require_role(RoleEnum.student))])


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
        .options(selectinload(Section.test_questions).selectinload(Question.choices))
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
        questions=list(section.test_questions),
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
        .options(selectinload(Lesson.questions).selectinload(Question.choices))
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

    out = LessonDetailOut.model_validate(lesson)
    out.is_unlocked = True
    out.is_passed = lesson_id in passed
    out.my_homework = HomeworkSubmissionOut.model_validate(submission) if submission else None
    return out
