from datetime import datetime, timezone

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rate_limit import UPLOAD_BY_USER
from app.core.authorization import (
    assert_student_has_category_access,
    assert_teacher_owns_category,
    get_category_id_for_lesson,
)
from app.core.notifications import notify
from app.core.progress import get_lesson_progress
from app.core.storage import attachment_response, inline_document_response, resolve_upload_path, save_homework_file
from app.database import get_db
from app.deps import get_current_user, require_role
from app.models.category import teacher_categories
from app.models.homework import HomeworkStatusEnum, HomeworkSubmission
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum, User
from app.schemas.homework import HomeworkReviewIn, HomeworkSubmissionOut, file_kind

router = APIRouter(tags=["homework"])


def _serialize(submission: HomeworkSubmission, *, with_student: bool = False, with_lesson: bool = False) -> HomeworkSubmissionOut:
    out = HomeworkSubmissionOut.model_validate(submission)
    if with_student:
        out.student_name = f"{submission.student.first_name} {submission.student.last_name}"
        out.student_phone = submission.student.phone
    if with_lesson:
        out.lesson_title = submission.lesson.title
        out.category_id = submission.lesson.section.category_id
        out.category_name = submission.lesson.section.category.name
    return out


@router.post("/lessons/{lesson_id}/homework", response_model=HomeworkSubmissionOut, status_code=status.HTTP_201_CREATED)
async def submit_homework(
    lesson_id: int,
    text_answer: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> HomeworkSubmissionOut:
    await UPLOAD_BY_USER.enforce(str(student.id))
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)

    unlocked, _ = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")

    # Whitespace is no answer: without this, "   " passed the check below
    # and a blank submission landed in the teacher's review queue.
    text_answer = (text_answer or "").strip() or None
    if not text_answer and file is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Добавьте текст ответа или файл")

    submission = await db.scalar(
        select(HomeworkSubmission).where(
            HomeworkSubmission.lesson_id == lesson_id, HomeworkSubmission.student_id == student.id
        )
    )
    if submission is None:
        submission = HomeworkSubmission(lesson_id=lesson_id, student_id=student.id)
        db.add(submission)

    if text_answer is not None:
        submission.text_answer = text_answer
    if file is not None:
        relative_path, original_name = await save_homework_file(file)
        submission.file_path = relative_path
        submission.file_original_name = original_name

    submission.status = HomeworkStatusEnum.submitted
    submission.teacher_feedback = None
    submission.grade = None
    submission.reviewed_by = None
    submission.reviewed_at = None
    submission.submitted_at = datetime.now(timezone.utc)

    lesson_title = await db.scalar(select(Lesson.title).where(Lesson.id == lesson_id))
    teacher_ids = (
        await db.scalars(
            select(teacher_categories.c.teacher_id).where(teacher_categories.c.category_id == category_id)
        )
    ).all()
    for teacher_id in teacher_ids:
        notify(
            db,
            teacher_id,
            "new_homework",
            f"{student.first_name} {student.last_name} сдал(а) домашнее задание по уроку «{lesson_title}»",
            link="/teacher/homework",
        )

    await db.commit()
    await db.refresh(submission)
    return HomeworkSubmissionOut.model_validate(submission)


@router.get("/lessons/{lesson_id}/homework", response_model=HomeworkSubmissionOut | None)
async def get_my_homework(
    lesson_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> HomeworkSubmissionOut | None:
    submission = await db.scalar(
        select(HomeworkSubmission).where(
            HomeworkSubmission.lesson_id == lesson_id, HomeworkSubmission.student_id == student.id
        )
    )
    return HomeworkSubmissionOut.model_validate(submission) if submission else None


HomeworkFilter = Literal["submitted", "accepted", "revision_requested", "reviewed", "all"]


@router.get("/teacher/homework", response_model=list[HomeworkSubmissionOut])
async def list_homework(
    status_filter: HomeworkFilter = Query("submitted", alias="status"),
    student_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[HomeworkSubmissionOut]:
    """Homework in the teacher's courses (all courses for an admin).

    `status`: the queue (`submitted`, oldest first), a reviewed state, or
    `reviewed`/`all` (newest first). `student_id` narrows it to one student
    -- the "all of this student's work" view the review cards link to.
    """
    query = (
        select(HomeworkSubmission)
        .join(Lesson, Lesson.id == HomeworkSubmission.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
    )
    if status_filter == "reviewed":
        query = query.where(HomeworkSubmission.status != HomeworkStatusEnum.submitted)
    elif status_filter != "all":
        query = query.where(HomeworkSubmission.status == HomeworkStatusEnum(status_filter))
    if student_id is not None:
        query = query.where(HomeworkSubmission.student_id == student_id)
    if teacher.role != RoleEnum.admin:
        query = query.join(teacher_categories, teacher_categories.c.category_id == Section.category_id).where(
            teacher_categories.c.teacher_id == teacher.id
        )
    # The queue oldest first (first come, first reviewed); reviewed work by
    # when it was reviewed, newest first; everything by submission, newest first.
    if status_filter == "submitted":
        order = HomeworkSubmission.submitted_at.asc()
    elif status_filter == "all":
        order = HomeworkSubmission.submitted_at.desc()
    else:
        order = HomeworkSubmission.reviewed_at.desc().nulls_last()
    submissions = (
        await db.scalars(
            query.options(
                selectinload(HomeworkSubmission.student),
                selectinload(HomeworkSubmission.lesson).selectinload(Lesson.section).selectinload(Section.category),
            )
            .order_by(order)
            .limit(200)
        )
    ).all()
    return [_serialize(s, with_student=True, with_lesson=True) for s in submissions]


@router.get("/teacher/homework/pending", response_model=list[HomeworkSubmissionOut])
async def list_pending_homework(
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[HomeworkSubmissionOut]:
    """The review queue; kept for existing clients -- same as ?status=submitted."""
    return await list_homework("submitted", None, db, teacher)


@router.post("/teacher/homework/{submission_id}/review", response_model=HomeworkSubmissionOut)
async def review_homework(
    submission_id: int,
    payload: HomeworkReviewIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> HomeworkSubmissionOut:
    submission = await db.get(HomeworkSubmission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Домашнее задание не найдено")
    if submission.status != HomeworkStatusEnum.submitted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Домашнее задание уже проверено")

    category_id = await get_category_id_for_lesson(db, submission.lesson_id)
    await assert_teacher_owns_category(db, teacher, category_id)

    submission.status = payload.status
    submission.teacher_feedback = payload.feedback
    submission.grade = payload.grade
    submission.reviewed_by = teacher.id
    submission.reviewed_at = datetime.now(timezone.utc)

    lesson_title = await db.scalar(select(Lesson.title).where(Lesson.id == submission.lesson_id))
    status_label = "принята" if payload.status == HomeworkStatusEnum.accepted else "отправлена на доработку"
    if payload.grade is not None:
        status_label += f", оценка: {payload.grade}/100"
    notify(
        db,
        submission.student_id,
        "homework_reviewed",
        f"Домашняя работа по уроку «{lesson_title}» {status_label}",
        link=f"/lessons/{submission.lesson_id}",
    )

    await db.commit()
    await db.refresh(submission)
    return HomeworkSubmissionOut.model_validate(submission)


@router.get("/homework/{submission_id}/file")
async def download_homework_file(
    submission_id: int,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    submission = await db.get(HomeworkSubmission, submission_id)
    if submission is None or not submission.file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")

    if user.role == RoleEnum.student:
        if submission.student_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому файлу")
    elif user.role == RoleEnum.teacher:
        category_id = await get_category_id_for_lesson(db, submission.lesson_id)
        await assert_teacher_owns_category(db, teacher=user, category_id=category_id)
    elif user.role != RoleEnum.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому файлу")

    path = resolve_upload_path(submission.file_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")

    name = submission.file_original_name or path.name
    # Images and PDFs can be previewed in the page (`?inline=1`); everything
    # else -- .docx, .txt, anything that could carry markup -- only ever
    # downloads. The kind comes from the stored name, whose bytes were
    # checked against it at upload.
    if inline and file_kind(path.name) in ("image", "pdf"):
        return inline_document_response(path, name)
    return attachment_response(path, name)
