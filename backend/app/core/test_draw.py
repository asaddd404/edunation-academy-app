"""Which questions a lesson/section test attempt is made of.

A teacher can give a test a bank larger than one attempt
(`questions_per_attempt`). Each attempt then draws its own selection, so
retaking a failed test means answering different questions rather than
re-submitting the same sheet with one answer changed -- which, with the
score shown after every attempt, was a way to recover the key.
"""

import random


def draw_question_ids(
    pool_ids: list[int],
    per_attempt: int | None,
    previous_ids: list[int] | None,
    rng: random.Random,
) -> list[int]:
    """An attempt's questions, in display order.

    Without `per_attempt` nothing changes from before: every question, in
    the teacher's order. With it, questions the previous attempt did not show
    come first and are topped up from the previous attempt's only when the
    bank is too small; the order is shuffled, and when the selection is
    necessarily the same set it is never served in the same order twice.
    """
    if not per_attempt:
        return list(pool_ids)
    count = min(per_attempt, len(pool_ids))
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
