from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import (
    assert_student_has_category_access,
    get_category_id_for_lesson,
    get_category_id_for_section,
)
from app.core.progress import get_lesson_progress, is_section_test_unlocked
from app.core.question_scoring import grade_question
from app.database import get_db
from app.deps import require_role
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt
from app.models.user import RoleEnum, User
from app.schemas.test_attempt import TestAttemptIn, TestAttemptOut

router = APIRouter(tags=["tests"], dependencies=[Depends(require_role(RoleEnum.student))])

_QUESTION_LOAD_OPTIONS = (
    selectinload(Question.choices),
    selectinload(Question.match_pairs),
    selectinload(Question.answer_variants),
)


def _grade(questions: list[Question], payload: TestAttemptIn) -> tuple[int, bool]:
    answers_by_question = {a.question_id: a for a in payload.answers}
    total_earned = 0
    total_max = 0
    for question in questions:
        answer = answers_by_question.get(question.id)
        answer_data = answer.model_dump(exclude_none=True, exclude={"question_id"}) if answer else None
        total_earned += grade_question(question, answer_data)
        total_max += question.max_score

    score = round((total_earned / total_max) * 100) if total_max else 0
    return score, score >= 50


@router.post("/lessons/{lesson_id}/test/attempts", response_model=TestAttemptOut, status_code=status.HTTP_201_CREATED)
async def submit_test_attempt(
    lesson_id: int,
    payload: TestAttemptIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestAttemptOut:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)

    unlocked, _ = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")

    lesson = await db.scalar(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(selectinload(Lesson.questions).options(*_QUESTION_LOAD_OPTIONS))
    )
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")
    if not lesson.questions:
        raise HTTPException(status.HTTP_409_CONFLICT, "В этом уроке ещё нет мини-теста")

    score, passed = _grade(lesson.questions, payload)

    attempt_number = 1 + (
        await db.scalar(
            select(func.count(TestAttempt.id)).where(
                TestAttempt.student_id == student.id, TestAttempt.lesson_id == lesson_id
            )
        )
        or 0
    )

    attempt = TestAttempt(student_id=student.id, lesson_id=lesson_id, score=score, passed=passed)
    db.add(attempt)
    await db.commit()

    return TestAttemptOut(score=score, passed=passed, attempt_number=attempt_number)


@router.post("/sections/{section_id}/test/attempts", response_model=TestAttemptOut, status_code=status.HTTP_201_CREATED)
async def submit_section_test_attempt(
    section_id: int,
    payload: TestAttemptIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestAttemptOut:
    category_id = await get_category_id_for_section(db, section_id)
    await assert_student_has_category_access(db, student, category_id)

    if not await is_section_test_unlocked(db, student.id, section_id, category_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Тест раздела ещё заблокирован")

    section = await db.scalar(
        select(Section)
        .where(Section.id == section_id)
        .options(selectinload(Section.test_questions).options(*_QUESTION_LOAD_OPTIONS))
    )
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")
    if not section.test_questions:
        raise HTTPException(status.HTTP_409_CONFLICT, "В этом разделе ещё нет теста")

    score, passed = _grade(section.test_questions, payload)

    attempt_number = 1 + (
        await db.scalar(
            select(func.count(TestAttempt.id)).where(
                TestAttempt.student_id == student.id, TestAttempt.section_id == section_id
            )
        )
        or 0
    )

    attempt = TestAttempt(student_id=student.id, section_id=section_id, score=score, passed=passed)
    db.add(attempt)
    await db.commit()

    return TestAttemptOut(score=score, passed=passed, attempt_number=attempt_number)
