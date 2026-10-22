"""Lesson mini-tests and section tests, as start -> submit sessions.

`start` opens an attempt (or resumes the student's open one), fixes its
`started_at`, and is the only place questions are handed out -- under
matching tokens scoped to that attempt. `submit` grades it exactly once,
under a row lock, and credits XP for a passed attempt by its accuracy and
the time the server measured between the two calls.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.content import QUESTION_LOAD_OPTIONS, build_student_question
from app.core.authorization import (
    assert_student_has_category_access,
    get_category_id_for_lesson,
    get_category_id_for_section,
)
from app.core.match_tokens import attempt_scope, decode_match_answer
from app.core.progress import get_lesson_progress, is_section_test_unlocked
from app.core.question_scoring import grade_question
from app.core.rate_limit import TEST_START_BY_USER, TEST_SUBMIT_BY_USER
from app.core.rating import apply_test_attempt_xp, compute_test_xp
from app.database import get_db
from app.deps import require_role
from app.models.question import Question
from app.models.test_attempt import TestAttempt, TestAttemptStatus
from app.models.user import RoleEnum, User
from app.schemas.test_attempt import TestAttemptIn, TestAttemptOut, TestSessionOut

router = APIRouter(tags=["tests"], dependencies=[Depends(require_role(RoleEnum.student))])

PASS_THRESHOLD_PERCENT = 50

# An attempt left open longer than this is abandoned rather than resumed:
# the student gets a fresh session (and a fresh clock) instead of one whose
# elapsed time already rules out any speed bonus.
STALE_ATTEMPT_AFTER = timedelta(hours=2)


async def _questions_for(db: AsyncSession, attempt: TestAttempt) -> list[Question]:
    owner = Question.lesson_id == attempt.lesson_id if attempt.lesson_id else Question.section_id == attempt.section_id
    return list(
        (
            await db.scalars(select(Question).where(owner).options(*QUESTION_LOAD_OPTIONS).order_by(Question.order_index))
        ).all()
    )


def _aware(moment: datetime) -> datetime:
    # SQLite (the no-Docker test path) hands timestamps back naive.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _elapsed_seconds(started_at: datetime, now: datetime) -> int:
    return max(0, int((now - _aware(started_at)).total_seconds()))


async def _open_session(db: AsyncSession, student: User, *, lesson_id: int | None, section_id: int | None) -> TestSessionOut:
    scope = TestAttempt.lesson_id == lesson_id if lesson_id is not None else TestAttempt.section_id == section_id
    open_filter = (TestAttempt.student_id == student.id, scope, TestAttempt.status == TestAttemptStatus.in_progress)
    now = datetime.now(timezone.utc)

    attempt = await db.scalar(select(TestAttempt).where(*open_filter))
    if attempt is not None and _elapsed_seconds(attempt.started_at, now) > STALE_ATTEMPT_AFTER.total_seconds():
        await db.execute(delete(TestAttempt).where(TestAttempt.id == attempt.id))
        attempt = None

    if attempt is None:
        attempt = TestAttempt(student_id=student.id, lesson_id=lesson_id, section_id=section_id, started_at=now)
        db.add(attempt)
        try:
            await db.commit()
        except IntegrityError:
            # A concurrent start won the partial unique index; resume theirs.
            await db.rollback()
            attempt = await db.scalar(select(TestAttempt).where(*open_filter))
            if attempt is None:
                raise
    else:
        await db.commit()

    questions = await _questions_for(db, attempt)
    if not questions:
        await db.execute(delete(TestAttempt).where(TestAttempt.id == attempt.id))
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "В этом тесте ещё нет вопросов")

    return TestSessionOut(
        attempt_id=attempt.id,
        started_at=_aware(attempt.started_at),
        elapsed_seconds=_elapsed_seconds(attempt.started_at, now),
        questions=[build_student_question(q, attempt.id) for q in questions],
    )


@router.post("/lessons/{lesson_id}/test/start", response_model=TestSessionOut)
async def start_lesson_test(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestSessionOut:
    await TEST_START_BY_USER.enforce(str(student.id))
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)

    unlocked, _ = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")

    return await _open_session(db, student, lesson_id=lesson_id, section_id=None)


@router.post("/sections/{section_id}/test/start", response_model=TestSessionOut)
async def start_section_test(
    section_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestSessionOut:
    await TEST_START_BY_USER.enforce(str(student.id))
    category_id = await get_category_id_for_section(db, section_id)
    await assert_student_has_category_access(db, student, category_id)

    if not await is_section_test_unlocked(db, student.id, section_id, category_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Тест раздела ещё заблокирован")

    return await _open_session(db, student, lesson_id=None, section_id=section_id)


@router.post("/test-attempts/{attempt_id}/submit", response_model=TestAttemptOut)
async def submit_test_attempt(
    attempt_id: int,
    payload: TestAttemptIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestAttemptOut:
    await TEST_SUBMIT_BY_USER.enforce(str(student.id))

    # Locked before the status check, so two concurrent submits of one
    # attempt cannot both see it open and both be graded and paid.
    attempt = await db.scalar(
        select(TestAttempt)
        .where(TestAttempt.id == attempt_id, TestAttempt.student_id == student.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Попытка не найдена")
    if attempt.status != TestAttemptStatus.in_progress:
        raise HTTPException(status.HTTP_409_CONFLICT, "Попытка уже сдана")

    # Access is re-checked rather than trusted from `start`: an enrollment
    # revoked mid-attempt should not still be able to earn XP.
    if attempt.lesson_id is not None:
        category_id = await get_category_id_for_lesson(db, attempt.lesson_id)
    else:
        category_id = await get_category_id_for_section(db, attempt.section_id)
    await assert_student_has_category_access(db, student, category_id)

    questions = await _questions_for(db, attempt)
    if not questions:
        raise HTTPException(status.HTTP_409_CONFLICT, "В этом тесте ещё нет вопросов")

    scope = attempt_scope(attempt.id)
    answers_by_question = {a.question_id: a for a in payload.answers}
    stored_answers: dict[str, dict] = {}
    earned = max_points = correct = 0
    for question in questions:
        answer = answers_by_question.get(question.id)
        answer_data = answer.model_dump(exclude_none=True, exclude={"question_id"}) if answer else None
        answer_data = decode_match_answer([p.id for p in question.match_pairs], scope, answer_data)
        points = grade_question(question, answer_data)
        earned += points
        max_points += question.max_score
        if points == question.max_score:
            correct += 1
        if answer_data is not None:
            stored_answers[str(question.id)] = answer_data

    now = datetime.now(timezone.utc)
    score = round(earned / max_points * 100) if max_points else 0

    attempt.status = TestAttemptStatus.completed
    attempt.submitted_at = now
    attempt.duration_seconds = _elapsed_seconds(attempt.started_at, now)
    attempt.score = score
    attempt.passed = score >= PASS_THRESHOLD_PERCENT
    attempt.earned_points = earned
    attempt.max_points = max_points
    attempt.correct_count = correct
    attempt.question_count = len(questions)
    attempt.answers = stored_answers
    attempt.xp_earned = await apply_test_attempt_xp(db, attempt)

    owner = (
        TestAttempt.lesson_id == attempt.lesson_id
        if attempt.lesson_id is not None
        else TestAttempt.section_id == attempt.section_id
    )
    attempt_number = await db.scalar(
        select(func.count(TestAttempt.id)).where(
            TestAttempt.student_id == student.id, owner, TestAttempt.status == TestAttemptStatus.completed
        )
    )

    await db.commit()

    worth = compute_test_xp(earned, max_points, len(questions), attempt.duration_seconds) if attempt.passed else None
    return TestAttemptOut(
        attempt_id=attempt.id,
        score=score,
        passed=attempt.passed,
        attempt_number=attempt_number or 1,
        correct_count=correct,
        question_count=len(questions),
        earned_points=earned,
        max_points=max_points,
        duration_seconds=attempt.duration_seconds,
        xp_earned=attempt.xp_earned,
        accuracy_xp=worth.accuracy_xp if worth else 0,
        speed_bonus=worth.speed_bonus if worth else 0,
    )
