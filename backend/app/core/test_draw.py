"""Which questions a lesson/section test attempt is made of.

A teacher can give a test a bank larger than one attempt
(`questions_per_attempt`). Each attempt then draws its own selection, so
retaking a failed test means answering different questions rather than
re-submitting the same sheet with one answer changed -- which, with the
score shown after every attempt, used to be a way to recover the key.
"""

import random


def draw_question_ids(
    pool_ids: list[int],
    per_attempt: int | None,
    previous_ids: list[int] | None,
    rng: random.Random,
) -> list[int]:
    """Draws an attempt's questions, in display order.

    Questions the previous attempt did not show are preferred, and only
    topped up from the previous attempt's when the bank is too small to
    avoid them. Whatever the bank size, the order is reshuffled, and when the
    selection is necessarily the same set it is never served in the same
    order twice in a row.
    """
    count = len(pool_ids) if not per_attempt else min(per_attempt, len(pool_ids))
    previous = set(previous_ids or [])

    fresh = [qid for qid in pool_ids if qid not in previous]
    seen = [qid for qid in pool_ids if qid in previous]
    rng.shuffle(fresh)
    rng.shuffle(seen)
    chosen = (fresh + seen)[:count]
    rng.shuffle(chosen)

    if previous_ids and len(chosen) > 1 and chosen == list(previous_ids):
        chosen = chosen[1:] + chosen[:1]
    return chosen


def attempt_rng(attempt_id: int) -> random.Random:
    """Seeded by the attempt, so reloading the page mid-test shows the same
    option order instead of reshuffling under the student's answers."""
    return random.Random(f"test-attempt:{attempt_id}")
