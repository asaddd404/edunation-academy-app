from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatusEnum
from app.models.category import teacher_categories
from app.models.ent_question import EntQuestion
from app.models.ent_subject import EntSubject
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.user import RoleEnum, User


async def assert_teacher_owns_category(db: AsyncSession, teacher: User, category_id: int) -> None:
    if teacher.role == RoleEnum.admin:
        return
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


async def assert_owns_ent_subject(db: AsyncSession, teacher: User, subject_id: int) -> EntSubject:
    """Admins may manage any ЕНТ subject; teachers only the ones they created."""
    subject = await db.get(EntSubject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Предмет не найден")
    if teacher.role != RoleEnum.admin and subject.created_by_id != teacher.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Вы не создавали этот предмет")
    return subject


async def get_subject_id_for_ent_question(db: AsyncSession, question_id: int) -> int:
    subject_id = await db.scalar(select(EntQuestion.subject_id).where(EntQuestion.id == question_id))
    if subject_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вопрос не найден")
    return subject_id


async def assert_owns_ent_question(db: AsyncSession, teacher: User, question_id: int) -> int:
    subject_id = await get_subject_id_for_ent_question(db, question_id)
    await assert_owns_ent_subject(db, teacher, subject_id)
    return subject_id


async def assert_teacher_owns_question(db: AsyncSession, teacher: User, question_id: int) -> int:
    """A lesson mini-test or section-test question belongs to exactly one
    lesson or section (never both), whose category determines ownership."""
    question = await db.get(Question, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вопрос не найден")
    if question.lesson_id is not None:
        return await assert_teacher_owns_lesson(db, teacher, question.lesson_id)
    return await assert_teacher_owns_section(db, teacher, question.section_id)


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


async def assert_student_has_any_course_access(db: AsyncSession, student: User) -> None:
    """The ЕНТ simulator is a perk for enrolled students, not a standalone
    product -- a student with zero approved applications shouldn't be able
    to use it either."""
    approved = await db.scalar(
        select(Application.id).where(
            Application.student_id == student.id,
            Application.status == ApplicationStatusEnum.approved,
        )
    )
    if approved is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "ЕНТ-тренажёр доступен только после одобрения хотя бы одной заявки на курс",
        )
