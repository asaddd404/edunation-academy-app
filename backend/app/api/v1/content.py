from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_student_has_category_access, get_category_id_for_lesson
from app.core.progress import get_lesson_progress
from app.database import get_db
from app.deps import require_role
from app.models.homework import HomeworkSubmission
from app.models.lesson import Lesson
from app.models.question import Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.homework import HomeworkSubmissionOut
from app.schemas.lesson import LessonDetailOut
from app.schemas.section import SectionOut

router = APIRouter(tags=["content"], dependencies=[Depends(require_role(RoleEnum.student))])


@router.get("/categories/{category_id}/sections", response_model=list[SectionOut])
async def list_sections(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> list[SectionOut]:
    await assert_student_has_category_access(db, student, category_id)

    sections = (
        await db.scalars(
            select(Section)
            .where(Section.category_id == category_id)
            .options(selectinload(Section.lessons))
            .order_by(Section.order_index)
        )
    ).all()

    unlocked, passed = await get_lesson_progress(db, student.id, category_id)

    result = []
    for section in sections:
        out = SectionOut.model_validate(section)
        for lesson_out, lesson in zip(out.lessons, section.lessons):
            lesson_out.is_unlocked = lesson.id in unlocked
            lesson_out.is_passed = lesson.id in passed
        result.append(out)
    return result


@router.get("/lessons/{lesson_id}", response_model=LessonDetailOut)
async def get_lesson(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> LessonDetailOut:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)

    lesson = await db.scalar(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(selectinload(Lesson.questions).selectinload(Question.choices))
    )
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")

    unlocked, passed = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")

    submission = await db.scalar(
        select(HomeworkSubmission).where(
            HomeworkSubmission.lesson_id == lesson_id, HomeworkSubmission.student_id == student.id
        )
    )

    out = LessonDetailOut.model_validate(lesson)
    out.is_unlocked = True
    out.is_passed = lesson_id in passed
    out.my_homework = HomeworkSubmissionOut.model_validate(submission) if submission else None
    return out
