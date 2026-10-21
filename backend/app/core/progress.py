from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.test_attempt import TestAttempt


async def get_ordered_sections(db: AsyncSession, category_id: int) -> list[tuple[int, list[int]]]:
    """Every section of the category in course order, each with its lesson
    ids in order. Sections without lessons are included: they can still
    carry a test that gates what comes after them."""
    section_ids = (
        await db.scalars(
            select(Section.id)
            .where(Section.category_id == category_id)
            # The ids break ties: order_index is assigned as max()+1, which two
            # concurrent creates can duplicate, and without a total order
            # Postgres may return tied rows differently per query -- flipping
            # which lesson counts as "next" and so which one is unlocked.
            .order_by(Section.order_index, Section.id)
        )
    ).all()
    lessons_by_section: dict[int, list[int]] = {sid: [] for sid in section_ids}
    rows = await db.execute(
        select(Lesson.id, Lesson.section_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.category_id == category_id)
        .order_by(Lesson.order_index, Lesson.id)
    )
    for lesson_id, section_id in rows.all():
        lessons_by_section[section_id].append(lesson_id)
    return [(sid, lessons_by_section[sid]) for sid in section_ids]


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


async def get_sections_with_test(db: AsyncSession, category_id: int) -> set[int]:
    result = await db.execute(
        select(Question.section_id)
        .join(Section, Section.id == Question.section_id)
        .where(Section.category_id == category_id)
        .distinct()
    )
    return {row[0] for row in result.all()}


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


@dataclass(frozen=True)
class CourseProgress:
    unlocked_lesson_ids: set[int]
    passed_lesson_ids: set[int]
    unlocked_test_section_ids: set[int]
    passed_section_ids: set[int]


def compute_progress(
    ordered_sections: list[tuple[int, list[int]]],
    effectively_passed: set[int],
    sections_with_test: set[int],
    passed_sections: set[int],
) -> tuple[set[int], set[int]]:
    """Walks the course in order and returns (unlocked lessons, sections
    whose test is open). This is the single rule for course progression:

    - a lesson opens once every lesson before it is passed (or has no
      mini-test yet) *and* every earlier section test has been passed --
      the end-of-section test is what lets a student into the next section;
    - a section's test opens once everything before it and every lesson in
      it is passed. A section with no lessons therefore opens its test when
      the course reaches it, neither immediately nor never.
    """
    unlocked: set[int] = set()
    tests_open: set[int] = set()
    chain_open = True
    for section_id, lesson_ids in ordered_sections:
        for lesson_id in lesson_ids:
            if chain_open:
                unlocked.add(lesson_id)
            chain_open = chain_open and lesson_id in effectively_passed
        if chain_open:
            tests_open.add(section_id)
        if section_id in sections_with_test and section_id not in passed_sections:
            chain_open = False
    return unlocked, tests_open


async def get_course_progress(db: AsyncSession, student_id: int, category_id: int) -> CourseProgress:
    ordered = await get_ordered_sections(db, category_id)
    passed = await get_passed_lesson_ids(db, student_id, category_id)
    auto_passed = await get_lessons_without_questions(db, category_id)
    sections_with_test = await get_sections_with_test(db, category_id)
    passed_sections = await get_passed_section_ids(db, student_id, category_id)
    unlocked, tests_open = compute_progress(ordered, passed | auto_passed, sections_with_test, passed_sections)
    # A lesson the student has already passed stays open. Gating on section
    # tests is new; without this, a pupil who got ahead before it existed
    # would find their own finished lessons locked behind a test.
    unlocked |= passed
    return CourseProgress(unlocked, passed, tests_open, passed_sections)


async def get_lesson_progress(db: AsyncSession, student_id: int, category_id: int) -> tuple[set[int], set[int]]:
    """Returns (unlocked_lesson_ids, passed_lesson_ids) for a student in a category."""
    progress = await get_course_progress(db, student_id, category_id)
    return progress.unlocked_lesson_ids, progress.passed_lesson_ids


async def is_section_test_unlocked(db: AsyncSession, student_id: int, section_id: int, category_id: int) -> bool:
    progress = await get_course_progress(db, student_id, category_id)
    return section_id in progress.unlocked_test_section_ids
