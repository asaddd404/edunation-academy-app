"""ЕНТ questions some attempt already drew are archived, not deleted:
past results keep them, the bank and new attempts no longer see them."""

from sqlalchemy import select

from app.models.ent_question import EntQuestion, EntQuestionType
from app.models.ent_simulation import EntSimulation
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum
from tests.test_course_tests_and_xp import _open_ent_simulation


async def _own_subject(db_session, teacher, question):
    subject = await db_session.get(EntSubject, question.subject_id)
    subject.created_by_id = teacher.id
    await db_session.commit()
    return subject


async def test_deleting_a_drawn_question_archives_it_and_keeps_past_results(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    teacher = await make_user(RoleEnum.teacher)
    simulation, question = await _open_ent_simulation(db_session, student)
    subject = await _own_subject(db_session, teacher, question)

    login_as(student)
    assert (await client.post(f"/api/v1/ent/simulations/{simulation.id}/submit", json={"answers": []})).status_code == 200

    login_as(teacher)
    assert (await client.delete(f"/api/v1/teacher/ent/questions/{question.id}")).status_code == 204
    await db_session.refresh(question)
    assert question.archived_at is not None  # still there

    bank = (await client.get(f"/api/v1/teacher/ent/subjects/{subject.id}/questions")).json()
    assert question.id not in [q["id"] for q in (bank["items"] if isinstance(bank, dict) else bank)]
    # Archived: no longer editable or deletable through the bank.
    assert (await client.delete(f"/api/v1/teacher/ent/questions/{question.id}")).status_code == 404

    login_as(student)
    result = (await client.get(f"/api/v1/ent/simulations/{simulation.id}/result")).json()
    assert [a["question_id"] for a in result["answers"]] == [question.id]


async def test_a_question_nobody_drew_is_really_deleted(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    subject = EntSubject(name="Химия", slug="chem-archive", created_by_id=teacher.id)
    db_session.add(subject)
    await db_session.flush()
    question = EntQuestion(subject_id=subject.id, qtype=EntQuestionType.short_answer, text="?", max_score=1)
    db_session.add(question)
    await db_session.commit()
    login_as(teacher)
    assert (await client.delete(f"/api/v1/teacher/ent/questions/{question.id}")).status_code == 204
    assert await db_session.scalar(select(EntQuestion.id).where(EntQuestion.id == question.id)) is None


async def test_bulk_delete_archives_drawn_questions_too(client, db_session, make_user, login_as):
    student = await make_user(RoleEnum.student)
    teacher = await make_user(RoleEnum.teacher)
    _simulation, question = await _open_ent_simulation(db_session, student)
    await _own_subject(db_session, teacher, question)
    login_as(teacher)
    r = await client.post("/api/v1/teacher/ent/questions/bulk-delete", json={"question_ids": [question.id]})
    assert r.status_code == 200 and r.json()["deleted"] == [question.id]
    await db_session.refresh(question)
    assert question.archived_at is not None
    assert await db_session.scalar(select(EntSimulation.id).where(EntSimulation.student_id == student.id)) is not None
