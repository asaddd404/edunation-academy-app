"""Files that belong to lessons -- embedded images, presentations, students'
homework attachments -- found so they can be removed from disk when the
lessons are deleted for good (the database cascade cannot reach files)."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rich_content import extract_image_paths
from app.models.homework import HomeworkSubmission
from app.models.homework_auto import HomeworkAttempt
from app.models.lesson import Lesson


async def homework_file_paths(db: AsyncSession, lesson_ids: list[int]) -> set[str]:
    """Stored homework attachments of these lessons -- the DB cascade removes
    the submissions but not their files."""
    if not lesson_ids:
        return set()
    paths = await db.scalars(
        select(HomeworkSubmission.file_path).where(
            HomeworkSubmission.lesson_id.in_(lesson_ids), HomeworkSubmission.file_path.is_not(None)
        )
    )
    found = set(paths.all())
    # Photos/files handed in for auto-checked homework live inside the
    # attempts' answers ({task_id: {"file_path": ...}}).
    answers = await db.scalars(select(HomeworkAttempt.answers).where(HomeworkAttempt.lesson_id.in_(lesson_ids)))
    for answer_map in answers:
        for value in (answer_map or {}).values():
            if isinstance(value, dict) and isinstance(value.get("file_path"), str):
                found.add(value["file_path"])
    return found


async def still_referenced(db: AsyncSession, paths: set[str]) -> set[str]:
    """Which of these lesson-content images some lesson still shows.

    A teacher copying a lesson's text into another lesson copies the image
    links with it, so one uploaded picture can sit in several lessons;
    deleting it with the first lesson broke it in all the others. Called
    after the commit, so the lesson being deleted or edited no longer
    counts."""
    images = {p for p in paths if p.startswith("lesson-content/")}
    if not images:
        return set()
    conditions = []
    for path in images:
        conditions.append(Lesson.description.contains(path, autoescape=True))
        conditions.append(Lesson.homework_assignment.contains(path, autoescape=True))
    rows = await db.execute(select(Lesson.description, Lesson.homework_assignment).where(or_(*conditions)))
    used: set[str] = set()
    for description, homework in rows:
        used |= extract_image_paths(description) | extract_image_paths(homework)
    return images & used


async def lesson_files(db: AsyncSession, lesson_ids: list[int]) -> set[str]:
    """Everything on disk these lessons own, except their HLS video folders
    (see app.core.video.delete_video_assets)."""
    if not lesson_ids:
        return set()
    rows = (
        await db.execute(
            select(Lesson.description, Lesson.homework_assignment, Lesson.presentation_path).where(Lesson.id.in_(lesson_ids))
        )
    ).all()
    files: set[str] = set()
    for row in rows:
        files |= extract_image_paths(row.description) | extract_image_paths(row.homework_assignment)
        if row.presentation_path:
            files.add(row.presentation_path)
    return files | await homework_file_paths(db, lesson_ids)
