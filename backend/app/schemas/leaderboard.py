from typing import Literal

from pydantic import BaseModel

LeaderboardPeriod = Literal["week", "month", "all"]


class LeaderboardEntryOut(BaseModel):
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
    # Distinct lesson and section tests passed, lifetime.
    tests_passed: int = 0
    is_me: bool
    # Lets the client decide between <img> and initials without a probe
    # request per row that would 404 for most students.
    has_avatar: bool = False


class LeaderboardOut(BaseModel):
    entries: list[LeaderboardEntryOut]
    # The requesting student's own row, populated even when they're outside
    # the top N returned in `entries` — the leaderboard UI always shows
    # "your position" alongside the top list.
    me: LeaderboardEntryOut | None


class TestLeaderboardEntryOut(BaseModel):
    """A student's best finished attempt at one lesson or section test."""

    __test__ = False

    rank: int
    student_id: int
    first_name: str
    last_name: str
    has_avatar: bool = False
    is_me: bool
    passed: bool
    score: int
    # NULL on attempts recorded before tests became sessions: the detail was
    # never stored, and inventing it would be worse than showing a dash.
    correct_count: int | None
    question_count: int | None
    duration_seconds: int | None
    # Total XP this student has earned on this test, across attempts.
    xp_earned: int
    attempts: int


class TestLeaderboardOut(BaseModel):
    __test__ = False

    scope: Literal["lesson", "section"]
    scope_id: int
    title: str
    entries: list[TestLeaderboardEntryOut]
    me: TestLeaderboardEntryOut | None


class LeaderboardLessonOut(BaseModel):
    id: int
    title: str


class LeaderboardSectionOut(BaseModel):
    id: int
    title: str
    has_test: bool
    lessons: list[LeaderboardLessonOut]


class LeaderboardCategoryOut(BaseModel):
    id: int
    name: str
    sections: list[LeaderboardSectionOut]
