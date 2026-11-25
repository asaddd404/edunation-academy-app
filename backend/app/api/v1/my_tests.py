"""«Мои тесты»: every lesson mini-test and section test of the student's
courses on one page -- what is open, what is passed, attempts and the best
result -- so a student does not have to open lessons one by one to find
what is left."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.progress import (
    compute_unlocked_ids,
    get_lessons_without_questions,
    get_ordered_lesson_ids,
    get_passed_lesson_ids,
    get_passed_section_ids,
)
from app.database import get_db
from app.deps import require_role
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.question import Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt, TestAttemptStatus
from app.models.user import RoleEnum, User

router = APIRouter(tags=["tests"])


class MyTestOut(BaseModel):
    kind: str  # "lesson" | "section"
    id: int
    title: str
    question_count: int  # per attempt
    pool_size: int  # whole bank; bigger than question_count = questions change
    is_unlocked: bool
    is_passed: bool
    in_progress: bool
    attempts_used: int
    best_score: int | None


class MyTestsSectionOut(BaseModel):
    section_id: int
    title: str
    tests: list[MyTestOut]


class MyTestsCourseOut(BaseModel):
    category_id: int
    category_name: str
    sections: list[MyTestsSectionOut]


def _per_attempt(pool: int, limit: int | None) -> int:
    return min(pool, limit) if limit else pool


@router.get("/tests/my", response_model=list[MyTestsCourseOut])
async def my_tests(
    db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> list[MyTestsCourseOut]:
    categories = (
        await db.scalars(
            select(Category)
            .join(Application, Application.category_id == Category.id)
            .where(
                Application.student_id == student.id,
                Application.status == ApplicationStatusEnum.approved,
                Category.is_active.is_(True),
            )
            .order_by(Category.name, Category.id)
            .distinct()
        )
    ).all()
    if not categories:
        return []

    # Attempt stats for every test at once: count, best score, open sitting.
    stats: dict[tuple[str, int], dict] = defaultdict(lambda: {"used": 0, "best": None, "open": False})
    rows = await db.execute(
        select(TestAttempt.lesson_id, TestAttempt.section_id, TestAttempt.status, func.count(), func.max(TestAttempt.score))
        .where(TestAttempt.student_id == student.id)
        .group_by(TestAttempt.lesson_id, TestAttempt.section_id, TestAttempt.status)
    )
    for lesson_id, section_id, status, n, best in rows.all():
        key = ("lesson", lesson_id) if lesson_id is not None else ("section", section_id)
        if status == TestAttemptStatus.completed:
            stats[key]["used"] += n
            stats[key]["best"] = best
        else:
            stats[key]["open"] = True

    out: list[MyTestsCourseOut] = []
    for category in categories:
        sections = (
            await db.scalars(
                select(Section)
                .where(Section.category_id == category.id)
                .options(selectinload(Section.lessons))
                .order_by(Section.order_index, Section.id)
            )
        ).all()
        lesson_ids = [lesson.id for s in sections for lesson in s.lessons]
        section_ids = [s.id for s in sections]
        lesson_pool = dict(
            (
                await db.execute(
                    select(Question.lesson_id, func.count()).where(Question.lesson_id.in_(lesson_ids or [-1])).group_by(Question.lesson_id)
                )
            ).all()
        )
        section_pool = dict(
            (
                await db.execute(
                    select(Question.section_id, func.count()).where(Question.section_id.in_(section_ids or [-1])).group_by(Question.section_id)
                )
            ).all()
        )

        passed = await get_passed_lesson_ids(db, student.id, category.id)
        auto_passed = await get_lessons_without_questions(db, category.id)
        unlocked = compute_unlocked_ids(await get_ordered_lesson_ids(db, category.id), passed | auto_passed)
        passed_sections = await get_passed_section_ids(db, student.id, category.id)

        course_sections: list[MyTestsSectionOut] = []
        for section in sections:
            tests: list[MyTestOut] = []
            for lesson in sorted(section.lessons, key=lambda l: (l.order_index, l.id)):
                pool = lesson_pool.get(lesson.id, 0)
                if not pool:
                    continue
                s = stats[("lesson", lesson.id)]
                tests.append(
                    MyTestOut(
                        kind="lesson",
                        id=lesson.id,
                        title=lesson.title,
                        question_count=_per_attempt(pool, lesson.questions_per_attempt),
                        pool_size=pool,
                        is_unlocked=lesson.id in unlocked,
                        is_passed=lesson.id in passed,
                        in_progress=s["open"],
                        attempts_used=s["used"],
                        best_score=s["best"],
                    )
                )
            pool = section_pool.get(section.id, 0)
            if pool:
                s = stats[("section", section.id)]
                section_lessons = [lesson.id for lesson in section.lessons]
                tests.append(
                    MyTestOut(
                        kind="section",
                        id=section.id,
                        title=section.title,
                        question_count=_per_attempt(pool, section.questions_per_attempt),
                        pool_size=pool,
                        # Same rule as content.is_section_test_unlocked.
                        is_unlocked=all(lid in passed | auto_passed for lid in section_lessons),
                        is_passed=section.id in passed_sections,
                        in_progress=s["open"],
                        attempts_used=s["used"],
                        best_score=s["best"],
                    )
                )
            if tests:
                course_sections.append(MyTestsSectionOut(section_id=section.id, title=section.title, tests=tests))
        if course_sections:
            out.append(MyTestsCourseOut(category_id=category.id, category_name=category.name, sections=course_sections))
    return out
