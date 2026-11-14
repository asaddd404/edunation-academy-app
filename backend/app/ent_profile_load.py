"""Replaces the question banks of the ЕНТ profile subjects with the
profile-structure banks in app.demo.ent_subjects (Mathematics, Physics,
Chemistry, Biology: 25 single + 5 context + 5 matching + 5 multiple, in
Russian and Kazakh).

For each profile subject, by slug: creates the subject if it is missing,
marks it a profile subject, DELETES every question it has -- and with them,
through the database cascade, those questions' answers inside past
simulations -- and loads the new 80. One transaction: all of it or nothing.

    docker compose ... exec backend python -m app.ent_profile_load            # what it would do
    docker compose ... exec backend python -m app.ent_profile_load --apply    # do it

Take a database backup first.
"""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.core.storage import delete_upload
from app.database import async_session_factory
from app.demo.ent_subjects import PROFILE_SUBJECTS
from app.models.ent_question import EntAnswerVariant, EntChoice, EntLanguage, EntMatchPair, EntQuestion
from app.models.ent_simulation import EntSimulationQuestion
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum, User
from app.seed_demo import STAFF, build_question, validate_content

_STAFF_PHONE = {key: phone for key, phone, *_ in STAFF}


async def _owner_id(db, spec: dict) -> int | None:
    """The subject's teacher from the demo staff list, if that account exists;
    else the first admin -- a subject nobody can edit would be a dead end."""
    phone = _STAFF_PHONE.get(spec["teacher"])
    if phone:
        teacher = await db.scalar(select(User.id).where(User.phone == phone, User.role == RoleEnum.teacher))
        if teacher:
            return teacher
    return await db.scalar(select(User.id).where(User.role == RoleEnum.admin).order_by(User.id).limit(1))


async def run(apply: bool) -> None:
    validate_content()
    async with async_session_factory() as db:
        images: list[str] = []
        for spec in PROFILE_SUBJECTS:
            subject = await db.scalar(select(EntSubject).where(EntSubject.slug == spec["slug"]))
            if subject is None:
                subject = EntSubject(name=spec["name"], slug=spec["slug"], created_by_id=await _owner_id(db, spec))
                db.add(subject)
                await db.flush()
                print(f"+ {spec['name']}: новый предмет")
            old_ids = select(EntQuestion.id).where(EntQuestion.subject_id == subject.id)
            old = await db.scalar(select(func.count()).select_from(old_ids.subquery()))
            answers = await db.scalar(
                select(func.count(EntSimulationQuestion.id)).where(EntSimulationQuestion.question_id.in_(old_ids))
            )
            images += (await db.scalars(
                select(EntQuestion.image_path).where(EntQuestion.subject_id == subject.id, EntQuestion.image_path.is_not(None))
            )).all()
            print(f"  {spec['name']}: удаляется вопросов {old} (ответов в прошлых попытках: {answers}), "
                  f"загружается {len(spec['questions'])} RU + {len(spec['questions_kk'])} KZ")

            await db.execute(delete(EntQuestion).where(EntQuestion.subject_id == subject.id))
            subject.is_profile = True
            subject.is_active = True
            for language, key in ((EntLanguage.ru, "questions"), (EntLanguage.kk, "questions_kk")):
                db.add_all(
                    build_question(q, EntQuestion, EntChoice, EntMatchPair, EntAnswerVariant, i,
                                   subject_id=subject.id, language=language, created_by_id=subject.created_by_id)
                    for i, q in enumerate(spec[key])
                )
        if not apply:
            await db.rollback()
            print("Пробный запуск: ничего не изменено. Запустите с --apply, чтобы применить.")
            return
        await db.commit()
    # Only after the commit, so a failed run never leaves questions pointing at missing files.
    for path in images:
        delete_upload(path)
    print("Готово.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="применить изменения (без флага — пробный запуск)")
    asyncio.run(run(parser.parse_args().apply))
