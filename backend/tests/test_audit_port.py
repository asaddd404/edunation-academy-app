"""Fixes carried over from the October audit (old PRs #1/#2), re-done on
top of the current code. Each test pins one concrete way the app could be
gamed or show a student the wrong thing."""

import pytest

from app.core import video as video_core
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum
from app.security import create_presentation_ticket, create_video_ticket
from tests.test_refresh_cookie import ORIGIN_HEADER, PASSWORD, REFRESH_COOKIE_NAME, _login


# --- sessions --------------------------------------------------------------


async def test_parallel_tab_refresh_does_not_clear_the_new_cookie(client, make_password_user):
    """Tab B arrives with the token tab A just rotated: it must not delete the
    cookie A was given, and it must not get a session of its own either."""
    user = await make_password_user(PASSWORD)
    await _login(client, user)
    shared = client.cookies[REFRESH_COOKIE_NAME]

    assert (await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)).status_code == 200

    client.cookies.set(REFRESH_COOKIE_NAME, shared)
    late = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)
    assert late.status_code == 401
    assert late.headers.get("x-refresh-rotated") == "1"
    assert "set-cookie" not in late.headers


async def test_unknown_refresh_token_still_clears_the_cookie(client):
    client.cookies.set(REFRESH_COOKIE_NAME, "never-issued")
    response = await client.post("/api/v1/auth/refresh", headers=ORIGIN_HEADER)
    assert response.status_code == 401
    assert "x-refresh-rotated" not in response.headers
    assert REFRESH_COOKIE_NAME in response.headers.get("set-cookie", "")


async def test_tickets_are_not_accepted_as_a_session(client, make_user):
    await make_user(RoleEnum.student)
    for ticket in (create_video_ticket(lesson_id=1), create_presentation_ticket(1, "presentations/x.pdf")):
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ticket}"})
        assert response.status_code == 401


# --- video -----------------------------------------------------------------


async def _enrolled_student(db_session, make_user, slug: str):
    student = await make_user(RoleEnum.student)
    category = Category(name=slug, slug=slug, is_active=True)
    db_session.add(category)
    await db_session.flush()
    application = Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.approved)
    db_session.add(application)
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    lesson = Lesson(section_id=section.id, title="Урок", order_index=0)
    db_session.add(lesson)
    await db_session.commit()
    return student, category, application, lesson


@pytest.fixture
def hls(tmp_path, monkeypatch):
    monkeypatch.setattr(video_core, "HLS_DIR", tmp_path)

    def make(lesson_id: int):
        folder = tmp_path / str(lesson_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "master.m3u8").write_text("#EXTM3U\n")
        (folder / "seg0.ts").write_bytes(b"\x47" * 188)

    return make


async def test_video_ticket_is_bound_to_its_student(client, db_session, make_user, hls):
    student, _category, application, lesson = await _enrolled_student(db_session, make_user, "video-bound")
    hls(lesson.id)
    url = f"/api/v1/video/lessons/{lesson.id}"
    client.cookies.set("video_ticket", create_video_ticket(lesson.id, student.id), path=url)

    assert (await client.get(f"{url}/master.m3u8")).status_code == 200
    assert (await client.get(f"{url}/seg0.ts")).status_code == 200

    # Enrollment revoked: the same cookie no longer starts playback.
    application.status = ApplicationStatusEnum.rejected
    await db_session.commit()
    assert (await client.get(f"{url}/master.m3u8")).status_code == 403


async def test_a_ticket_from_before_the_update_still_plays_until_it_expires(client, db_session, make_user, hls):
    _student, _category, _application, lesson = await _enrolled_student(db_session, make_user, "video-legacy")
    hls(lesson.id)
    url = f"/api/v1/video/lessons/{lesson.id}"
    client.cookies.set("video_ticket", create_video_ticket(lesson.id), path=url)
    assert (await client.get(f"{url}/master.m3u8")).status_code == 200


async def test_a_ticket_in_the_url_is_not_accepted(client, db_session, make_user, hls):
    student, _category, _application, lesson = await _enrolled_student(db_session, make_user, "video-query")
    hls(lesson.id)
    ticket = create_video_ticket(lesson.id, student.id)
    response = await client.get(f"/api/v1/video/lessons/{lesson.id}/master.m3u8", params={"token": ticket})
    assert response.status_code == 403


# --- courses ---------------------------------------------------------------


async def test_deactivated_course_closes_its_content(client, db_session, make_user, login_as):
    student, category, _application, lesson = await _enrolled_student(db_session, make_user, "deactivated")
    login_as(student)
    assert (await client.get(f"/api/v1/categories/{category.id}/sections")).status_code == 200

    category.is_active = False
    await db_session.commit()
    assert (await client.get(f"/api/v1/categories/{category.id}/sections")).status_code == 403
    assert (await client.get(f"/api/v1/lessons/{lesson.id}")).status_code == 403


async def test_approved_status_wins_over_an_older_rejection(client, db_session, make_user, login_as):
    student, category, _application, _lesson = await _enrolled_student(db_session, make_user, "status-order")
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.rejected))
    await db_session.commit()
    login_as(student)

    listing = await client.get("/api/v1/categories")
    detail = await client.get(f"/api/v1/categories/{category.id}")

    item = next(c for c in listing.json()["items"] if c["id"] == category.id)
    assert item["my_application_status"] == "approved"
    assert detail.json()["my_application_status"] == "approved"


async def test_cannot_reapply_to_a_course_already_approved(client, db_session, make_user, login_as):
    student, category, _application, _lesson = await _enrolled_student(db_session, make_user, "reapply")
    login_as(student)
    response = await client.post("/api/v1/applications", json={"category_id": category.id})
    assert response.status_code == 409
    assert response.json()["detail"] == "Вы уже записаны на этот курс"


async def test_reapplying_after_a_rejection_still_works(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    category = Category(name="again", slug="again", is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(Application(student_id=student.id, category_id=category.id, status=ApplicationStatusEnum.rejected))
    await db_session.commit()
    login_as(student)
    assert (await client.post("/api/v1/applications", json={"category_id": category.id})).status_code == 201


async def test_switched_off_course_is_hidden_from_students(client, db_session, make_user, login_as):
    student, category, _application, _lesson = await _enrolled_student(db_session, make_user, "hidden")
    category.is_active = False
    await db_session.commit()
    login_as(student)
    assert (await client.get(f"/api/v1/categories/{category.id}")).status_code == 404


# --- activity --------------------------------------------------------------


def test_school_day_rolls_over_at_kazakhstan_midnight(monkeypatch):
    from datetime import datetime, timezone

    from app.core import clock

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # 20:30 UTC on the 1st is already 01:30 on the 2nd in Almaty.
            return datetime(2026, 3, 1, 20, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", FakeDatetime)
    assert clock.school_today().isoformat() == "2026-03-02"


# --- lesson images and homework --------------------------------------------


async def test_deleting_a_lesson_keeps_an_image_another_lesson_uses(client, db_session, make_user, login_as, monkeypatch):
    import json

    from app.core import trash
    from app.models.category import teacher_categories

    deleted: list[str] = []
    monkeypatch.setattr(trash, "delete_upload", lambda path: deleted.append(path))

    teacher = await make_user(RoleEnum.teacher)
    category = Category(name="shared-img", slug="shared-img", is_active=True)
    db_session.add(category)
    await db_session.flush()
    await db_session.execute(teacher_categories.insert().values(teacher_id=teacher.id, category_id=category.id))
    section = Section(category_id=category.id, title="Раздел", order_index=0)
    db_session.add(section)
    await db_session.flush()
    doc = json.dumps({"type": "doc", "content": [{"type": "image", "attrs": {"src": "lesson-content/shared.png"}}]})
    first = Lesson(section_id=section.id, title="Первый", order_index=0, description=doc)
    second = Lesson(section_id=section.id, title="Второй", order_index=1, homework_assignment=doc)
    db_session.add_all([first, second])
    await db_session.commit()
    login_as(teacher)

    # Deleting goes to the trash; files only go when it is emptied for good.
    for lesson in (first, second):
        assert (await client.delete(f"/api/v1/teacher/lessons/{lesson.id}")).status_code == 204
    assert deleted == []

    assert (await client.delete(f"/api/v1/teacher/trash/lesson/{first.id}")).status_code == 204
    assert "lesson-content/shared.png" not in deleted  # the second lesson (in the trash) still shows it

    assert (await client.delete(f"/api/v1/teacher/trash/lesson/{second.id}")).status_code == 204
    assert "lesson-content/shared.png" in deleted  # now nothing does


async def test_homework_text_has_a_ceiling(client, db_session, make_user, login_as):
    student, _category, _application, lesson = await _enrolled_student(db_session, make_user, "hw-long")
    login_as(student)
    response = await client.post(f"/api/v1/lessons/{lesson.id}/homework", data={"text_answer": "а" * 20_001})
    assert response.status_code == 422
    ok = await client.post(f"/api/v1/lessons/{lesson.id}/homework", data={"text_answer": "Ответ"})
    assert ok.status_code == 201, ok.text


# --- ENT results -----------------------------------------------------------


async def test_ent_answer_key_hidden_for_unanswered_questions(client, db_session, make_user, login_as):
    from tests.test_course_tests_and_xp import _open_ent_simulation

    student = await make_user(RoleEnum.student)
    simulation, _question = await _open_ent_simulation(db_session, student)
    login_as(student)

    result = (await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": []})).json()
    answer = result["answers"][0]
    assert answer["answer_revealed"] is False
    assert answer["match_pairs"] == [] and answer["answer_variants"] == []
    assert not any(c["is_correct"] for c in answer["choices"])


async def test_ent_answer_key_shown_for_answered_questions(client, db_session, make_user, login_as):
    from tests.test_account_and_exam_rules import _correct_answer
    from tests.test_course_tests_and_xp import _open_ent_simulation

    student = await make_user(RoleEnum.student)
    simulation, question = await _open_ent_simulation(db_session, student)
    login_as(student)
    wrong = {"question_id": question.id, "pairs": {k: "nope" for k in (await _correct_answer(client, simulation.id, question))["pairs"]}}

    result = (await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": [wrong]})).json()
    answer = result["answers"][0]
    assert answer["answer_revealed"] is True
    assert len(answer["match_pairs"]) >= 2
