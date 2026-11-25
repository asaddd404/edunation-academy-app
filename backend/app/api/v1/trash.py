"""«Корзина»: what teachers deleted in the last 30 days, and putting it back."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_log
from app.core.authorization import assert_teacher_owns_category
from app.core.trash import TRASH_DAYS, delete_forever, restore
from app.database import get_db
from app.deps import require_role
from app.models.category import Category, teacher_categories
from app.models.trash import TrashItem
from app.models.user import RoleEnum, User

router = APIRouter(prefix="/teacher/trash", tags=["trash"])


class TrashItemOut(BaseModel):
    id: int
    kind: str
    object_id: int
    title: str
    course_id: int
    course: str
    lesson_count: int
    deleted_at: datetime
    deleted_by: str | None
    purge_at: datetime


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@router.get("", response_model=list[TrashItemOut])
async def list_trash(
    db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
) -> list[TrashItemOut]:
    query = (
        select(TrashItem, Category.name, User)
        .join(Category, Category.id == TrashItem.category_id)
        .outerjoin(User, User.id == TrashItem.deleted_by)
        .order_by(TrashItem.deleted_at.desc(), TrashItem.id.desc())
    )
    if teacher.role != RoleEnum.admin:
        query = query.join(teacher_categories, teacher_categories.c.category_id == TrashItem.category_id).where(
            teacher_categories.c.teacher_id == teacher.id
        )
    out = []
    for item, course, who in (await db.execute(query)).all():
        out.append(
            TrashItemOut(
                id=item.id,
                kind=item.kind,
                object_id=item.object_id,
                title=item.title,
                course_id=item.category_id,
                course=course,
                lesson_count=item.lesson_count,
                deleted_at=_aware(item.deleted_at),
                deleted_by=f"{who.first_name} {who.last_name}".strip() if who else None,
                purge_at=_aware(item.deleted_at) + timedelta(days=TRASH_DAYS),
            )
        )
    return out


async def _own_item(db: AsyncSession, teacher: User, kind: str, object_id: int) -> TrashItem:
    item = await db.scalar(select(TrashItem).where(TrashItem.kind == kind, TrashItem.object_id == object_id))
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "В корзине этого нет — возможно, уже восстановлено")
    await assert_teacher_owns_category(db, teacher, item.category_id)
    return item


@router.post("/{kind}/{object_id}/restore")
async def restore_item(
    request: Request,
    kind: str,
    object_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    item = await _own_item(db, teacher, kind, object_id)
    try:
        message = await restore(db, item)
    except HTTPException as error:
        if error.status_code == status.HTTP_410_GONE:
            await db.commit()  # the stale record is dropped
        raise
    await db.commit()
    audit_log(f"content.{kind}.restore", actor_id=teacher.id, actor_role=teacher.role.value, request=request, object_id=object_id)
    return {"message": message, "course_id": item.category_id}


@router.delete("/{kind}/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_forever(
    request: Request,
    kind: str,
    object_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> None:
    item = await _own_item(db, teacher, kind, object_id)
    await delete_forever(db, item)
    audit_log(f"content.{kind}.delete", actor_id=teacher.id, actor_role=teacher.role.value, request=request, object_id=object_id)
