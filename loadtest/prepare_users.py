"""Creates load-test students and prints their access tokens as JSON.

Run inside the backend container (it needs the app's DB and JWT secret):

    docker compose ... exec -T backend python - < loadtest/prepare_users.py 200 > /tmp/lt.json

Tokens are minted directly instead of logging in through the API: 200
logins from one machine would (correctly) trip LOGIN_BY_IP long before the
test began. Users are +7700900NNNN, approved for every course; re-running
app.seed_demo afterwards removes them along with everything they wrote.
"""

import asyncio
import json
import sys

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Application, ApplicationStatusEnum, Category, EntSubject, Lesson, RoleEnum, Section, User
from app.security import create_access_token, hash_password


async def main(count: int) -> None:
    async with async_session_factory() as db:
        categories = (await db.scalars(select(Category))).all()
        password = hash_password("LoadTest-unused-password")
        users = []
        for i in range(count):
            phone = f"+7700900{i:04d}"
            user = await db.scalar(select(User).where(User.phone == phone))
            if user is None:
                user = User(phone=phone, password_hash=password, first_name="Нагрузка", last_name=f"Тест{i}", role=RoleEnum.student)
                db.add(user)
                await db.flush()
                for c in categories:
                    db.add(Application(student_id=user.id, category_id=c.id, status=ApplicationStatusEnum.approved))
            users.append(user)
        await db.commit()

        first_lessons = []
        for c in categories:
            lesson_id = await db.scalar(
                select(Lesson.id).join(Section).where(Section.category_id == c.id)
                .order_by(Section.order_index, Lesson.order_index).limit(1)
            )
            first_lessons.append(lesson_id)
        lessons = (await db.scalars(select(Lesson.id))).all()
        subjects = (await db.scalars(select(EntSubject.id))).all()

    print(json.dumps({
        "tokens": [create_access_token(u.id, u.role.value) for u in users],
        "categories": [c.id for c in categories],
        "lessons": list(lessons),
        "first_lessons": first_lessons,
        "subjects": list(subjects),
    }))


asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 200))
