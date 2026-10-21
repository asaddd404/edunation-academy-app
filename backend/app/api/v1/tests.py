"""Lesson mini-tests and section tests, from the student's side.

An attempt now has two steps. `.../test/attempts/start` draws the attempt's
questions from the test's bank (see app.core.test_draw) and records them;
`.../test/attempts` grades exactly those. The server has to remember the
draw: with a bank larger than one attempt, grading against the whole bank
would count every question the student was never shown as wrong.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.content import build_student_question
from app.core.authorization import (
    assert_student_has_category_access,
    get_category_id_for_lesson,
    get_category_id_for_section,
)
from app.core.progress import CourseProgress, get_course_progress
from app.core.question_scoring import grade_question
from app.core.rate_limit import TEST_ATTEMPT_BY_USER
from app.core.test_draw import attempt_rng, draw_question_ids
from app.database import get_db
from app.deps import require_role
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt
from app.models.user import RoleEnum, User
from app.schemas.test_attempt import (
    TestAttemptIn,
    TestAttemptOut,
    TestAttemptStartOut,
    TestHubCourseOut,
    TestHubSectionOut,
    TestInfoOut,
    TestKind,
)

router = APIRouter(tags=["tests"], dependencies=[Depends(require_role(RoleEnum.student))])

_QUESTION_LOAD_OPTIONS = (
    selectinload(Question.choices),
    selectinload(Question.match_pairs),
    selectinload(Question.answer_variants),
)


@dataclass
class _Test:
    """One lesson's mini-test or one section's test, resolved for a student."""

    kind: TestKind
    id: int
    title: str
    questions_per_attempt: int | None
    pool: list[Question]
    is_unlocked: bool
    is_passed: bool

    @property
    def question_count(self) -> int:
        return min(self.questions_per_attempt or len(self.pool), len(self.pool))

    def attempt_filter(self):
        column = TestAttempt.lesson_id if self.kind == "lesson" else TestAttempt.section_id
        return column == self.id

    def owner_fields(self) -> dict:
        return {"lesson_id": self.id} if self.kind == "lesson" else {"section_id": self.id}


async def _load_test(db: AsyncSession, student: User, kind: TestKind, test_id: int) -> _Test:
    """Resolves the test and checks the student may see it at all (enrolled
    in the course). Whether it is *open* is reported, not enforced, here:
    the info endpoint shows a locked test; start/submit refuse it."""
    if kind == "lesson":
        category_id = await get_category_id_for_lesson(db, test_id)
        await assert_student_has_category_access(db, student, category_id)
        owner = await db.scalar(
            select(Lesson).where(Lesson.id == test_id).options(selectinload(Lesson.questions).options(*_QUESTION_LOAD_OPTIONS))
        )
        pool = owner.questions
    else:
        category_id = await get_category_id_for_section(db, test_id)
        await assert_student_has_category_access(db, student, category_id)
        owner = await db.scalar(
            select(Section)
            .where(Section.id == test_id)
            .options(selectinload(Section.test_questions).options(*_QUESTION_LOAD_OPTIONS))
        )
        pool = owner.test_questions

    progress = await get_course_progress(db, student.id, category_id)
    return _test_from(kind, owner, list(pool), progress)


def _test_from(kind: TestKind, owner: Lesson | Section, pool: list[Question], progress: CourseProgress) -> _Test:
    if kind == "lesson":
        unlocked = owner.id in progress.unlocked_lesson_ids
        passed = owner.id in progress.passed_lesson_ids
    else:
        unlocked = owner.id in progress.unlocked_test_section_ids
        passed = owner.id in progress.passed_section_ids
    return _Test(
        kind=kind,
        id=owner.id,
        title=owner.title,
        questions_per_attempt=owner.questions_per_attempt,
        pool=pool,
        is_unlocked=unlocked,
        is_passed=passed,
    )


def _assert_open(test: _Test) -> None:
    if not test.is_unlocked:
        message = "Урок ещё заблокирован" if test.kind == "lesson" else "Тест раздела ещё заблокирован"
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)
    if not test.pool:
        message = "В этом уроке ещё нет мини-теста" if test.kind == "lesson" else "В этом разделе ещё нет теста"
        raise HTTPException(status.HTTP_409_CONFLICT, message)


async def _open_attempt(db: AsyncSession, student: User, test: _Test) -> TestAttempt | None:
    return await db.scalar(
        select(TestAttempt)
        .where(TestAttempt.student_id == student.id, test.attempt_filter(), TestAttempt.submitted_at.is_(None))
        .order_by(TestAttempt.id.desc())
        .limit(1)
    )


async def _info(db: AsyncSession, student: User, test: _Test) -> TestInfoOut:
    used, best = (
        await db.execute(
            select(func.count(TestAttempt.id), func.max(TestAttempt.score)).where(
                TestAttempt.student_id == student.id, test.attempt_filter(), TestAttempt.submitted_at.is_not(None)
            )
        )
    ).one()
    open_attempt = await _open_attempt(db, student, test)
    return TestInfoOut(
        kind=test.kind,
        id=test.id,
        title=test.title,
        is_unlocked=test.is_unlocked,
        is_passed=test.is_passed,
        question_count=test.question_count,
        pool_size=len(test.pool),
        attempts_used=used or 0,
        best_score=best,
        in_progress_attempt_id=open_attempt.id if open_attempt else None,
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


def _questions_out(test: _Test, attempt: TestAttempt):
    by_id = {q.id: q for q in test.pool}
    rng = attempt_rng(attempt.id)
    return [build_student_question(by_id[qid], rng) for qid in attempt.question_ids or [] if qid in by_id]


async def _start(db: AsyncSession, student: User, test: _Test) -> TestAttemptStartOut:
    _assert_open(test)
    pool_ids = {q.id for q in test.pool}

    # An unfinished attempt is resumed, never redrawn: otherwise reopening the
    # page would be a free reroll until an easy selection came up. One whose
    # questions were since deleted from the bank is abandoned instead.
    attempt = await _open_attempt(db, student, test)
    if attempt is not None and attempt.question_ids and set(attempt.question_ids) <= pool_ids:
        return TestAttemptStartOut(attempt_id=attempt.id, questions=_questions_out(test, attempt))
    if attempt is not None:
        await db.delete(attempt)

    previous = await db.scalar(
        select(TestAttempt.question_ids)
        .where(TestAttempt.student_id == student.id, test.attempt_filter(), TestAttempt.submitted_at.is_not(None))
        .order_by(TestAttempt.id.desc())
        .limit(1)
    )
    attempt = TestAttempt(student_id=student.id, question_ids=[], **test.owner_fields())
    db.add(attempt)
    await db.flush()
    # The draw is seeded by the attempt too, so it is reproducible for
    # debugging a complaint ("my retake had the same questions").
    attempt.question_ids = draw_question_ids(
        [q.id for q in test.pool], test.questions_per_attempt, previous, attempt_rng(attempt.id)
    )
    await db.commit()
    return TestAttemptStartOut(attempt_id=attempt.id, questions=_questions_out(test, attempt))


async def _submit(db: AsyncSession, student: User, test: _Test, payload: TestAttemptIn) -> TestAttemptOut:
    await TEST_ATTEMPT_BY_USER.enforce(f"{student.id}:{test.kind}:{test.id}")
    _assert_open(test)
    now = datetime.now(timezone.utc)

    if payload.attempt_id is None:
        # A page opened before attempts were drawn per start. Gradeable only
        # while the test still shows its whole bank -- that page displayed
        # every question; with a per-attempt draw it cannot know which.
        if test.questions_per_attempt:
            raise HTTPException(status.HTTP_409_CONFLICT, "Тест обновился — откройте его заново")
        questions = test.pool
        attempt = TestAttempt(
            student_id=student.id, question_ids=[q.id for q in questions], submitted_at=now, **test.owner_fields()
        )
        db.add(attempt)
    else:
        attempt = await db.get(TestAttempt, payload.attempt_id)
        expected_scope = (test.id, None) if test.kind == "lesson" else (None, test.id)
        if attempt is None or attempt.student_id != student.id or (attempt.lesson_id, attempt.section_id) != expected_scope:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Попытка не найдена")
        # Claimed atomically, like an ЕНТ submit: two submits of one attempt
        # in flight together must not both be graded and counted.
        claimed = await db.execute(
            update(TestAttempt)
            .where(TestAttempt.id == attempt.id, TestAttempt.submitted_at.is_(None))
            .values(submitted_at=now)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Эта попытка уже отправлена")
        attempt.submitted_at = now
        drawn = set(attempt.question_ids or [])
        questions = [q for q in test.pool if q.id in drawn]

    attempt.score, attempt.passed = _grade(questions, payload)
    await db.flush()
    attempt_number = await db.scalar(
        select(func.count(TestAttempt.id)).where(
            TestAttempt.student_id == student.id, test.attempt_filter(), TestAttempt.submitted_at.is_not(None)
        )
    )
    await db.commit()
    return TestAttemptOut(score=attempt.score, passed=attempt.passed, attempt_number=attempt_number or 1)


@router.get("/lessons/{lesson_id}/test", response_model=TestInfoOut)
async def get_lesson_test(
    lesson_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> TestInfoOut:
    return await _info(db, student, await _load_test(db, student, "lesson", lesson_id))


@router.get("/sections/{section_id}/test", response_model=TestInfoOut)
async def get_section_test(
    section_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> TestInfoOut:
    return await _info(db, student, await _load_test(db, student, "section", section_id))


@router.post("/lessons/{lesson_id}/test/attempts/start", response_model=TestAttemptStartOut)
async def start_lesson_test(
    lesson_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> TestAttemptStartOut:
    return await _start(db, student, await _load_test(db, student, "lesson", lesson_id))


@router.post("/sections/{section_id}/test/attempts/start", response_model=TestAttemptStartOut)
async def start_section_test(
    section_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> TestAttemptStartOut:
    return await _start(db, student, await _load_test(db, student, "section", section_id))


@router.post("/lessons/{lesson_id}/test/attempts", response_model=TestAttemptOut, status_code=status.HTTP_201_CREATED)
async def submit_test_attempt(
    lesson_id: int,
    payload: TestAttemptIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestAttemptOut:
    return await _submit(db, student, await _load_test(db, student, "lesson", lesson_id), payload)


@router.post("/sections/{section_id}/test/attempts", response_model=TestAttemptOut, status_code=status.HTTP_201_CREATED)
async def submit_section_test_attempt(
    section_id: int,
    payload: TestAttemptIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> TestAttemptOut:
    return await _submit(db, student, await _load_test(db, student, "section", section_id), payload)


@router.get("/me/tests", response_model=list[TestHubCourseOut])
async def list_my_tests(
    db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> list[TestHubCourseOut]:
    """Every test in every course the student is enrolled in, grouped by
    course and section, with where they stand on each -- the "Тесты" page."""
    categories = (
        await db.scalars(
            select(Category)
            .join(Application, Application.category_id == Category.id)
            .where(
                Application.student_id == student.id,
                Application.status == ApplicationStatusEnum.approved,
                Category.is_active.is_(True),
            )
            .distinct()
            .order_by(Category.name, Category.id)
        )
    ).all()

    courses: list[TestHubCourseOut] = []
    for category in categories:
        sections = (
            await db.scalars(
                select(Section)
                .where(Section.category_id == category.id)
                .options(selectinload(Section.lessons).selectinload(Lesson.questions), selectinload(Section.test_questions))
                .order_by(Section.order_index, Section.id)
            )
        ).all()
        progress = await get_course_progress(db, student.id, category.id)

        hub_sections: list[TestHubSectionOut] = []
        for section in sections:
            lesson_tests = [
                await _info(db, student, _test_from("lesson", lesson, list(lesson.questions), progress))
                for lesson in section.lessons
                if lesson.questions
            ]
            section_test = (
                await _info(db, student, _test_from("section", section, list(section.test_questions), progress))
                if section.test_questions
                else None
            )
            if lesson_tests or section_test:
                hub_sections.append(
                    TestHubSectionOut(
                        section_id=section.id, title=section.title, lesson_tests=lesson_tests, section_test=section_test
                    )
                )
        if hub_sections:
            courses.append(TestHubCourseOut(category_id=category.id, category_name=category.name, sections=hub_sections))
    return courses
