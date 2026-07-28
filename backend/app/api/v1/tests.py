from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_student_has_category_access, get_category_id_for_lesson
from app.core.progress import get_lesson_progress
from app.database import get_db
from app.deps import require_role
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.test_attempt import TestAttempt
from app.models.user import RoleEnum, User
from app.schemas.test_attempt import TestAttemptIn, TestAttemptOut

router = APIRouter(tags=["tests"], dependencies=[Depends(require_role(RoleEnum.student))])


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

    submitted = {a.question_id: a.choice_id for a in payload.answers}

    correct_count = 0
    for question in lesson.questions:
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

    total = len(lesson.questions)
    score = round((correct_count / total) * 100)
    passed = score >= 50

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
