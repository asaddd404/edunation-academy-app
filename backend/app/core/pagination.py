from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


@dataclass
class PageParams:
    page: int
    per_page: int


def page_params(page: int = Query(1, ge=1), per_page: int = Query(DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE)) -> PageParams:
    return PageParams(page=page, per_page=per_page)


async def fetch_page(db: AsyncSession, query: Select, params: PageParams) -> tuple[list, int]:
    """Runs `query` (already filtered/ordered) as one COUNT and one
    LIMIT/OFFSET slice. Ordering is stripped for the count -- it's
    meaningless there and wasted work for the database to sort rows it's
    about to just count."""
    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = (await db.scalars(query.limit(params.per_page).offset((params.page - 1) * params.per_page))).all()
    return list(rows), total or 0
