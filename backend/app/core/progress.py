from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt


async def get_ordered_lesson_ids(db: AsyncSession, category_id: int) -> list[int]:
    result = await db.execute(
        select(Lesson.id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.category_id == category_id)
        .order_by(Section.order_index, Lesson.order_index)
    )
    return [row[0] for row in result.all()]


async def get_passed_lesson_ids(db: AsyncSession, student_id: int, category_id: int) -> set[int]:
    result = await db.execute(
        select(TestAttempt.lesson_id)
        .join(Lesson, Lesson.id == TestAttempt.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(
            TestAttempt.student_id == student_id,
            Section.category_id == category_id,
            TestAttempt.passed.is_(True),
        )
        .distinct()
    )
    return {row[0] for row in result.all()}


async def get_lessons_without_questions(db: AsyncSession, category_id: int) -> set[int]:
    """Lessons with zero questions are treated as auto-passed for unlock purposes,
    so course authoring in progress doesn't permanently block student progress."""
    has_question = select(Question.id).where(Question.lesson_id == Lesson.id).exists()
    result = await db.execute(
        select(Lesson.id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.category_id == category_id, ~has_question)
    )
    return {row[0] for row in result.all()}


def compute_unlocked_ids(ordered_lesson_ids: list[int], effectively_passed_ids: set[int]) -> set[int]:
    """A lesson is unlocked if it's first in the category-wide order, or the
    lesson immediately before it (in that order) has been passed."""
    unlocked: set[int] = set()
    for index, lesson_id in enumerate(ordered_lesson_ids):
        if index == 0 or ordered_lesson_ids[index - 1] in effectively_passed_ids:
            unlocked.add(lesson_id)
        else:
            break
    return unlocked


async def get_lesson_progress(db: AsyncSession, student_id: int, category_id: int) -> tuple[set[int], set[int]]:
    """Returns (unlocked_lesson_ids, passed_lesson_ids) for a student in a category."""
    ordered = await get_ordered_lesson_ids(db, category_id)
    passed = await get_passed_lesson_ids(db, student_id, category_id)
    auto_passed = await get_lessons_without_questions(db, category_id)
    unlocked = compute_unlocked_ids(ordered, passed | auto_passed)
    return unlocked, passed


async def get_lesson_ids_in_section(db: AsyncSession, section_id: int) -> list[int]:
    result = await db.execute(select(Lesson.id).where(Lesson.section_id == section_id))
    return [row[0] for row in result.all()]


async def get_passed_section_ids(db: AsyncSession, student_id: int, category_id: int) -> set[int]:
    result = await db.execute(
        select(TestAttempt.section_id)
        .join(Section, Section.id == TestAttempt.section_id)
        .where(
            TestAttempt.student_id == student_id,
            Section.category_id == category_id,
            TestAttempt.passed.is_(True),
        )
        .distinct()
    )
    return {row[0] for row in result.all()}


async def is_section_test_unlocked(db: AsyncSession, student_id: int, section_id: int, category_id: int) -> bool:
    """The section test opens once every lesson in that section has been
    passed (or, per get_lessons_without_questions, has no mini-test yet)."""
    lesson_ids = await get_lesson_ids_in_section(db, section_id)
    if not lesson_ids:
        return True
    passed = await get_passed_lesson_ids(db, student_id, category_id)
    auto_passed = await get_lessons_without_questions(db, category_id)
    effectively_passed = passed | auto_passed
    return all(lid in effectively_passed for lid in lesson_ids)
