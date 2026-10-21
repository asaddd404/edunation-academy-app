"""The school's calendar day.

`date.today()` answers in the server's zone, which in the containers is UTC
-- so for pupils in Kazakhstan the "day" their activity is counted against
rolled over at 05:00 in the morning, and an evening study session was split
across two days. Kazakhstan has been on a single UTC+5 zone since March 2024
with no daylight saving, so a fixed offset is exact and does not depend on
the image shipping tzdata.
"""

from datetime import date, datetime, timedelta, timezone

SCHOOL_TZ = timezone(timedelta(hours=5), "Asia/Almaty")


def school_today() -> date:
    return datetime.now(SCHOOL_TZ).date()
