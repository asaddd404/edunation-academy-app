from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import ACTIVITY_PING_BY_USER
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.schemas.activity import TodayActivityOut

router = APIRouter(prefix="/activity", tags=["activity"])

# Fixed server-side increment per ping -- the client's job is only to say
# "still here", never how much time to credit, so a stuck tab firing pings
# in a burst (throttled background timer catching up) can't inflate the total.
PING_SECONDS = 60


async def _get_or_create_today(db: AsyncSession, user_id: int) -> UserDailyActivity:
    today = date.today()
    row = await db.scalar(
        select(UserDailyActivity).where(UserDailyActivity.user_id == user_id, UserDailyActivity.date == today)
    )
    if row is None:
        row = UserDailyActivity(user_id=user_id, date=today, total_seconds=0)
        db.add(row)
    return row


@router.post("/ping", response_model=TodayActivityOut)
async def ping_activity(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TodayActivityOut:
    # PING_SECONDS is credited per call, so without a floor on how often a
    # call counts, a student can script the endpoint and mint any activity
    # total they like -- the number teachers and admins grade attendance by.
    await ACTIVITY_PING_BY_USER.enforce(str(user.id))

    row = await _get_or_create_today(db, user.id)
    row.total_seconds += PING_SECONDS
    await db.commit()
    return TodayActivityOut(total_seconds=row.total_seconds)


@router.get("/me/today", response_model=TodayActivityOut)
async def get_my_today_activity(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TodayActivityOut:
    today = date.today()
    total = await db.scalar(
        select(UserDailyActivity.total_seconds).where(
            UserDailyActivity.user_id == user.id, UserDailyActivity.date == today
        )
    )
    return TodayActivityOut(total_seconds=total or 0)
