"""Opaque ids for the answer side of a matching question.

A matching row (MatchPair / EntMatchPair) stores its own correct pairing:
the prompt and the answer live on the same row, so the grader counts a
prompt as matched when the student picked *that same row's* answer. Sending
both sides to the client under the row id therefore hands over the key --
"pair prompt 41 with the answer whose id is 41" -- and shuffling the list
hides nothing from anyone who opens DevTools.

So the answer side goes out under a token instead: an HMAC of the row id,
keyed with a server secret and scoped to the attempt being sat. The client
cannot invert it, cannot line it up with a prompt id, and a token learned in
one attempt means nothing in the next. Nothing is stored -- the server
recomputes the same tokens at submit time and translates the answer back to
row ids before grading, so the grader and the stored `answer_data` keep
speaking row ids exactly as before.
"""

import hashlib
import hmac

from app.config import settings

# Domain-separated from the JWT signing use of the same secret: a token
# minted here can never collide with, or be replayed as, anything else
# derived from it.
_KEY = hmac.new(settings.jwt_secret.encode(), b"match-answer-token/v1", hashlib.sha256).digest()

# 64 bits: far beyond guessing within the handful of options a question has,
# and short enough to keep the payload readable.
_TOKEN_HEX_CHARS = 16


def ent_scope(simulation_id: int) -> str:
    return f"ent:{simulation_id}"


def attempt_scope(attempt_id: int) -> str:
    return f"attempt:{attempt_id}"


def match_answer_token(scope: str, pair_id: int) -> str:
    digest = hmac.new(_KEY, f"{scope}:{pair_id}".encode(), hashlib.sha256).hexdigest()
    return digest[:_TOKEN_HEX_CHARS]


def decode_match_answer(pair_ids: list[int], scope: str, answer_data: dict | None) -> dict | None:
    """Rewrites a submitted matching answer from tokens back to row ids.

    A token that matches no row of this question becomes -1, which no row
    has -- the grader then scores that prompt as wrong, the same as any
    other invalid reference, instead of failing the whole submission.
    """
    if not answer_data or not isinstance(answer_data.get("pairs"), dict):
        return answer_data
    by_token = {match_answer_token(scope, pid): pid for pid in pair_ids}
    decoded = {
        prompt_id: by_token.get(token, -1) if isinstance(token, str) else -1
        for prompt_id, token in answer_data["pairs"].items()
    }
    return {**answer_data, "pairs": decoded}
