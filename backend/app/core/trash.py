"""The trash (корзина): deleted lessons and sections are kept 30 days.

Deleting does not remove anything. The lesson or section is moved, with
everything hanging off it, into one hidden course (`Category.is_trash`):
no student applies to it, no teacher teaches it, nothing lists it -- so
every existing query stops seeing it without having to be taught about the
trash. A `TrashItem` remembers where it came from. Restoring moves it
back, and its video, tests, homework and every student's results return
exactly as they were.

After TRASH_DAYS the retention sweep deletes it for real, files included
(see purge_trash, run from app.core.retention).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lesson_files import lesson_files, still_referenced
from app.core.storage import delete_upload
from app.core.video import delete_video_assets
from app.models.category import Category
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.trash import TrashItem
from app.models.user import User

logger = logging.getLogger(__name__)

TRASH_DAYS = 30
TRASH_SLUG = "__trash__"
_HOLDING_TITLE = "Удалённые уроки"


async def trash_category(db: AsyncSession) -> Category:
    category = await db.scalar(select(Category).where(Category.is_trash.is_(True)).order_by(Category.id).limit(1))
    if category is None:
        category = Category(name="Корзина (служебный)", slug=TRASH_SLUG, is_active=False, is_trash=True)
        db.add(category)
        await db.flush()
    return category


async def _holding_section(db: AsyncSession, category: Category) -> Section:
    """Where single deleted lessons wait (a deleted section waits as itself)."""
    section = await db.scalar(
        select(Section).where(Section.category_id == category.id, Section.title == _HOLDING_TITLE).limit(1)
    )
    if section is None:
        section = Section(category_id=category.id, title=_HOLDING_TITLE, order_index=0)
        db.add(section)
        await db.flush()
    return section


async def trash_lesson(db: AsyncSession, lesson: Lesson, user: User) -> TrashItem:
    section = await db.get(Section, lesson.section_id)
    item = TrashItem(
        kind="lesson",
        object_id=lesson.id,
        title=lesson.title,
        category_id=section.category_id,
        section_id=section.id,
        order_index=lesson.order_index,
        deleted_by=user.id,
    )
    db.add(item)
    holding = await _holding_section(db, await trash_category(db))
    lesson.section_id = holding.id
    return item


async def trash_section(db: AsyncSession, section: Section, user: User) -> TrashItem:
    lesson_count = await db.scalar(select(func.count(Lesson.id)).where(Lesson.section_id == section.id)) or 0
    item = TrashItem(
        kind="section",
        object_id=section.id,
        title=section.title,
        category_id=section.category_id,
        order_index=section.order_index,
        lesson_count=lesson_count,
        deleted_by=user.id,
    )
    db.add(item)
    section.category_id = (await trash_category(db)).id
    return item


async def restore(db: AsyncSession, item: TrashItem) -> str:
    """Puts the item back. Returns a sentence for the teacher about where
    it went (a lesson whose section is gone lands in the first section)."""
    trash = await trash_category(db)
    if item.kind == "section":
        section = await db.get(Section, item.object_id)
        if section is None or section.category_id != trash.id:
            await db.delete(item)
            raise HTTPException(status.HTTP_410_GONE, "Этот раздел уже нельзя восстановить")
        # Make room at its old place so the course order comes back as it was.
        await db.execute(
            update(Section)
            .where(Section.category_id == item.category_id, Section.order_index >= item.order_index)
            .values(order_index=Section.order_index + 1)
        )
        section.category_id = item.category_id
        section.order_index = item.order_index
        await db.delete(item)
        return f"Раздел «{item.title}» восстановлен вместе с уроками."

    lesson = await db.get(Lesson, item.object_id)
    holding = await _holding_section(db, trash)
    if lesson is None or lesson.section_id != holding.id:
        await db.delete(item)
        raise HTTPException(status.HTTP_410_GONE, "Этот урок уже нельзя восстановить")
    target = await db.get(Section, item.section_id) if item.section_id else None
    message = f"Урок «{item.title}» восстановлен."
    if target is not None and target.category_id == item.category_id:
        await db.execute(
            update(Lesson)
            .where(Lesson.section_id == target.id, Lesson.order_index >= item.order_index)
            .values(order_index=Lesson.order_index + 1)
        )
        order_index = item.order_index
    else:
        # Its section was deleted (or moved) since: the first section of the
        # course takes it, at the end.
        target = await db.scalar(
            select(Section)
            .where(Section.category_id == item.category_id)
            .order_by(Section.order_index, Section.id)
            .limit(1)
        )
        if target is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "В курсе нет ни одного раздела. Восстановите раздел или создайте новый — потом восстановите урок.",
            )
        order_index = (
            await db.scalar(select(func.coalesce(func.max(Lesson.order_index), -1) + 1).where(Lesson.section_id == target.id))
        ) or 0
        message = f"Урок «{item.title}» восстановлен в раздел «{target.title}» — его прежнего раздела больше нет."
    lesson.section_id = target.id
    lesson.order_index = order_index
    await db.delete(item)
    return message


async def _hard_delete(db: AsyncSession, *, lesson_ids: list[int], section_ids: list[int]) -> None:
    """Deletes for real, files included. Commits."""
    if section_ids:
        lesson_ids = lesson_ids + list(
            await db.scalars(select(Lesson.id).where(Lesson.section_id.in_(section_ids)))
        )
    files = await lesson_files(db, lesson_ids)
    for lesson_id in lesson_ids:
        lesson = await db.get(Lesson, lesson_id)
        if lesson is not None:
            await db.delete(lesson)
    await db.flush()
    for section_id in section_ids:
        section = await db.get(Section, section_id)
        if section is not None:
            await db.delete(section)
    await db.commit()
    for lesson_id in lesson_ids:
        delete_video_assets(lesson_id)
    for path in files - await still_referenced(db, files):
        delete_upload(path)


async def delete_forever(db: AsyncSession, item: TrashItem) -> None:
    if item.kind == "section":
        await _hard_delete(db, lesson_ids=[], section_ids=[item.object_id])
    else:
        await _hard_delete(db, lesson_ids=[item.object_id], section_ids=[])
    # The cascade does not reach trash_items (no FK to the object).
    leftover = await db.get(TrashItem, item.id)
    if leftover is not None:
        await db.delete(leftover)
        await db.commit()


async def purge_trash(db: AsyncSession, now: datetime | None = None) -> int:
    """Deletes for good what has been in the trash for TRASH_DAYS, and
    anything parked there without a record (its course was deleted). Returns
    how many lessons and sections went."""
    now = now or datetime.now(timezone.utc)
    trash = await db.scalar(select(Category).where(Category.is_trash.is_(True)).limit(1))
    if trash is None:
        return 0
    expired = (await db.scalars(select(TrashItem).where(TrashItem.deleted_at < now - timedelta(days=TRASH_DAYS)))).all()
    removed = 0
    for item in expired:
        await delete_forever(db, item)
        removed += 1

    # Orphans: parked with no record to restore them by.
    holding = await _holding_section(db, trash)
    lesson_records = set(await db.scalars(select(TrashItem.object_id).where(TrashItem.kind == "lesson")))
    section_records = set(await db.scalars(select(TrashItem.object_id).where(TrashItem.kind == "section")))
    orphan_lessons = [lid for lid in await db.scalars(select(Lesson.id).where(Lesson.section_id == holding.id)) if lid not in lesson_records]
    orphan_sections = [
        sid
        for sid in await db.scalars(select(Section.id).where(Section.category_id == trash.id, Section.id != holding.id))
        if sid not in section_records
    ]
    if orphan_lessons or orphan_sections:
        await _hard_delete(db, lesson_ids=orphan_lessons, section_ids=orphan_sections)
        removed += len(orphan_lessons) + len(orphan_sections)
    else:
        await db.commit()
    if removed:
        logger.info("Trash: removed %d item(s) for good", removed)
    return removed
