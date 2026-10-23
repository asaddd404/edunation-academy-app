"""The demo seed's content must be something the API itself would accept."""

import pytest

from app.core.youtube import youtube_video_id
from app.demo.courses import COURSES
from app.demo.ent_bank import SUBJECTS
from app.seed_demo import validate_content


def test_every_demo_question_passes_the_api_schemas():
    validate_content()  # raises SystemExit listing every problem


def test_every_lesson_has_a_youtube_video_notes_homework_and_a_test():
    for course in COURSES:
        for section in course["sections"]:
            assert section["test"]
            for lesson in section["lessons"]:
                assert youtube_video_id(lesson["video"]), lesson["title"]
                assert lesson["notes"] and lesson["homework"] and lesson["test"], lesson["title"]


@pytest.mark.parametrize("key", ["questions", "questions_kk"])
def test_ent_bank_covers_quotas_with_every_question_type(key):
    """Both languages: a simulation in Kazakh draws only Kazakh questions, so
    each language needs the full quota of every type on its own."""
    for subject in SUBJECTS:
        by_type = {}
        for q in subject[key]:
            by_type[q["qtype"].value] = by_type.get(q["qtype"].value, 0) + 1
        assert len(subject[key]) == 40
        assert set(by_type) == {"single", "multiple", "matching", "short_answer"}
        quotas = subject["quotas"]
        assert by_type["single"] >= quotas["single"] and by_type["multiple"] >= quotas["multiple"]
        assert by_type["matching"] >= quotas["matching"] and by_type["short_answer"] >= quotas["short"]


def test_demo_choices_are_not_all_in_first_position():
    """The specs list the right option first; the seed must shuffle them, or
    every demo answer is "A"."""
    from app.models import Choice, Question
    from app.seed_demo import build_question

    first_correct = 0
    specs = [q for s in SUBJECTS for q in s["questions"] if q.get("choices")]
    for spec in specs:
        q = build_question(spec, Question, Choice, Choice, Choice, 0)
        first_correct += q.choices[0].is_correct
    assert first_correct < len(specs) * 0.5
