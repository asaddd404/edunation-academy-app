from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ent_simulation import EntSimulation
from app.models.student_rating import StudentRating

# 1 ENT point = 1 XP, plus a 20% bonus for finishing a *timed* simulation
# within the limit — rewards choosing the harder, exam-realistic mode over
# always going untimed. Untimed attempts and timed-but-overrun attempts earn
# the base amount only.
_TIMED_BONUS_DIVISOR = 5


async def apply_simulation_xp(db: AsyncSession, simulation: EntSimulation) -> int:
    """Grants XP for a just-graded simulation and updates the student's
    running rating. Must be called inside the same transaction as the
    grading commit, before it — so a submitted attempt and its XP are
    always consistent."""
    base = simulation.total_score or 0
    bonus = base // _TIMED_BONUS_DIVISOR if simulation.is_timed and not simulation.time_expired else 0
    xp_earned = base + bonus

    rating = await db.get(StudentRating, simulation.student_id)
    if rating is None:
        # total_xp/simulations_completed default to 0 at INSERT time, but
        # that server-side default isn't reflected on this Python object
        # until a flush — set them explicitly so the += below works.
        rating = StudentRating(student_id=simulation.student_id, total_xp=0, simulations_completed=0)
        db.add(rating)

    rating.total_xp += xp_earned
    rating.simulations_completed += 1
    rating.best_score = max(rating.best_score or 0, base)
    rating.last_simulation_at = simulation.submitted_at

    return xp_earned
