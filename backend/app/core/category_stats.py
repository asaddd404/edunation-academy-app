from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lesson import Lesson
from app.models.section import Section


async def lesson_stats(db: AsyncSession, category_ids: list[int]) -> dict[int, tuple[int, int]]:
    """category_id -> (lesson_count, total_video_duration_seconds), real counts from Section/Lesson."""
    if not category_ids:
        return {}
    rows = (
        await db.execute(
            select(
                Section.category_id,
                func.count(Lesson.id),
                func.coalesce(func.sum(Lesson.video_duration_seconds), 0),
            )
            .join(Lesson, Lesson.section_id == Section.id)
            .where(Section.category_id.in_(category_ids))
            .group_by(Section.category_id)
        )
    ).all()
    return {row[0]: (row[1], int(row[2])) for row in rows}
