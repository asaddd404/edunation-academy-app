from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatusEnum
from app.models.category import teacher_categories
from app.models.lesson import Lesson
from app.models.section import Section
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


async def get_category_id_for_section(db: AsyncSession, section_id: int) -> int:
    category_id = await db.scalar(select(Section.category_id).where(Section.id == section_id))
    if category_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")
    return category_id


async def get_category_id_for_lesson(db: AsyncSession, lesson_id: int) -> int:
    category_id = await db.scalar(
        select(Section.category_id).join(Lesson, Lesson.section_id == Section.id).where(Lesson.id == lesson_id)
    )
    if category_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")
    return category_id


async def assert_teacher_owns_section(db: AsyncSession, teacher: User, section_id: int) -> int:
    category_id = await get_category_id_for_section(db, section_id)
    await assert_teacher_owns_category(db, teacher, category_id)
    return category_id


async def assert_teacher_owns_lesson(db: AsyncSession, teacher: User, lesson_id: int) -> int:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_teacher_owns_category(db, teacher, category_id)
    return category_id


async def assert_student_has_category_access(db: AsyncSession, student: User, category_id: int) -> None:
    approved = await db.scalar(
        select(Application.id).where(
            Application.student_id == student.id,
            Application.category_id == category_id,
            Application.status == ApplicationStatusEnum.approved,
        )
    )
    if approved is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой категории")
