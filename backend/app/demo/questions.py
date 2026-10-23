"""Compact question specs shared by the course tests and the ЕНТ bank."""

from app.models.ent_question import EntQuestionType


def S(text: str, options: list, correct: int, score: int = 1) -> dict:
    """Single choice: exactly one correct option."""
    return {"qtype": EntQuestionType.single, "text": text, "max_score": score,
            "choices": [(str(o), i == correct) for i, o in enumerate(options)]}


def M(text: str, options: list, correct: list[int]) -> dict:
    """Multiple choice: two or more correct options, 2 points with partial credit."""
    return {"qtype": EntQuestionType.multiple, "text": text, "max_score": 2,
            "choices": [(str(o), i in correct) for i, o in enumerate(options)]}


def P(text: str, pairs: list[tuple[str, str]]) -> dict:
    """Matching: each (prompt, answer) row is its own correct pairing."""
    return {"qtype": EntQuestionType.matching, "text": text, "max_score": 2, "pairs": pairs}


def T(text: str, variants: list[str]) -> dict:
    """Short answer: any of `variants` is accepted (case and spacing ignored)."""
    return {"qtype": EntQuestionType.short_answer, "text": text, "max_score": 1, "variants": variants}
