from pydantic import BaseModel


class EntLeaderboardEntryOut(BaseModel):
    rank: int
    student_id: int
    first_name: str
    last_name: str
    # For a period board this is the XP earned *within* that period, not the
    # lifetime figure -- the field name stays the same so the UI does not have
    # to branch, but the meaning follows the requested period.
    total_xp: int
    simulations_completed: int
    best_score: int
    is_me: bool
    # Lets the client decide between <img> and initials without a probe
    # request per row that would 404 for most students.
    has_avatar: bool = False


class EntLeaderboardOut(BaseModel):
    entries: list[EntLeaderboardEntryOut]
    # The requesting student's own row, populated even when they're outside
    # the top N returned in `entries` — the leaderboard UI always shows
    # "your position" alongside the top list.
    me: EntLeaderboardEntryOut | None
