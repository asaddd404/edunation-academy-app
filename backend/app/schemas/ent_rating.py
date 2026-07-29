from pydantic import BaseModel


class EntLeaderboardEntryOut(BaseModel):
    rank: int
    student_id: int
    first_name: str
    last_name: str
    total_xp: int
    simulations_completed: int
    best_score: int
    is_me: bool


class EntLeaderboardOut(BaseModel):
    entries: list[EntLeaderboardEntryOut]
    # The requesting student's own row, populated even when they're outside
    # the top N returned in `entries` — the leaderboard UI always shows
    # "your position" alongside the top list.
    me: EntLeaderboardEntryOut | None
