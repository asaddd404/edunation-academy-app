"""API tests for auto-checked homework (app/api/v1/homework_auto.py)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core import storage
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.homework_auto import HomeworkAttempt
from app.models.lesson import Lesson
from app.models.notification import Notification
from app.models.section import Section
from app.models.user import RoleEnum

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
async def course(db_session, make_user):
    """A category with one lesson (no mini-test, so it's unlocked), its
    teacher, and two enrolled students."""
    teacher = await make_user(RoleEnum.teacher)
    s1 = await make_user(RoleEnum.student)
    s2 = await make_user(RoleEnum.student)
    category = Category(name="hw", slug="hw-auto", is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    for s in (s1, s2):
        db_session.add(Application(student_id=s.id, category_id=category.id, status=ApplicationStatusEnum.approved))
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add(lesson)
    await db_session.commit()
    return {"teacher": teacher, "s1": s1, "s2": s2, "lesson": lesson}


async def _add(client, lesson_id, ttype, prompt, data, points=1):
    r = await client.post(f"/api/v1/teacher/lessons/{lesson_id}/auto-homework/tasks", json={"type": ttype, "prompt": prompt, "data": data, "points": points})
    assert r.status_code == 201, r.text
    return r.json()


async def _settings(client, lesson_id, **kw):
    body = {"opens_at": None, "deadline": None, "time_limit_minutes": None, "max_attempts": 3, "tasks_per_student": None}
    body.update(kw)
    r = await client.patch(f"/api/v1/teacher/lessons/{lesson_id}/auto-homework/settings", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _basic_homework(client, login_as, course):
    login_as(course["teacher"])
    lid = course["lesson"].id
    gaps = await _add(client, lid, "gaps", "Вставьте", {"text": "Абай родился в [1845] году в [Семипалатинской|Семей] области"}, 2)
    single = await _add(client, lid, "single", "2+2?", {"options": [{"text": "4", "correct": True}, {"text": "5"}]})
    short = await _add(client, lid, "short", "2x=16, x=?", {"answers": ["8"]})
    return lid, gaps, single, short


def _answers_for(attempt, gaps_answers, single_text, short_text):
    out = {}
    for t in attempt["tasks"]:
        if t["type"] == "gaps":
            out[str(t["id"])] = {"gaps": gaps_answers}
        elif t["type"] == "single":
            out[str(t["id"])] = {"option": next(o["id"] for o in t["options"] if o["text"] == single_text)}
        elif t["type"] == "short":
            out[str(t["id"])] = {"text": short_text}
    return out


# ── teacher constructor ─────────────────────────────────────────────────────


async def test_teacher_builds_reorders_and_duplicates(client, login_as, course):
    lid, gaps, single, short = await _basic_homework(client, login_as, course)
    r = await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework")
    assert [t["id"] for t in r.json()["tasks"]] == [gaps["id"], single["id"], short["id"]]

    r = await client.put(f"/api/v1/teacher/lessons/{lid}/auto-homework/order", json={"task_ids": [short["id"], gaps["id"], single["id"]]})
    assert [t["id"] for t in r.json()] == [short["id"], gaps["id"], single["id"]]
    # A stale list (missing a task) is refused, not half-applied.
    r = await client.put(f"/api/v1/teacher/lessons/{lid}/auto-homework/order", json={"task_ids": [short["id"]]})
    assert r.status_code == 409

    r = await client.post(f"/api/v1/teacher/auto-homework/tasks/{single['id']}/duplicate")
    copy = r.json()
    assert copy["id"] != single["id"]
    assert {o["id"] for o in copy["data"]["options"]}.isdisjoint({o["id"] for o in single["data"]["options"]})
    r = await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework")
    ids = [t["id"] for t in r.json()["tasks"]]
    assert ids.index(copy["id"]) == ids.index(single["id"]) + 1


async def test_invalid_task_gets_a_readable_message(client, login_as, course):
    login_as(course["teacher"])
    r = await client.post(
        f"/api/v1/teacher/lessons/{course['lesson'].id}/auto-homework/tasks", json={"type": "gaps", "prompt": "", "data": {"text": "нет скобок"}}
    )
    assert r.status_code == 422
    assert "пропуск" in r.json()["detail"]


async def test_other_teacher_and_students_cannot_edit(client, login_as, course, make_user):
    lid, gaps, *_ = await _basic_homework(client, login_as, course)
    login_as(await make_user(RoleEnum.teacher))
    assert (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework")).status_code == 403
    assert (await client.delete(f"/api/v1/teacher/auto-homework/tasks/{gaps['id']}")).status_code == 403
    login_as(course["s1"])
    assert (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework")).status_code == 403


# ── student flow ────────────────────────────────────────────────────────────


async def test_start_hides_keys_and_submit_grades(client, login_as, course):
    lid, *_ = await _basic_homework(client, login_as, course)
    login_as(course["s1"])
    state = (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()
    assert state["has_homework"] and state["can_start"] and state["attempts_left"] == 3

    attempt = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert "1845" not in str(attempt["tasks"]) and "Семей" not in str(attempt["tasks"])
    assert "correct" not in str(attempt["tasks"])
    # Starting again resumes the same sitting.
    again = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert again["id"] == attempt["id"]

    answers = _answers_for(attempt, ["1845", "семей"], "4", "9")
    r = await client.put(f"/api/v1/auto-homework/attempts/{attempt['id']}/answers", json={"answers": answers, "away_count": 1})
    assert r.status_code == 200
    resumed = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert resumed["answers"] == answers

    result = (await client.post(f"/api/v1/auto-homework/attempts/{attempt['id']}/submit", json={"answers": answers})).json()
    assert result["result"]["auto_earned"] == 3.0 and result["result"]["auto_max"] == 4.0
    assert result["result"]["grade"] == 75
    assert result["attempts_left"] == 2
    # Before the key opens the student sees no per-task verdicts.
    assert result["reveal"] is False and result["review"] is None
    assert (await client.post(f"/api/v1/auto-homework/attempts/{attempt['id']}/submit", json={"answers": {}})).status_code == 409


async def test_attempt_limit_and_best_attempt_counts(client, login_as, course):
    lid, *_ = await _basic_homework(client, login_as, course)
    login_as(course["teacher"])
    await _settings(client, lid, max_attempts=2)
    login_as(course["s1"])
    a1 = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    await client.post(f"/api/v1/auto-homework/attempts/{a1['id']}/submit", json={"answers": _answers_for(a1, ["1845", "Семей"], "4", "8")})
    a2 = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    final = (await client.post(f"/api/v1/auto-homework/attempts/{a2['id']}/submit", json={"answers": {}})).json()
    assert final["result"]["grade"] == 100  # the better first attempt counts
    assert final["attempts_left"] == 0 and final["can_start"] is False
    assert (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).status_code == 409
    # No deadline and no attempts left: the key opens for this student.
    assert final["reveal"] is True and final["review"]


async def test_time_limit_grades_only_what_was_saved_in_time(client, login_as, course, db_session):
    lid, *_ = await _basic_homework(client, login_as, course)
    login_as(course["teacher"])
    await _settings(client, lid, time_limit_minutes=20)
    login_as(course["s1"])
    attempt = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert attempt["expires_at"] is not None
    saved = _answers_for(attempt, ["1845", ""], "5", "")
    await client.put(f"/api/v1/auto-homework/attempts/{attempt['id']}/answers", json={"answers": saved})

    row = await db_session.get(HomeworkAttempt, attempt["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await db_session.commit()

    late = _answers_for(attempt, ["1845", "Семей"], "4", "8")
    r = await client.put(f"/api/v1/auto-homework/attempts/{attempt['id']}/answers", json={"answers": late})
    assert r.status_code == 409
    state = (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()
    assert state["result"]["auto_earned"] == 1.0  # one gap, saved in time


async def test_settings_change_moves_open_attempts_and_add_time(client, login_as, course, db_session):
    lid, *_ = await _basic_homework(client, login_as, course)
    login_as(course["s1"])
    attempt = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert attempt["expires_at"] is None
    login_as(course["teacher"])
    await _settings(client, lid, time_limit_minutes=10)
    row = await db_session.get(HomeworkAttempt, attempt["id"])
    await db_session.refresh(row)
    first = row.expires_at
    assert first is not None
    r = await client.post(f"/api/v1/teacher/lessons/{lid}/auto-homework/add-time", json={"minutes": 10})
    assert r.json()["updated"] == 1
    await db_session.refresh(row)
    assert (row.expires_at - first) == timedelta(minutes=10)


async def test_opening_date_and_deadline_and_extension(client, login_as, course):
    lid, *_ = await _basic_homework(client, login_as, course)
    now = datetime.now(timezone.utc)
    login_as(course["teacher"])
    await _settings(client, lid, opens_at=_iso(now + timedelta(days=1)), deadline=_iso(now + timedelta(days=2)))
    login_as(course["s1"])
    state = (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()
    assert state["phase"] == "not_open" and not state["can_start"]
    assert (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).status_code == 409

    login_as(course["teacher"])
    await _settings(client, lid, deadline=_iso(now - timedelta(hours=1)))
    login_as(course["s1"])
    assert (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()["phase"] == "closed"
    assert (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).status_code == 409

    login_as(course["teacher"])
    r = await client.post(
        f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/extension", json={"until": _iso(now + timedelta(days=1))}
    )
    assert r.status_code == 200
    login_as(course["s1"])
    attempt = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    # The sitting ends at the personal deadline.
    assert datetime.fromisoformat(attempt["expires_at"]) <= now + timedelta(days=1, seconds=5)
    # The other student is still locked out.
    login_as(course["s2"])
    assert (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).status_code == 409


async def test_key_is_revealed_only_after_every_extension(client, login_as, course, db_session):
    lid, *_ = await _basic_homework(client, login_as, course)
    now = datetime.now(timezone.utc)
    login_as(course["teacher"])
    await _settings(client, lid, deadline=_iso(now + timedelta(hours=1)))
    login_as(course["s2"])
    a = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    await client.post(f"/api/v1/auto-homework/attempts/{a['id']}/submit", json={"answers": {}})
    login_as(course["teacher"])
    await client.post(f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/extension", json={"until": _iso(now + timedelta(days=3))})
    await _settings(client, lid, deadline=_iso(now - timedelta(minutes=1)))
    login_as(course["s2"])
    state = (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()
    assert state["phase"] == "closed"
    assert state["reveal"] is False, "s1 still has days left -- the key must stay closed for everyone"
    assert (await client.post(f"/api/v1/lessons/{lid}/auto-homework/practice", json={"answers": {}})).status_code == 409

    login_as(course["teacher"])
    await client.post(f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/extension", json={"until": None})
    login_as(course["s2"])
    state = (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()
    assert state["reveal"] is True
    review = state["review"]
    gaps_block = next(b for b in review if b["task"]["type"] == "gaps")
    assert gaps_block["correct"]["gaps"][0] == ["1845"]

    # «Работа над ошибками»: checked, nothing stored.
    tid = gaps_block["task"]["id"]
    r = await client.post(f"/api/v1/lessons/{lid}/auto-homework/practice", json={"answers": {str(tid): {"gaps": ["1845", "Семей"]}}})
    assert r.json()["results"][str(tid)]["correct"] is True
    assert (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()["result"]["auto_earned"] == 0


async def test_each_student_gets_a_fixed_variant(client, login_as, course):
    login_as(course["teacher"])
    lid = course["lesson"].id
    for i in range(6):
        await _add(client, lid, "short", f"Вопрос {i}", {"answers": [str(i)]})
    await _settings(client, lid, tasks_per_student=3, max_attempts=None)
    login_as(course["s1"])
    first = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert len(first["tasks"]) == 3
    await client.post(f"/api/v1/auto-homework/attempts/{first['id']}/submit", json={"answers": {}})
    second = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert [t["id"] for t in second["tasks"]] == [t["id"] for t in first["tasks"]]


async def test_locked_or_foreign_lesson_is_refused(client, login_as, course, make_user):
    lid, *_ = await _basic_homework(client, login_as, course)
    login_as(await make_user(RoleEnum.student))  # not enrolled
    assert (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).status_code == 403
    login_as(course["s1"])
    a = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    login_as(course["s2"])  # someone else's attempt
    assert (await client.post(f"/api/v1/auto-homework/attempts/{a['id']}/submit", json={"answers": {}})).status_code == 404


# ── manual tasks, decisions ─────────────────────────────────────────────────


async def test_essay_is_graded_by_criteria_and_notifies(client, login_as, course, db_session):
    login_as(course["teacher"])
    lid = course["lesson"].id
    short = await _add(client, lid, "short", "x?", {"answers": ["8"]}, 2)
    essay = await _add(client, lid, "essay", "Почему?", {"min_words": 3, "criteria": [{"text": "Объяснение", "points": 6}, {"text": "Пример", "points": 2}]})
    assert essay["points"] == 8
    login_as(course["s1"])
    a = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    res = (
        await client.post(
            f"/api/v1/auto-homework/attempts/{a['id']}/submit",
            json={"answers": {str(short["id"]): {"text": "8"}, str(essay["id"]): {"text": "потому что так"}}},
        )
    ).json()
    assert res["result"]["manual_pending"] is True and res["result"]["grade"] is None

    login_as(course["teacher"])
    rows = (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework/results")).json()
    assert next(r for r in rows["rows"] if r["student"]["id"] == course["s1"].id)["state"] == "manual_pending"
    crit = essay["data"]["criteria"][0]["id"]
    r = await client.post(f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/manual", json={"task_id": essay["id"], "criteria": [crit]})
    assert r.json()["result"]["grade"] == 80  # (2 + 6) / 10
    note = await db_session.scalar(select(Notification).where(Notification.user_id == course["s1"].id))
    assert note is not None and "80/100" in note.message
    r = await client.post(f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/manual", json={"task_id": essay["id"], "earned": 99})
    assert r.status_code == 422


async def test_zero_edit_undo_and_retake(client, login_as, course):
    lid, *_ = await _basic_homework(client, login_as, course)
    login_as(course["teacher"])
    await _settings(client, lid, max_attempts=1)
    login_as(course["s1"])
    a = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    await client.post(f"/api/v1/auto-homework/attempts/{a['id']}/submit", json={"answers": _answers_for(a, ["1845", "Семей"], "4", "8")})

    login_as(course["teacher"])
    base = f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/decision"
    assert (await client.post(base, json={"action": "zero", "comment": "списал"})).json()["result"]["grade"] == 0
    assert (await client.post(base, json={"action": "undo"})).json()["result"]["grade"] == 100
    assert (await client.post(base, json={"action": "edit"})).status_code == 422
    assert (await client.post(base, json={"action": "edit", "grade": 40})).json()["result"]["grade"] == 40

    r = await client.post(base, json={"action": "retake"})
    assert r.json()["decision"] == "retake" and r.json()["result"] is None
    login_as(course["s1"])
    state = (await client.get(f"/api/v1/lessons/{lid}/auto-homework")).json()
    assert state["attempts_left"] == 1 and state["can_start"]
    # Undo is possible until the student starts again.
    login_as(course["teacher"])
    assert (await client.post(base, json={"action": "undo"})).json()["result"]["grade"] == 100
    await client.post(base, json={"action": "retake"})
    login_as(course["s1"])
    await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")
    login_as(course["teacher"])
    assert (await client.post(base, json={"action": "undo"})).status_code == 409


async def test_shared_wrong_answers_are_flagged_and_can_be_dismissed(client, login_as, course):
    login_as(course["teacher"])
    lid = course["lesson"].id
    await _add(client, lid, "gaps", "", {"text": "[a] [b] [c]"}, 3)
    for student in (course["s1"], course["s2"]):
        login_as(student)
        a = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
        tid = a["tasks"][0]["id"]
        await client.post(f"/api/v1/auto-homework/attempts/{a['id']}/submit", json={"answers": {str(tid): {"gaps": ["a", "зебра", "жираф"]}}})
    login_as(course["teacher"])
    res = (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework/results")).json()
    assert res["summary"]["flagged"] == 2
    assert all("Одинаковые неправильные ответы" in r["flags"][0] for r in res["rows"])
    await client.post(f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}/decision", json={"action": "keep"})
    res = (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework/results")).json()
    flagged = {r["student"]["id"] for r in res["rows"] if r["flags"]}
    assert flagged == {course["s2"].id}

    problems = (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework/problems")).json()["items"]
    top = problems[0]
    assert top["percent"] == 100 and top["common_wrong"] in ("зебра", "жираф") and top["item_label"].startswith("Пропуск")


async def test_file_task_upload_and_teacher_download(client, login_as, course, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(storage, "HOMEWORK_DIR", tmp_path / "homework")
    login_as(course["teacher"])
    lid = course["lesson"].id
    task = await _add(client, lid, "file", "Фото решения", {}, 5)
    login_as(course["s1"])
    a = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    # A file answer can't be forged through the answers endpoint.
    await client.put(f"/api/v1/auto-homework/attempts/{a['id']}/answers", json={"answers": {str(task["id"]): {"file_path": "../../x", "file_name": "x"}}})
    r = await client.post(f"/api/v1/auto-homework/attempts/{a['id']}/files/{task['id']}", files={"file": ("photo.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["file_kind"] == "image"
    resumed = (await client.post(f"/api/v1/lessons/{lid}/auto-homework/start")).json()
    assert resumed["answers"][str(task["id"])] == {"file_name": "photo.png"}  # no server path leaks
    await client.post(f"/api/v1/auto-homework/attempts/{a['id']}/submit", json={"answers": {}})
    login_as(course["teacher"])
    r = await client.get(f"/api/v1/teacher/auto-homework/attempts/{a['id']}/files/{task['id']}")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    detail = (await client.get(f"/api/v1/teacher/lessons/{lid}/auto-homework/students/{course['s1'].id}")).json()
    assert detail["latest"][0]["has_file"] is True
