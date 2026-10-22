"""XP: how much an attempt is worth, and the one path that credits it.

Every award goes through `award_xp`, which writes an `xp_events` row and
bumps the student's running total in `student_ratings` in the caller's
transaction. The ledger row carries a unique (source, source_id), so the
same simulation or test attempt can never be credited twice; the rating row
is taken FOR UPDATE first, so awards for one student are serialized -- which
the course-test "only pay for improvement" rule below depends on.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ent_simulation import EntSimulation
from app.models.student_rating import StudentRating
from app.models.test_attempt import TestAttempt, TestAttemptStatus
from app.models.xp_event import XpEvent, XpSource

# 1 ENT point = 1 XP, plus a 20% bonus for finishing a *timed* simulation
# within the limit — rewards choosing the harder, exam-realistic mode over
# always going untimed. Untimed attempts and timed-but-overrun attempts earn
# the base amount only.
_TIMED_BONUS_DIVISOR = 5

# Course tests: 10 XP per question at full accuracy, so a 29-question test
# answered perfectly is worth 290 before the speed bonus.
TEST_XP_PER_QUESTION = 10
# The speed bonus tops out at +50% of the accuracy XP for an instant finish
# and falls linearly to nothing at this many seconds per question. Scaling it
# off the accuracy XP (not a flat amount) means racing through with wrong
# answers earns almost nothing extra.
TEST_SPEED_BONUS_MAX = 0.5
TEST_SPEED_SECONDS_PER_QUESTION = 60


@dataclass(frozen=True)
class TestXp:
    __test__ = False

    accuracy_xp: int
    speed_bonus: int

    @property
    def total(self) -> int:
        return self.accuracy_xp + self.speed_bonus


def compute_test_xp(earned_points: int, max_points: int, question_count: int, duration_seconds: int) -> TestXp:
    """What a passed course-test attempt is worth on its own (before the
    improvement rule in `apply_test_attempt_xp`)."""
    if max_points <= 0 or question_count <= 0:
        return TestXp(0, 0)
    accuracy = earned_points / max_points
    accuracy_xp = round(accuracy * question_count * TEST_XP_PER_QUESTION)
    budget = question_count * TEST_SPEED_SECONDS_PER_QUESTION
    speed_factor = max(0.0, 1 - max(duration_seconds, 0) / budget)
    return TestXp(accuracy_xp, round(accuracy_xp * TEST_SPEED_BONUS_MAX * speed_factor))


def _insert(db: AsyncSession):
    """`INSERT ... ON CONFLICT DO NOTHING` for whichever backend this is.
    Postgres in production; SQLite only on the no-Docker test path."""
    dialect = db.get_bind().dialect.name
    return (postgresql if dialect == "postgresql" else sqlite).insert


async def _lock_rating(db: AsyncSession, student_id: int) -> StudentRating:
    # Insert-if-missing first, so the FOR UPDATE below always has a row to
    # lock. Two first-ever awards racing each other both reach this; the
    # loser's insert is a no-op rather than a primary-key error.
    insert = _insert(db)
    await db.execute(
        insert(StudentRating)
        .values(student_id=student_id, total_xp=0, simulations_completed=0)
        .on_conflict_do_nothing(index_elements=["student_id"])
    )
    return await db.scalar(
        select(StudentRating)
        .where(StudentRating.student_id == student_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def award_xp(
    db: AsyncSession, student_id: int, source: XpSource, source_id: int, xp: int
) -> tuple[StudentRating, bool]:
    """Credits `xp` once for (source, source_id).

    Returns the student's (locked) rating row and whether the award was new.
    Does not commit -- the caller commits together with whatever earned it.
    """
    rating = await _lock_rating(db, student_id)
    inserted = await db.scalar(
        _insert(db)(XpEvent)
        .values(student_id=student_id, source=source.value, source_id=source_id, xp=xp)
        .on_conflict_do_nothing(index_elements=["source", "source_id"])
        .returning(XpEvent.id)
    )
    if inserted is None:
        return rating, False
    rating.total_xp += xp
    return rating, True


async def apply_simulation_xp(db: AsyncSession, simulation: EntSimulation) -> int:
    """Grants XP for a just-graded simulation and updates the student's
    running rating. Must be called inside the same transaction as the
    grading commit, before it — so a submitted attempt and its XP are
    always consistent."""
    base = simulation.total_score or 0
    bonus = base // _TIMED_BONUS_DIVISOR if simulation.is_timed and not simulation.time_expired else 0
    xp_earned = base + bonus

    rating, is_new = await award_xp(db, simulation.student_id, XpSource.ent, simulation.id, xp_earned)
    if not is_new:
        return 0

    rating.simulations_completed += 1
    rating.best_score = max(rating.best_score or 0, base)
    rating.last_simulation_at = simulation.submitted_at

    return xp_earned


async def apply_test_attempt_xp(db: AsyncSession, attempt: TestAttempt) -> int:
    """Credits a just-graded, passed course-test attempt.

    Retakes are unlimited, so paying the full amount every time would make
    the leaderboard a measure of who clicked "retry" most. Instead a test is
    worth its best result: an attempt earns only what it adds over the XP
    already earned on that same test, and a retake that does no better earns
    nothing. The rating row lock taken by award_xp is acquired *before* the
    already-earned sum is read, so two attempts of one student finishing at
    once cannot both be paid against the same baseline.
    """
    if not attempt.passed:
        return 0

    rating = await _lock_rating(db, attempt.student_id)  # noqa: F841 -- held for the read below

    if attempt.lesson_id is not None:
        source, scope_filter = XpSource.lesson_test, TestAttempt.lesson_id == attempt.lesson_id
    else:
        source, scope_filter = XpSource.section_test, TestAttempt.section_id == attempt.section_id

    already = await db.scalar(
        select(func.coalesce(func.sum(XpEvent.xp), 0))
        .join(TestAttempt, TestAttempt.id == XpEvent.source_id)
        .where(
            XpEvent.source == source.value,
            XpEvent.student_id == attempt.student_id,
            TestAttempt.student_id == attempt.student_id,
            TestAttempt.status == TestAttemptStatus.completed,
            scope_filter,
        )
    )

    worth = compute_test_xp(
        attempt.earned_points or 0, attempt.max_points or 0, attempt.question_count or 0, attempt.duration_seconds or 0
    ).total
    gain = max(0, worth - (already or 0))
    if gain == 0:
        return 0

    _, is_new = await award_xp(db, attempt.student_id, source, attempt.id, gain)
    return gain if is_new else 0
