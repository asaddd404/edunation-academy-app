"""Leaderboards: the overall XP board, and one board per lesson / section test.

The overall board ranks by XP from every source (the ЕНТ simulator and
course tests), read from `student_ratings` for all-time and summed from the
`xp_events` ledger for a week or a month. A test board ranks each student's
best finished attempt at that one test.

Every board is identical for every viewer except for `is_me`, so the rows
are computed once per cache window for everyone (see core.cache) and the
viewer's own row is picked out afterwards.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.ent import require_student_with_course_access
from app.config import settings
from app.core.authorization import (
    assert_student_has_category_access,
    get_category_id_for_lesson,
    get_category_id_for_section,
)
from app.core.cache import cached_json
from app.core.rate_limit import LEADERBOARD_BY_USER
from app.database import get_db
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.ent_simulation import EntSimulation, EntSimulationStatus
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.student_rating import StudentRating
from app.models.test_attempt import TestAttempt, TestAttemptStatus
from app.models.user import User
from app.models.xp_event import XpEvent
from app.schemas.leaderboard import (
    LeaderboardCategoryOut,
    LeaderboardEntryOut,
    LeaderboardLessonOut,
    LeaderboardOut,
    LeaderboardPeriod,
    LeaderboardSectionOut,
    TestLeaderboardEntryOut,
    TestLeaderboardOut,
)

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"], dependencies=[Depends(require_student_with_course_access)])

_PERIOD_DAYS: dict[str, int] = {"week": 7, "month": 30}


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, 100))


# --- overall XP board -------------------------------------------------------


def _overall_source(period: str):
    """Per-student totals the overall board is built from, as a subquery."""
    if period == "all":
        # Fast path: the running aggregate is already what we want.
        return select(
            StudentRating.student_id.label("student_id"),
            StudentRating.total_xp.label("total_xp"),
            StudentRating.simulations_completed.label("simulations_completed"),
            func.coalesce(StudentRating.best_score, 0).label("best_score"),
        ).subquery()

    cutoff = datetime.now(timezone.utc) - timedelta(days=_PERIOD_DAYS[period])
    xp = (
        select(XpEvent.student_id.label("student_id"), func.sum(XpEvent.xp).label("total_xp"))
        .where(XpEvent.created_at >= cutoff)
        .group_by(XpEvent.student_id)
        .subquery()
    )
    ent = (
        select(
            EntSimulation.student_id.label("student_id"),
            func.count().label("simulations_completed"),
            func.max(EntSimulation.total_score).label("best_score"),
        )
        .where(
            EntSimulation.status == EntSimulationStatus.submitted,
            EntSimulation.submitted_at.is_not(None),
            EntSimulation.submitted_at >= cutoff,
        )
        .group_by(EntSimulation.student_id)
        .subquery()
    )
    return (
        select(
            xp.c.student_id,
            xp.c.total_xp,
            func.coalesce(ent.c.simulations_completed, 0).label("simulations_completed"),
            func.coalesce(ent.c.best_score, 0).label("best_score"),
        )
        .outerjoin(ent, ent.c.student_id == xp.c.student_id)
        .subquery()
    )


async def _tests_passed(db: AsyncSession, student_ids: list[int]) -> dict[int, int]:
    if not student_ids:
        return {}
    rows = await db.execute(
        select(
            TestAttempt.student_id,
            func.count(distinct(TestAttempt.lesson_id)) + func.count(distinct(TestAttempt.section_id)),
        )
        .where(TestAttempt.student_id.in_(student_ids), TestAttempt.passed.is_(True))
        .group_by(TestAttempt.student_id)
    )
    return {student_id: count for student_id, count in rows.all()}


def _overall_row(rank: int, row, user: User, tests_passed: int) -> dict:
    # Plain dicts, not models: this is what goes into the cache, and it
    # stays readable with `redis-cli GET` when something looks wrong.
    return {
        "rank": rank,
        "student_id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "total_xp": row.total_xp,
        "simulations_completed": row.simulations_completed,
        "best_score": row.best_score,
        "tests_passed": tests_passed,
        "has_avatar": user.avatar_path is not None,
    }


async def _overall_rows(db: AsyncSession, period: str, limit: int) -> list[dict]:
    source = _overall_source(period)
    # `student_id` tiebreaker, as everywhere else that paginates in this app:
    # ties on XP are common (a fresh period starts everyone at 0) and without
    # it Postgres is free to reorder equal rows between requests.
    rows = (
        await db.execute(
            select(source, User)
            .join(User, User.id == source.c.student_id)
            .order_by(source.c.total_xp.desc(), source.c.student_id)
            .limit(limit)
        )
    ).all()
    passed = await _tests_passed(db, [row.student_id for row in rows])
    return [_overall_row(i + 1, row, row.User, passed.get(row.student_id, 0)) for i, row in enumerate(rows)]


async def _overall_own_standing(db: AsyncSession, period: str, student: User) -> dict | None:
    """Where one student sits, for when they are outside the top rows."""
    source = _overall_source(period)
    mine = (await db.execute(select(source).where(source.c.student_id == student.id))).one_or_none()
    if mine is None:
        return None

    # Same ordering as the list itself -- XP, then student_id -- so a student
    # tied with someone above them gets the rank the list would give them.
    ahead = await db.scalar(
        select(func.count())
        .select_from(source)
        .where(
            (source.c.total_xp > mine.total_xp)
            | ((source.c.total_xp == mine.total_xp) & (source.c.student_id < student.id))
        )
    )
    passed = await _tests_passed(db, [student.id])
    return _overall_row((ahead or 0) + 1, mine, student, passed.get(student.id, 0))


@router.get("", response_model=LeaderboardOut)
async def get_leaderboard(
    limit: int = 20,
    period: LeaderboardPeriod = "all",
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> LeaderboardOut:
    await LEADERBOARD_BY_USER.enforce(str(student.id))
    limit = _clamp_limit(limit)

    async def build_rows() -> list[dict]:
        return await _overall_rows(db, period, limit)

    raw_rows = await cached_json(f"leaderboard:{period}:{limit}", settings.leaderboard_cache_seconds, build_rows)
    entries = [LeaderboardEntryOut(**row, is_me=(row["student_id"] == student.id)) for row in raw_rows]

    me = next((e for e in entries if e.is_me), None)
    if me is None:

        async def build_me() -> dict | None:
            return await _overall_own_standing(db, period, student)

        own = await cached_json(
            f"leaderboard:{period}:me:{student.id}", settings.leaderboard_cache_seconds, build_me
        )
        if own is not None:
            me = LeaderboardEntryOut(**own, is_me=True)

    return LeaderboardOut(entries=entries, me=me)


# --- per-test boards --------------------------------------------------------


async def _test_rows(db: AsyncSession, owner_filter) -> list[dict]:
    """Every student's best finished attempt at one test, ranked.

    Best = highest score, then fastest; attempts recorded before durations
    were measured sort after timed ones at the same score. The whole ranked
    list is returned (and cached) rather than the top N, because the viewer's
    own rank has to come from the same ordering -- a test's audience is one
    category's enrolled students, so this stays small.
    """
    per_student = (
        select(
            TestAttempt.student_id,
            TestAttempt.score,
            TestAttempt.passed,
            TestAttempt.correct_count,
            TestAttempt.question_count,
            TestAttempt.duration_seconds,
            func.row_number()
            .over(
                partition_by=TestAttempt.student_id,
                order_by=(
                    TestAttempt.score.desc(),
                    TestAttempt.duration_seconds.asc().nulls_last(),
                    TestAttempt.id,
                ),
            )
            .label("rn"),
            func.sum(func.coalesce(TestAttempt.xp_earned, 0)).over(partition_by=TestAttempt.student_id).label("xp_total"),
            func.count().over(partition_by=TestAttempt.student_id).label("attempts"),
        )
        .where(owner_filter, TestAttempt.status == TestAttemptStatus.completed)
        .subquery()
    )
    rows = (
        await db.execute(
            select(per_student, User)
            .join(User, User.id == per_student.c.student_id)
            .where(per_student.c.rn == 1)
        )
    ).all()

    def sort_key(row):
        no_time = row.duration_seconds is None
        return (-row.score, no_time, row.duration_seconds or 0, row.student_id)

    return [
        {
            "rank": i + 1,
            "student_id": row.student_id,
            "first_name": row.User.first_name,
            "last_name": row.User.last_name,
            "has_avatar": row.User.avatar_path is not None,
            "passed": row.passed,
            "score": row.score,
            "correct_count": row.correct_count,
            "question_count": row.question_count,
            "duration_seconds": row.duration_seconds,
            "xp_earned": row.xp_total,
            "attempts": row.attempts,
        }
        for i, row in enumerate(sorted(rows, key=sort_key))
    ]


async def _test_board(
    db: AsyncSession, student: User, scope: str, scope_id: int, title: str, owner_filter, limit: int
) -> TestLeaderboardOut:
    async def build_rows() -> list[dict]:
        return await _test_rows(db, owner_filter)

    raw_rows = await cached_json(
        f"leaderboard:{scope}:{scope_id}", settings.leaderboard_cache_seconds, build_rows
    )
    mine = next((row for row in raw_rows if row["student_id"] == student.id), None)
    return TestLeaderboardOut(
        scope=scope,
        scope_id=scope_id,
        title=title,
        entries=[TestLeaderboardEntryOut(**row, is_me=row["student_id"] == student.id) for row in raw_rows[:limit]],
        me=TestLeaderboardEntryOut(**mine, is_me=True) if mine else None,
    )


@router.get("/lessons/{lesson_id}", response_model=TestLeaderboardOut)
async def get_lesson_leaderboard(
    lesson_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> TestLeaderboardOut:
    await LEADERBOARD_BY_USER.enforce(str(student.id))
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)
    title = await db.scalar(select(Lesson.title).where(Lesson.id == lesson_id))
    return await _test_board(
        db, student, "lesson", lesson_id, title, TestAttempt.lesson_id == lesson_id, _clamp_limit(limit)
    )


@router.get("/sections/{section_id}", response_model=TestLeaderboardOut)
async def get_section_leaderboard(
    section_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> TestLeaderboardOut:
    await LEADERBOARD_BY_USER.enforce(str(student.id))
    category_id = await get_category_id_for_section(db, section_id)
    await assert_student_has_category_access(db, student, category_id)
    title = await db.scalar(select(Section.title).where(Section.id == section_id))
    return await _test_board(
        db, student, "section", section_id, title, TestAttempt.section_id == section_id, _clamp_limit(limit)
    )


@router.get("/scopes", response_model=list[LeaderboardCategoryOut])
async def list_leaderboard_scopes(
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> list[LeaderboardCategoryOut]:
    """The lessons and sections the student can open a test board for:
    every one in their approved categories that actually has a test."""
    categories = (
        await db.scalars(
            select(Category)
            .join(Application, Application.category_id == Category.id)
            .where(Application.student_id == student.id, Application.status == ApplicationStatusEnum.approved)
            .order_by(Category.name)
        )
    ).all()
    if not categories:
        return []
    category_ids = [c.id for c in categories]

    sections = (
        await db.scalars(
            select(Section).where(Section.category_id.in_(category_ids)).order_by(Section.order_index, Section.id)
        )
    ).all()
    lessons = (
        await db.execute(
            select(Lesson.id, Lesson.title, Lesson.section_id)
            .join(Section, Section.id == Lesson.section_id)
            .where(Section.category_id.in_(category_ids))
            .order_by(Lesson.order_index, Lesson.id)
        )
    ).all()
    lessons_with_test = set(
        (
            await db.scalars(
                select(distinct(Question.lesson_id)).where(Question.lesson_id.in_([lesson.id for lesson in lessons]))
            )
        ).all()
    )
    sections_with_test = set(
        (
            await db.scalars(
                select(distinct(Question.section_id)).where(Question.section_id.in_([s.id for s in sections]))
            )
        ).all()
    )

    lessons_by_section: dict[int, list[LeaderboardLessonOut]] = {}
    for lesson in lessons:
        if lesson.id in lessons_with_test:
            lessons_by_section.setdefault(lesson.section_id, []).append(
                LeaderboardLessonOut(id=lesson.id, title=lesson.title)
            )

    sections_by_category: dict[int, list[LeaderboardSectionOut]] = {}
    for section in sections:
        has_test = section.id in sections_with_test
        section_lessons = lessons_by_section.get(section.id, [])
        if has_test or section_lessons:
            sections_by_category.setdefault(section.category_id, []).append(
                LeaderboardSectionOut(id=section.id, title=section.title, has_test=has_test, lessons=section_lessons)
            )

    return [
        LeaderboardCategoryOut(id=c.id, name=c.name, sections=sections_by_category.get(c.id, []))
        for c in categories
        if sections_by_category.get(c.id)
    ]
