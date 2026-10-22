"""Teacher CRUD for lesson and section test questions.

Covers what a teacher does in the course builder -- all four question types,
edits, deletes -- plus who must be turned away, and the two properties an
edit has to keep: validation errors come back as 422 rather than a database
500, and editing a question keeps its option ids, so a student mid-attempt
is not silently marked wrong.
"""

import pytest
from sqlalchemy import func, select

from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson
from app.models.question import Choice, MatchPair, Question
from app.models.section import Section
from app.models.user import RoleEnum

SINGLE = {
    "qtype": "single",
    "text": "Столица Казахстана?",
    "max_score": 1,
    "choices": [{"text": "Астана", "is_correct": True}, {"text": "Алматы", "is_correct": False}],
}
MULTIPLE = {
    "qtype": "multiple",
    "text": "Простые числа",
    "max_score": 2,
    "choices": [
        {"text": "2", "is_correct": True},
        {"text": "3", "is_correct": True},
        {"text": "4", "is_correct": False},
    ],
}
MATCHING = {
    "qtype": "matching",
    "text": "Сопоставьте",
    "max_score": 2,
    "match_pairs": [{"prompt_text": "H2O", "answer_text": "вода"}, {"prompt_text": "NaCl", "answer_text": "соль"}],
}
SHORT = {"qtype": "short_answer", "text": "2+2", "max_score": 1, "answer_variants": ["4", " четыре "]}


async def _course(db_session, teacher, slug: str):
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add(lesson)
    await db_session.commit()
    return section, lesson


# --- create / list ----------------------------------------------------------


@pytest.mark.parametrize("payload", [SINGLE, MULTIPLE, MATCHING, SHORT], ids=lambda p: p["qtype"])
async def test_teacher_creates_each_question_type(client, db_session, make_user, login_as, payload):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, f"create-{payload['qtype']}")
    login_as(teacher)

    response = await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["qtype"] == payload["qtype"]
    assert body["lesson_id"] == lesson.id and body["section_id"] is None
    assert [c["text"] for c in body["choices"]] == [c["text"] for c in payload.get("choices", [])]
    assert [c["is_correct"] for c in body["choices"]] == [c["is_correct"] for c in payload.get("choices", [])]
    assert [(p["prompt_text"], p["answer_text"]) for p in body["match_pairs"]] == [
        (p["prompt_text"], p["answer_text"]) for p in payload.get("match_pairs", [])
    ]
    # Accepted short answers are stored trimmed; blank ones are dropped.
    assert [v["text"] for v in body["answer_variants"]] == [v.strip() for v in payload.get("answer_variants", [])]


async def test_list_returns_questions_in_creation_order_with_answers(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, "list-order")
    login_as(teacher)
    for payload in (SINGLE, MATCHING, SHORT):
        await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=payload)

    body = (await client.get(f"/api/v1/teacher/lessons/{lesson.id}/questions")).json()

    assert [q["qtype"] for q in body] == ["single", "matching", "short_answer"]
    assert [q["order_index"] for q in body] == [0, 1, 2]
    # The teacher view, unlike the student one, carries the key.
    assert any(c["is_correct"] for c in body[0]["choices"])


async def test_section_test_questions_have_their_own_endpoints(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    section, lesson = await _course(db_session, teacher, "section-q")
    login_as(teacher)

    created = await client.post(f"/api/v1/teacher/sections/{section.id}/questions", json=SINGLE)

    assert created.status_code == 201
    assert created.json()["section_id"] == section.id
    assert len((await client.get(f"/api/v1/teacher/sections/{section.id}/questions")).json()) == 1
    assert (await client.get(f"/api/v1/teacher/lessons/{lesson.id}/questions")).json() == []


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {**SINGLE, "choices": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]},
        {**SINGLE, "choices": [{"text": "only", "is_correct": True}]},
        {**MULTIPLE, "choices": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}]},
        {**MULTIPLE, "max_score": 1},
        {**MATCHING, "match_pairs": MATCHING["match_pairs"][:1]},
        {**SHORT, "answer_variants": ["  "]},
        {**SINGLE, "match_pairs": MATCHING["match_pairs"]},
        {**SINGLE, "text": ""},
    ],
    ids=[
        "single-two-correct",
        "single-one-option",
        "multiple-one-correct",
        "multiple-one-point",
        "matching-one-pair",
        "short-blank",
        "single-with-pairs",
        "empty-text",
    ],
)
async def test_invalid_questions_are_rejected(client, db_session, make_user, login_as, payload):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, f"invalid-{id(payload)}")
    login_as(teacher)

    response = await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=payload)

    assert response.status_code == 422
    assert await db_session.scalar(select(func.count(Question.id)).where(Question.lesson_id == lesson.id)) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {**SINGLE, "text": "x" * 1001},
        {**SINGLE, "choices": [{"text": "x" * 501, "is_correct": True}, SINGLE["choices"][1]]},
        {**MATCHING, "match_pairs": [{"prompt_text": "x" * 301, "answer_text": "a"}, MATCHING["match_pairs"][1]]},
        {**SHORT, "answer_variants": ["x" * 301]},
    ],
    ids=["text", "choice", "pair", "variant"],
)
async def test_text_longer_than_its_column_is_a_422_not_a_500(client, db_session, make_user, login_as, payload):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, f"too-long-{id(payload)}")
    login_as(teacher)

    response = await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=payload)

    assert response.status_code == 422


# --- update / delete --------------------------------------------------------


@pytest.mark.parametrize("method", ["put", "patch"])
async def test_update_replaces_the_question(client, db_session, make_user, login_as, method):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, f"update-{method}")
    login_as(teacher)
    question_id = (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=SINGLE)).json()["id"]

    response = await client.request(method.upper(), f"/api/v1/teacher/questions/{question_id}", json=MATCHING)

    assert response.status_code == 200
    body = response.json()
    assert body["qtype"] == "matching"
    assert body["choices"] == []
    assert len(body["match_pairs"]) == 2
    leftover = await db_session.scalar(select(func.count(Choice.id)).where(Choice.question_id == question_id))
    assert leftover == 0


async def test_editing_keeps_option_ids(client, db_session, make_user, login_as):
    """Fixing a typo must not renumber the options a student may be
    answering right now."""
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, "stable-ids")
    login_as(teacher)
    created = (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=MULTIPLE)).json()
    before = [c["id"] for c in created["choices"]]

    edited = {
        **MULTIPLE,
        "text": "Простые числа (исправлено)",
        "choices": [*MULTIPLE["choices"], {"text": "5", "is_correct": True}],
    }
    after = (await client.put(f"/api/v1/teacher/questions/{created['id']}", json=edited)).json()

    assert [c["id"] for c in after["choices"]][:3] == before
    assert [c["text"] for c in after["choices"]] == ["2", "3", "4", "5"]

    shrunk = (await client.put(f"/api/v1/teacher/questions/{created['id']}", json=MULTIPLE)).json()
    assert [c["id"] for c in shrunk["choices"]] == before
    assert await db_session.scalar(select(func.count(Choice.id)).where(Choice.question_id == created["id"])) == 3


async def test_editing_matching_keeps_pair_ids(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, "stable-pairs")
    login_as(teacher)
    created = (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=MATCHING)).json()

    edited = {**MATCHING, "match_pairs": [{"prompt_text": "H₂O", "answer_text": "вода"}, MATCHING["match_pairs"][1]]}
    after = (await client.put(f"/api/v1/teacher/questions/{created['id']}", json=edited)).json()

    assert [p["id"] for p in after["match_pairs"]] == [p["id"] for p in created["match_pairs"]]
    assert after["match_pairs"][0]["prompt_text"] == "H₂O"


async def test_delete_removes_question_and_its_options(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, "delete")
    login_as(teacher)
    question_id = (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=MATCHING)).json()["id"]

    response = await client.delete(f"/api/v1/teacher/questions/{question_id}")

    assert response.status_code == 204
    assert await db_session.get(Question, question_id) is None
    assert await db_session.scalar(select(func.count(MatchPair.id)).where(MatchPair.question_id == question_id)) == 0
    assert (await client.delete(f"/api/v1/teacher/questions/{question_id}")).status_code == 404


# --- who may do it ----------------------------------------------------------


async def test_teacher_cannot_touch_questions_outside_their_categories(client, db_session, make_user, login_as):
    owner = await make_user(RoleEnum.teacher)
    other = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, owner, "foreign-owner")
    login_as(owner)
    question_id = (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=SINGLE)).json()["id"]

    login_as(other)
    assert (await client.get(f"/api/v1/teacher/lessons/{lesson.id}/questions")).status_code == 403
    assert (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=SINGLE)).status_code == 403
    assert (await client.put(f"/api/v1/teacher/questions/{question_id}", json=SHORT)).status_code == 403
    assert (await client.delete(f"/api/v1/teacher/questions/{question_id}")).status_code == 403

    stored = await db_session.get(Question, question_id)
    await db_session.refresh(stored)
    assert stored.text == SINGLE["text"]
    assert await db_session.scalar(select(func.count(Question.id)).where(Question.lesson_id == lesson.id)) == 1


async def test_student_cannot_use_teacher_endpoints(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    student = await make_user(RoleEnum.student)
    _, lesson = await _course(db_session, teacher, "student-blocked")

    login_as(student)
    assert (await client.get(f"/api/v1/teacher/lessons/{lesson.id}/questions")).status_code == 403
    assert (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=SINGLE)).status_code == 403


async def test_admin_manages_any_course(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    admin = await make_user(RoleEnum.admin)
    _, lesson = await _course(db_session, teacher, "admin-any")

    login_as(admin)
    response = await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=SINGLE)

    assert response.status_code == 201


async def test_missing_lesson_is_404(client, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)

    assert (await client.post("/api/v1/teacher/lessons/999999/questions", json=SINGLE)).status_code == 404
    assert (await client.put("/api/v1/teacher/questions/999999", json=SINGLE)).status_code == 404
