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
from app.database import get_db
from app.deps import require_role
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt
from app.models.user import RoleEnum, User
from app.schemas.test_attempt import TestAttemptIn, TestAttemptOut

router = APIRouter(tags=["tests"], dependencies=[Depends(require_role(RoleEnum.student))])


def _grade(questions: list[Question], payload: TestAttemptIn) -> tuple[int, bool]:
    submitted = {a.question_id: a.choice_id for a in payload.answers}
    correct_count = 0
    for question in questions:
        chosen_choice_id = submitted.get(question.id)
        if chosen_choice_id is None:
            continue
        # Validates the choice actually belongs to this question — a
        # spoofed choice_id from another question/lesson never matches.
        correct_choice_ids = {c.id for c in question.choices if c.is_correct}
        valid_choice_ids = {c.id for c in question.choices}
        if chosen_choice_id not in valid_choice_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Вариант ответа не принадлежит этому вопросу")
        if chosen_choice_id in correct_choice_ids:
            correct_count += 1

    score = round((correct_count / len(questions)) * 100)
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
        .options(selectinload(Lesson.questions).selectinload(Question.choices))
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
        .options(selectinload(Section.test_questions).selectinload(Question.choices))
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
