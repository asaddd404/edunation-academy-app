from app.models.ent_question import EntQuestion, EntQuestionType
from app.models.question import Question

# Shared by both the ЕНТ question bank and course lesson/section tests --
# both models expose the same shape (qtype, max_score, choices, match_pairs,
# answer_variants), reusing the same EntQuestionType enum, so one grader
# serves both.
GradeableQuestion = EntQuestion | Question

# Answer payload shapes submitted by the student, per qtype:
#   single:       {"choice_id": <int>}
#   multiple:     {"choice_ids": [<int>, ...]}
#   matching:     {"pairs": {"<pair_id>": <chosen_pair_id>, ...}}
#   short_answer: {"text": "<str>"}
#
# Scoring rule (2/1/0), confirmed for multiple/matching: full credit
# (max_score) if every part is correct, 1 point if partially correct,
# 0 otherwise. single/short_answer are all-or-nothing — schema validation
# keeps their max_score at 1 (or 2 for a profile subject), never awarding
# a partial 1 for those types. Any reference to a choice/pair id that
# doesn't belong to the question is treated as an invalid answer (0),
# rather than raising, so one bad entry doesn't fail an entire submission.


def _normalize_text(text: str) -> str:
    return " ".join(text.strip().lower().split())


def grade_single(question: GradeableQuestion, answer_data: dict | None) -> int:
    if not answer_data:
        return 0
    choice_id = answer_data.get("choice_id")
    if not isinstance(choice_id, int):
        return 0
    valid_ids = {c.id for c in question.choices}
    if choice_id not in valid_ids:
        return 0
    correct_ids = {c.id for c in question.choices if c.is_correct}
    return question.max_score if choice_id in correct_ids else 0


def grade_multiple(question: GradeableQuestion, answer_data: dict | None) -> int:
    if not answer_data:
        return 0
    raw_ids = answer_data.get("choice_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return 0
    valid_ids = {c.id for c in question.choices}
    selected = {cid for cid in raw_ids if isinstance(cid, int)}
    if not selected or not selected.issubset(valid_ids):
        return 0

    correct_ids = {c.id for c in question.choices if c.is_correct}
    if selected == correct_ids:
        return question.max_score
    if selected.issubset(correct_ids):
        return 1
    return 0


def grade_matching(question: GradeableQuestion, answer_data: dict | None) -> int:
    if not answer_data:
        return 0
    raw_pairs = answer_data.get("pairs")
    if not isinstance(raw_pairs, dict) or not raw_pairs:
        return 0

    valid_pair_ids = {p.id for p in question.match_pairs}
    if not valid_pair_ids:
        return 0

    correct_count = 0
    seen_prompt_ids: set[int] = set()
    for prompt_id_raw, chosen_answer_id in raw_pairs.items():
        try:
            prompt_id = int(prompt_id_raw)
        except (TypeError, ValueError):
            continue
        if prompt_id not in valid_pair_ids or prompt_id in seen_prompt_ids:
            continue
        seen_prompt_ids.add(prompt_id)
        # Each ent_match_pairs row encodes its own correct pairing, so a
        # correct match means the student picked this same row's id as
        # the answer for this prompt.
        if isinstance(chosen_answer_id, int) and chosen_answer_id == prompt_id:
            correct_count += 1

    if correct_count == len(valid_pair_ids):
        return question.max_score
    if correct_count > 0:
        return 1
    return 0


def grade_short_answer(question: GradeableQuestion, answer_data: dict | None) -> int:
    if not answer_data:
        return 0
    text = answer_data.get("text")
    if not isinstance(text, str) or not text.strip():
        return 0
    normalized = _normalize_text(text)
    accepted = {_normalize_text(v.text) for v in question.answer_variants}
    return question.max_score if normalized in accepted else 0


_GRADERS = {
    EntQuestionType.single: grade_single,
    EntQuestionType.multiple: grade_multiple,
    EntQuestionType.matching: grade_matching,
    EntQuestionType.short_answer: grade_short_answer,
}


def grade_question(question: GradeableQuestion, answer_data: dict | None) -> int:
    return _GRADERS[question.qtype](question, answer_data)
