"""ЕНТ multiple choice (questions 36-40), 2 points:
2 -- every right answer and nothing else; 1 -- some right answers and nothing
wrong, or every right answer plus one extra; 0 -- anything worse."""

import pytest

from app.core.question_scoring import grade_question
from app.models.ent_question import EntChoice, EntQuestion, EntQuestionType
from app.models.question import Choice, Question

# Six options; 1, 2 and 3 are right.
RIGHT = {1, 2, 3}


def _ent() -> EntQuestion:
    q = EntQuestion(qtype=EntQuestionType.multiple, max_score=2)
    q.choices = [EntChoice(id=i, is_correct=i in RIGHT) for i in range(1, 7)]
    return q


@pytest.mark.parametrize(
    ("picked", "score"),
    [
        ({1, 2, 3}, 2),  # all right, nothing extra
        ({1, 2}, 1),  # not all found, nothing wrong
        ({1}, 1),
        ({1, 2, 3, 4}, 1),  # all right plus one extra
        ({1, 2, 3, 4, 5}, 0),  # two extras
        ({1, 2, 4}, 0),  # one missed and one wrong
        ({4}, 0),
        ({4, 5, 6}, 0),
        (set(), 0),
    ],
)
def test_ent_multiple_partial_credit(picked, score):
    assert grade_question(_ent(), {"choice_ids": sorted(picked)} if picked else None) == score


def test_single_right_answer_plus_one_extra_is_partial():
    q = EntQuestion(qtype=EntQuestionType.multiple, max_score=2)
    q.choices = [EntChoice(id=i, is_correct=i == 1) for i in range(1, 7)]
    assert grade_question(q, {"choice_ids": [1]}) == 2
    assert grade_question(q, {"choice_ids": [1, 2]}) == 1
    assert grade_question(q, {"choice_ids": [2]}) == 0


def test_course_tests_keep_their_stricter_rule():
    q = Question(qtype=EntQuestionType.multiple, max_score=2)
    q.choices = [Choice(id=i, is_correct=i in RIGHT) for i in range(1, 7)]
    assert grade_question(q, {"choice_ids": [1, 2, 3, 4]}) == 0
    assert grade_question(q, {"choice_ids": [1, 2]}) == 1
