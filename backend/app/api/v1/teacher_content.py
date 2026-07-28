from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_teacher_owns_category, assert_teacher_owns_lesson, assert_teacher_owns_section
from app.database import get_db
from app.deps import require_role
from app.models.category import Category, teacher_categories
from app.models.lesson import Lesson
from app.models.question import Choice, Question
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.category import CategoryOut
from app.schemas.lesson import LessonIn, LessonTeacherOut
from app.schemas.question import QuestionIn, QuestionTeacherOut
from app.schemas.section import SectionIn, SectionOut

router = APIRouter(tags=["teacher-content"], dependencies=[Depends(require_role(RoleEnum.teacher))])


@router.get("/teacher/categories", response_model=list[CategoryOut])
async def list_my_categories(
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher)),
) -> list[CategoryOut]:
    categories = (
        await db.scalars(
            select(Category)
            .join(teacher_categories, teacher_categories.c.category_id == Category.id)
            .where(teacher_categories.c.teacher_id == teacher.id)
        )
    ).all()
    return [CategoryOut.model_validate(c) for c in categories]


@router.get("/teacher/categories/{category_id}/sections", response_model=list[SectionOut])
async def list_category_sections(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher)),
) -> list[SectionOut]:
    await assert_teacher_owns_category(db, teacher, category_id)

    sections = (
        await db.scalars(
            select(Section)
            .where(Section.category_id == category_id)
            .options(selectinload(Section.lessons))
            .order_by(Section.order_index)
        )
    ).all()
    return [SectionOut.model_validate(s) for s in sections]


@router.post("/teacher/categories/{category_id}/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
async def create_section(
    category_id: int,
    payload: SectionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher)),
) -> SectionOut:
    await assert_teacher_owns_category(db, teacher, category_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Section.order_index), -1) + 1).where(Section.category_id == category_id))
    )
    section = Section(category_id=category_id, title=payload.title, description=payload.description, order_index=next_order)
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return SectionOut.model_validate(section)


@router.post("/teacher/sections/{section_id}/lessons", response_model=LessonTeacherOut, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    section_id: int,
    payload: LessonIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher)),
) -> LessonTeacherOut:
    await assert_teacher_owns_section(db, teacher, section_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Lesson.order_index), -1) + 1).where(Lesson.section_id == section_id))
    )
    lesson = Lesson(
        section_id=section_id,
        title=payload.title,
        description=payload.description,
        video_url=payload.video_url,
        homework_assignment=payload.homework_assignment,
        order_index=next_order,
    )
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    return LessonTeacherOut.model_validate(lesson)


@router.post("/teacher/lessons/{lesson_id}/questions", response_model=QuestionTeacherOut, status_code=status.HTTP_201_CREATED)
async def create_question(
    lesson_id: int,
    payload: QuestionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher)),
) -> QuestionTeacherOut:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)

    next_order = (
        await db.scalar(select(func.coalesce(func.max(Question.order_index), -1) + 1).where(Question.lesson_id == lesson_id))
    )
    question = Question(lesson_id=lesson_id, text=payload.text, order_index=next_order)
    question.choices = [
        Choice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(payload.choices)
    ]
    db.add(question)
    await db.commit()

    question = await db.scalar(
        select(Question).where(Question.id == question.id).options(selectinload(Question.choices))
    )
    return QuestionTeacherOut.model_validate(question)
