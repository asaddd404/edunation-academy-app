"""app.ent_profile_load: replaces the profile subjects' banks in place."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import ent_profile_load
from app.models.ent_question import EntChoice, EntQuestion, EntQuestionType
from app.models.ent_simulation import EntSimulation, EntSimulationQuestion
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum
from tests.test_ent_profile_structure import _enrolled_student, _start


async def test_load_replaces_old_questions_and_creates_missing_subjects(
    client, db_session, make_user, login_as, test_engine, monkeypatch
):
    await make_user(RoleEnum.admin)
    student = await _enrolled_student(db_session, make_user)
    physics = EntSubject(name="Физика", slug="fizika", single_choice_count=13)
    db_session.add(physics)
    await db_session.flush()
    old = EntQuestion(subject_id=physics.id, qtype=EntQuestionType.single, text="старый", max_score=1)
    old.choices = [EntChoice(text="a", is_correct=True), EntChoice(text="b", is_correct=False)]
    db_session.add(old)
    await db_session.flush()
    simulation = EntSimulation(student_id=student.id, is_timed=False)
    db_session.add(simulation)
    await db_session.flush()
    db_session.add(EntSimulationQuestion(simulation_id=simulation.id, question_id=old.id, order_index=0))
    await db_session.commit()
    old_id, simulation_id = old.id, simulation.id
    login_as(student)

    monkeypatch.setattr(ent_profile_load, "async_session_factory", async_sessionmaker(test_engine, expire_on_commit=False))

    await ent_profile_load.run(apply=False)
    assert await db_session.get(EntQuestion, old_id, populate_existing=True) is not None

    await ent_profile_load.run(apply=True)

    db_session.expire_all()
    assert await db_session.scalar(select(EntQuestion).where(EntQuestion.id == old_id)) is None
    assert await db_session.scalar(select(func.count(EntSimulationQuestion.id)).where(
        EntSimulationQuestion.simulation_id == simulation_id)) == 0
    subjects = {s.slug: s for s in (await db_session.scalars(select(EntSubject))).all()}
    assert {"matematika", "fizika", "himiya", "biologiya"} <= subjects.keys()
    for slug in ("matematika", "fizika", "himiya", "biologiya"):
        subject = subjects[slug]
        assert subject.is_profile and subject.is_active
        count = await db_session.scalar(select(func.count(EntQuestion.id)).where(EntQuestion.subject_id == subject.id))
        assert count == 80
        for language in ("ru", "kk"):
            response = await client.post("/api/v1/ent/simulations", json={
                "subject_ids": [subject.id], "is_timed": False, "language": language})
            assert response.status_code == 201, (slug, language, response.json())
            assert len(response.json()["questions"]) == 40
            # One attempt at a time (MAX_UNFINISHED_SIMULATIONS).
            await client.post(f"/api/v1/ent/simulations/{response.json()['id']}/submit", json={"answers": []})
