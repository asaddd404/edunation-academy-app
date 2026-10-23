"""The demo seed's content must be something the API itself would accept."""

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


def test_ent_bank_covers_quotas_with_every_question_type():
    for subject in SUBJECTS:
        by_type = {}
        for q in subject["questions"]:
            by_type[q["qtype"].value] = by_type.get(q["qtype"].value, 0) + 1
        assert len(subject["questions"]) == 40
        assert set(by_type) == {"single", "multiple", "matching", "short_answer"}
        quotas = subject["quotas"]
        assert by_type["single"] >= quotas["single"] and by_type["multiple"] >= quotas["multiple"]
        assert by_type["matching"] >= quotas["matching"] and by_type["short_answer"] >= quotas["short"]
