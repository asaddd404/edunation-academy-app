"""Profile subjects: the fixed 40-question ЕНТ structure, the question format
it accepts, context questions, and matching with more answers than prompts."""

from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.ent_question import EntAnswerVariant, EntChoice, EntMatchPair, EntQuestion, EntQuestionType
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum


def _choices(count: int, correct: set[int]) -> list[dict]:
    return [{"text": f"вариант {i}", "is_correct": i in correct} for i in range(count)]


SINGLE = {"qtype": "single", "text": "Вопрос", "max_score": 1, "choices": _choices(4, {0})}
CONTEXT = {**SINGLE, "qtype": "context", "context_text": "Абзац текста, о котором вопрос."}
MULTIPLE = {"qtype": "multiple", "text": "Выберите верные", "max_score": 2, "choices": _choices(6, {1, 4})}
MATCHING = {
    "qtype": "matching",
    "text": "Сопоставьте",
    "max_score": 2,
    "match_pairs": [
        {"prompt_text": "Куб", "answer_text": "a^3"},
        {"prompt_text": "Квадрат", "answer_text": "a^2"},
        {"prompt_text": None, "answer_text": "2a"},
        {"prompt_text": "", "answer_text": "4a"},
    ],
}


async def _profile_subject(client, slug: str) -> int:
    subject = (await client.post("/api/v1/teacher/ent/subjects", json={"name": slug, "slug": slug})).json()
    patched = await client.patch(f"/api/v1/teacher/ent/subjects/{subject['id']}", json={"is_profile": True})
    assert patched.status_code == 200 and patched.json()["is_profile"] is True
    return subject["id"]


def _create(client, subject_id: int, payload: dict):
    return client.post(f"/api/v1/teacher/ent/subjects/{subject_id}/questions", json=payload)


async def test_a_profile_subject_accepts_questions_in_the_ent_format(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    subject_id = await _profile_subject(client, "profile-format-ok")

    for payload in (SINGLE, CONTEXT, MULTIPLE, MATCHING):
        response = await _create(client, subject_id, payload)
        assert response.status_code == 201, (payload["qtype"], response.json())

    context = (await _create(client, subject_id, CONTEXT)).json()
    assert context["context_text"] == CONTEXT["context_text"]


async def test_a_profile_subject_refuses_questions_outside_the_format(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    subject_id = await _profile_subject(client, "profile-format-bad")

    refused = [
        {**SINGLE, "choices": _choices(5, {0})},
        {**SINGLE, "max_score": 2},
        {**MULTIPLE, "choices": _choices(4, {0, 1})},
        {"qtype": "short_answer", "text": "Ответ?", "max_score": 1, "answer_variants": ["42"]},
    ]
    for payload in refused:
        assert (await _create(client, subject_id, payload)).status_code == 422, payload


async def test_question_rules_that_hold_for_every_subject(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    subject = (await client.post("/api/v1/teacher/ent/subjects", json={"name": "Обычный", "slug": "plain-rules"})).json()

    # One correct answer is now a valid "multiple"; four is too many.
    assert (await _create(client, subject["id"], {**MULTIPLE, "choices": _choices(6, {2})})).status_code == 201
    assert (await _create(client, subject["id"], {**MULTIPLE, "choices": _choices(6, {0, 1, 2, 3})})).status_code == 422
    # A context question needs its passage.
    assert (await _create(client, subject["id"], {**CONTEXT, "context_text": "  "})).status_code == 422
    # Distractors do not count towards the two pairs a matching question needs.
    one_pair = {**MATCHING, "match_pairs": [MATCHING["match_pairs"][0], MATCHING["match_pairs"][2], MATCHING["match_pairs"][3]]}
    assert (await _create(client, subject["id"], one_pair)).status_code == 422


async def test_editing_into_a_profile_subject_is_checked_too(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    subject_id = await _profile_subject(client, "profile-edit")
    question = (await _create(client, subject_id, SINGLE)).json()

    response = await client.patch(f"/api/v1/teacher/ent/questions/{question['id']}", json={**SINGLE, "choices": _choices(3, {0})})

    assert response.status_code == 422


async def test_a_teacher_cannot_add_questions_to_another_teachers_subject(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    subject_id = await _profile_subject(client, "profile-owner")

    login_as(await make_user(RoleEnum.teacher))
    assert (await _create(client, subject_id, SINGLE)).status_code == 403
    assert (await client.patch(f"/api/v1/teacher/ent/subjects/{subject_id}", json={"is_profile": False})).status_code == 403


async def test_course_questions_refuse_the_context_type(client, make_user, login_as, db_session):
    from tests.test_teacher_questions import _course  # noqa: PLC0415 -- reuse its fixtures

    teacher = await make_user(RoleEnum.teacher)
    _, lesson = await _course(db_session, teacher, "context-course")
    login_as(teacher)

    response = await client.post(f"/api/v1/teacher/lessons/{lesson.id}/questions", json=CONTEXT)

    assert response.status_code == 422


# ── Generator ────────────────────────────────────────────────────────────


def _add(db_session, subject_id: int, qtype: EntQuestionType, *, options: int = 4, max_score: int = 1, **extra) -> None:
    question = EntQuestion(subject_id=subject_id, qtype=qtype, text=f"{qtype.value}", max_score=max_score, **extra)
    if qtype == EntQuestionType.matching:
        question.match_pairs = [EntMatchPair(prompt_text=f"p{i}", answer_text=f"a{i}", order_index=i) for i in range(2)]
    elif qtype == EntQuestionType.short_answer:
        question.answer_variants = [EntAnswerVariant(text="1")]
    else:
        question.choices = [EntChoice(text=f"c{i}", is_correct=i == 0, order_index=i) for i in range(options)]
    db_session.add(question)


async def _enrolled_student(db_session, make_user):
    student = await make_user(RoleEnum.student)
    category = Category(name="c", slug=f"profile-course-{student.id}", is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    await db_session.commit()
    return student


async def _profile_bank(db_session, slug: str, *, singles: int = 25) -> EntSubject:
    subject = EntSubject(name=slug, slug=slug, is_profile=True,
                         # Quotas are ignored for a profile subject.
                         single_choice_count=3, short_answer_count=3)
    db_session.add(subject)
    await db_session.flush()
    for _ in range(singles):
        _add(db_session, subject.id, EntQuestionType.single)
    for _ in range(5):
        _add(db_session, subject.id, EntQuestionType.context, context_text="Текст")
        _add(db_session, subject.id, EntQuestionType.matching, max_score=2)
        _add(db_session, subject.id, EntQuestionType.multiple, options=6, max_score=2)
    # Not in the profile format: never drawn.
    for _ in range(5):
        _add(db_session, subject.id, EntQuestionType.single, options=5)
        _add(db_session, subject.id, EntQuestionType.multiple, options=4, max_score=2)
        _add(db_session, subject.id, EntQuestionType.short_answer)
    await db_session.commit()
    return subject


def _start(client, subject_id: int):
    return client.post("/api/v1/ent/simulations", json={"subject_ids": [subject_id], "is_timed": False, "questions_per_subject": 10})


async def test_a_profile_simulation_is_40_questions_in_the_ent_order(client, db_session, make_user, login_as):
    subject = await _profile_bank(db_session, "profile-gen")
    login_as(await _enrolled_student(db_session, make_user))

    response = await _start(client, subject.id)

    assert response.status_code == 201, response.json()
    questions = response.json()["questions"]
    assert [q["qtype"] for q in questions] == ["single"] * 25 + ["context"] * 5 + ["matching"] * 5 + ["multiple"] * 5
    assert all(len(q["choices"]) == 4 for q in questions[:30])
    assert all(len(q["choices"]) == 6 for q in questions[35:])
    assert all(q["context_text"] == "Текст" for q in questions[25:30])
    assert sum(q["max_score"] for q in questions) == 50


async def test_a_short_profile_bank_names_the_missing_block(client, db_session, make_user, login_as):
    subject = await _profile_bank(db_session, "profile-short", singles=24)
    login_as(await _enrolled_student(db_session, make_user))

    response = await _start(client, subject.id)

    assert response.status_code == 422
    assert "нужно 25, доступно 24" in response.json()["detail"]


# ── Matching with distractors ────────────────────────────────────────────


async def _distractor_simulation(client, db_session, make_user, login_as):
    subject = EntSubject(name="Матем", slug="distractor-subject", single_choice_count=0, matching_count=1)
    db_session.add(subject)
    await db_session.flush()
    question = EntQuestion(subject_id=subject.id, qtype=EntQuestionType.matching, text="Пары", max_score=2)
    question.match_pairs = [
        EntMatchPair(prompt_text="Куб", answer_text="a^3", order_index=0),
        EntMatchPair(prompt_text="Квадрат", answer_text="a^2", order_index=1),
        EntMatchPair(prompt_text=None, answer_text="2a", order_index=2),
        EntMatchPair(prompt_text=None, answer_text="4a", order_index=3),
    ]
    db_session.add(question)
    await db_session.commit()
    login_as(await _enrolled_student(db_session, make_user))
    exam = (await _start(client, subject.id)).json()
    return exam, question


async def test_distractors_are_offered_as_answers_but_not_asked_about(client, db_session, make_user, login_as):
    exam, _ = await _distractor_simulation(client, db_session, make_user, login_as)
    q = exam["questions"][0]

    assert [p["text"] for p in q["match_prompts"]] == ["Куб", "Квадрат"]
    assert sorted(a["text"] for a in q["match_answers"]) == ["2a", "4a", "a^2", "a^3"]


async def test_matching_with_distractors_is_graded_2_1_0(client, db_session, make_user, login_as):
    exam, question = await _distractor_simulation(client, db_session, make_user, login_as)
    q = exam["questions"][0]
    token = {a["text"]: a["id"] for a in q["match_answers"]}
    cube, square = question.match_pairs[0].id, question.match_pairs[1].id

    # Right for one prompt, a distractor for the other: partial credit.
    answer = {"question_id": question.id, "pairs": {str(cube): token["a^3"], str(square): token["4a"]}}
    result = (await client.post(f"/api/v1/ent/simulations/{exam['id']}/submit", json={"answers": [answer]})).json()

    assert result["total_score"] == 1 and result["max_score"] == 2
    distractors = [p for p in result["answers"][0]["match_pairs"] if p["prompt_text"] is None]
    assert sorted(p["answer_text"] for p in distractors) == ["2a", "4a"]


async def test_matching_with_distractors_all_right_is_full_marks(client, db_session, make_user, login_as):
    exam, question = await _distractor_simulation(client, db_session, make_user, login_as)
    token = {a["text"]: a["id"] for a in exam["questions"][0]["match_answers"]}
    cube, square = question.match_pairs[0].id, question.match_pairs[1].id

    answer = {"question_id": question.id, "pairs": {str(cube): token["a^3"], str(square): token["a^2"]}}
    result = (await client.post(f"/api/v1/ent/simulations/{exam['id']}/submit", json={"answers": [answer]})).json()

    assert result["total_score"] == 2


# ── Structure view for the teacher ───────────────────────────────────────


async def test_structure_counts_each_block_per_language(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    subject = await _profile_bank(db_session, "profile-structure-view", singles=24)
    subject.created_by_id = teacher.id
    await db_session.commit()
    login_as(teacher)

    body = (await client.get(f"/api/v1/teacher/ent/subjects/{subject.id}/structure")).json()

    assert body["is_profile"] is True
    blocks = {b["qtype"]: b for b in body["blocks"]}
    assert [b["qtype"] for b in body["blocks"]] == ["single", "context", "matching", "multiple"]
    assert (blocks["single"]["first_number"], blocks["single"]["last_number"]) == (1, 25)
    assert (blocks["multiple"]["first_number"], blocks["multiple"]["last_number"]) == (36, 40)
    assert blocks["single"]["have"] == {"ru": 24, "kk": 0} and blocks["single"]["needed"] == 25
    # The five-option singles and four-option multiples are not drawn.
    assert blocks["single"]["off_format"]["ru"] == 5 and blocks["multiple"]["off_format"]["ru"] == 5
    assert body["unused"]["ru"] == 5  # short answers


async def test_question_list_filters_by_type(client, make_user, login_as):
    login_as(await make_user(RoleEnum.teacher))
    subject_id = await _profile_subject(client, "profile-list-filter")
    await _create(client, subject_id, SINGLE)
    await _create(client, subject_id, MATCHING)

    page = (await client.get(f"/api/v1/teacher/ent/subjects/{subject_id}/questions?qtype=matching")).json()

    assert [q["qtype"] for q in page["items"]] == ["matching"]
