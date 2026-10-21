from datetime import datetime, timedelta, timezone

from sqlalchemy import case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ent_simulation import EntSimulation
from app.models.student_rating import StudentRating

# 1 ENT point = 1 XP, plus a 20% bonus for finishing a *timed* simulation
# within the limit — rewards choosing the harder, exam-realistic mode over
# always going untimed. Untimed attempts earn the base amount only.
_TIMED_BONUS_DIVISOR = 5

# How late a timed attempt may arrive and still count, to absorb network
# latency and a slow auto-submit. Past this the time limit was simply not
# kept -- the countdown lives in the browser, so without a server-side cut-off
# anyone could sit a "timed" exam for as long as they liked.
SUBMIT_GRACE = timedelta(seconds=60)


def is_past_deadline(simulation: EntSimulation, now: datetime) -> bool:
    """Whether a timed attempt was submitted after its deadline plus grace."""
    if not simulation.is_timed or simulation.expires_at is None:
        return False
    expires_at = simulation.expires_at
    if expires_at.tzinfo is None:  # SQLite returns naive UTC timestamps
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now > expires_at + SUBMIT_GRACE


async def apply_simulation_xp(db: AsyncSession, simulation: EntSimulation) -> int:
    """Grants XP for a just-graded simulation, decides whether it is rated,
    and updates the student's running rating. Must be called inside the same
    transaction as the grading commit, before it -- so a submitted attempt
    and its XP are always consistent.

    - Past its deadline (see `is_past_deadline`): graded for the student's
      own review, but earns nothing and does not touch the rating.
    - Untimed: practice. Earns base XP, but cannot set the best score the
      leaderboard ranks by -- with no clock it is effectively open-book.
    - Timed and on time: XP with the bonus, and a candidate best score.
    """
    if simulation.submitted_at is not None and is_past_deadline(simulation, simulation.submitted_at):
        simulation.counts_for_rating = False
        return 0

    simulation.counts_for_rating = bool(simulation.is_timed)
    base = simulation.total_score or 0
    bonus = base // _TIMED_BONUS_DIVISOR if simulation.is_timed and not simulation.time_expired else 0
    xp_earned = base + bonus
    rated_score = base if simulation.counts_for_rating else None

    rating = await db.get(StudentRating, simulation.student_id)
    if rating is None:
        rating = StudentRating(
            student_id=simulation.student_id, total_xp=xp_earned, simulations_completed=1, best_score=rated_score
        )
        db.add(rating)
    else:
        # Incremented in SQL rather than read-modify-write in Python: two
        # different attempts by the same student submitted at once would
        # otherwise both read the old total and one grant would be lost.
        rating.total_xp = StudentRating.total_xp + xp_earned
        rating.simulations_completed = StudentRating.simulations_completed + 1
        if rated_score is not None:
            rating.best_score = case(
                (StudentRating.best_score.is_(None), rated_score),
                (StudentRating.best_score >= rated_score, StudentRating.best_score),
                else_=rated_score,
            )
    rating.last_simulation_at = simulation.submitted_at

    return xp_earned
