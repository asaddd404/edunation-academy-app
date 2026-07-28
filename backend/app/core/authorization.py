from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatusEnum
from app.models.category import teacher_categories
from app.models.user import User


async def assert_teacher_owns_category(db: AsyncSession, teacher: User, category_id: int) -> None:
    result = await db.execute(
        select(teacher_categories.c.category_id).where(
            teacher_categories.c.teacher_id == teacher.id,
            teacher_categories.c.category_id == category_id,
        )
    )
    if result.first() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Вы не назначены на эту категорию")


async def assert_can_decide_application(db: AsyncSession, teacher: User, application: Application) -> None:
    if application.status != ApplicationStatusEnum.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Заявка уже рассмотрена")
    await assert_teacher_owns_category(db, teacher, application.category_id)
