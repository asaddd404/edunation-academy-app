"""DB-backed coverage for `POST /teacher/ent/questions/bulk-delete`.

The two things worth pinning down here are exactly the two ways a bulk
delete can go wrong for a teacher: it reaches into a bank that isn't yours,
or a stale click re-submits ids that are already gone. Everything else
(batch-size cap, image cleanup) is straightforward enough to leave to
reading the code.
"""
from sqlalchemy import select

from app.models.ent_question import EntLanguage, EntQuestion, EntQuestionType
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum


async def _subject_with_questions(db_session, owner, count: int):
    subject = EntSubject(name="Test Subject", slug=f"test-subject-{owner.id}", created_by_id=owner.id)
    db_session.add(subject)
    await db_session.flush()

    questions = []
    for i in range(count):
        question = EntQuestion(
            subject_id=subject.id,
            qtype=EntQuestionType.single,
            text=f"Question {i}",
            language=EntLanguage.ru,
            max_score=1,
            order_index=i,
            created_by_id=owner.id,
        )
        db_session.add(question)
        questions.append(question)
    await db_session.flush()
    return subject, questions


async def test_bulk_delete_rejects_foreign_question_and_deletes_nothing(client, db_session, make_user, login_as):
    teacher_a = await make_user(RoleEnum.teacher)
    teacher_b = await make_user(RoleEnum.teacher)
    subject, questions = await _subject_with_questions(db_session, teacher_a, count=2)
    await db_session.commit()

    login_as(teacher_b)
    response = await client.post(
        "/api/v1/teacher/ent/questions/bulk-delete",
        json={"question_ids": [q.id for q in questions]},
    )

    assert response.status_code == 403
    remaining = (
        await db_session.scalars(select(EntQuestion).where(EntQuestion.subject_id == subject.id))
    ).all()
    assert len(remaining) == 2


async def test_bulk_delete_rejects_whole_batch_when_one_id_is_foreign(client, db_session, make_user, login_as):
    """A batch mixing the caller's own questions with one foreign id must
    reject the entire request -- not delete the owned ones and skip the
    rest. Partial success here is exactly the ambiguous outcome a bulk
    action shouldn't produce."""
    teacher_a = await make_user(RoleEnum.teacher)
    teacher_b = await make_user(RoleEnum.teacher)
    subject_a, questions_a = await _subject_with_questions(db_session, teacher_a, count=2)
    subject_b, questions_b = await _subject_with_questions(db_session, teacher_b, count=1)
    await db_session.commit()

    login_as(teacher_a)
    response = await client.post(
        "/api/v1/teacher/ent/questions/bulk-delete",
        json={"question_ids": [q.id for q in questions_a] + [questions_b[0].id]},
    )

    assert response.status_code == 403
    remaining_a = (
        await db_session.scalars(select(EntQuestion).where(EntQuestion.subject_id == subject_a.id))
    ).all()
    remaining_b = (
        await db_session.scalars(select(EntQuestion).where(EntQuestion.subject_id == subject_b.id))
    ).all()
    assert len(remaining_a) == 2
    assert len(remaining_b) == 1


async def test_bulk_delete_is_idempotent_on_already_deleted_ids(client, db_session, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    _, questions = await _subject_with_questions(db_session, teacher, count=3)
    await db_session.commit()
    ids = [q.id for q in questions]

    login_as(teacher)
    first = await client.post("/api/v1/teacher/ent/questions/bulk-delete", json={"question_ids": ids})
    assert first.status_code == 200
    first_body = first.json()
    assert sorted(first_body["deleted"]) == sorted(ids)
    assert first_body["failed"] == []

    second = await client.post("/api/v1/teacher/ent/questions/bulk-delete", json={"question_ids": ids})
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["deleted"] == []
    assert sorted(f["id"] for f in second_body["failed"]) == sorted(ids)
    assert all(f["reason"] == "not_found" for f in second_body["failed"])


async def test_bulk_delete_rejects_batch_over_500(client, make_user, login_as):
    teacher = await make_user(RoleEnum.teacher)
    login_as(teacher)

    response = await client.post(
        "/api/v1/teacher/ent/questions/bulk-delete",
        json={"question_ids": list(range(1, 502))},
    )

    assert response.status_code == 400
