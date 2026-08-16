from pydantic import BaseModel


class TodayActivityOut(BaseModel):
    total_seconds: int
