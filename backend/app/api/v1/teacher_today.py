"""«Сегодня» -- the teacher's start page: what needs them today.

One request that sums up every course the teacher runs (every course for an
admin): new applications, auto-checked homework that came in, work that
waits for the teacher's decision (essays to mark, copy hints), today's
deadlines and who hasn't handed in, lessons with no homework yet, and the
spots where most of a class went wrong this week.

Only lessons with recent homework activity are looked at closely, so the
page stays fast however many old lessons a course has.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.homework_auto import _problem_items, _results_rows, _signals
from app.database import get_db
from app.deps import require_role
from app.models.application import Application, ApplicationStatusEnum
from app.models.category import Category, teacher_categories
from app.models.homework import HomeworkStatusEnum, HomeworkSubmission
from app.models.homework_auto import HomeworkAttempt, HomeworkTask
from app.models.lesson import Lesson
from app.models.section import Section
from app.models.user import RoleEnum, User

router = APIRouter(tags=["teacher"])

KZ = timezone(timedelta(hours=5))
RECENT = timedelta(days=14)
NEW_RESULTS = timedelta(hours=24)
PROBLEM_WINDOW = timedelta(days=7)
PROBLEM_MIN_STUDENTS = 3
PROBLEM_MIN_PERCENT = 50


async def _category_ids(db: AsyncSession, teacher: User) -> list[int]:
    if teacher.role == RoleEnum.admin:
        return list(await db.scalars(select(Category.id).where(Category.is_trash.is_(False))))
    return list(await db.scalars(select(teacher_categories.c.category_id).where(teacher_categories.c.teacher_id == teacher.id)))


def _lesson_ref(lesson: Lesson, course: Category) -> dict:
    return {"lesson_id": lesson.id, "title": lesson.title, "course_id": course.id, "course": course.name}


@router.get("/teacher/today")
async def teacher_today(
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    now = datetime.now(timezone.utc)
    category_ids = await _category_ids(db, teacher)

    applications = 0
    old_homework = 0
    if category_ids:
        applications = await db.scalar(
            select(func.count(Application.id)).where(
                Application.status == ApplicationStatusEnum.pending, Application.category_id.in_(category_ids)
            )
        ) or 0
        old_homework = await db.scalar(
            select(func.count(HomeworkSubmission.id))
            .join(Lesson, Lesson.id == HomeworkSubmission.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .where(HomeworkSubmission.status == HomeworkStatusEnum.submitted, Section.category_id.in_(category_ids))
        ) or 0

    rows = (
        await db.execute(
            select(Lesson, Section, Category)
            .join(Section, Section.id == Lesson.section_id)
            .join(Category, Category.id == Section.category_id)
            .where(Category.id.in_(category_ids or [-1]))
            .order_by(Category.name, Section.order_index, Lesson.order_index, Lesson.id)
        )
    ).all()
    lessons = {lesson.id: (lesson, course) for lesson, _section, course in rows}
    lesson_ids = list(lessons)

    task_counts: dict[int, int] = {}
    if lesson_ids:
        task_counts = dict(
            (
                await db.execute(
                    select(HomeworkTask.lesson_id, func.count(HomeworkTask.id))
                    .where(HomeworkTask.lesson_id.in_(lesson_ids))
                    .group_by(HomeworkTask.lesson_id)
                )
            ).all()
        )

    # Courses at a glance, and lessons that have no homework of either kind.
    courses: dict[int, dict] = {}
    without_homework: list[dict] = []
    for lesson, course in lessons.values():
        entry = courses.setdefault(course.id, {"id": course.id, "name": course.name, "lessons": 0, "with_homework": 0})
        entry["lessons"] += 1
        has_hw = task_counts.get(lesson.id, 0) > 0 or bool((lesson.homework_assignment or "").strip())
        if has_hw:
            entry["with_homework"] += 1
        else:
            without_homework.append(_lesson_ref(lesson, course))

    # Lessons worth a close look: homework activity or a deadline near now.
    active: set[int] = set()
    new_by_lesson: dict[int, int] = defaultdict(int)
    if lesson_ids:
        recent = await db.execute(
            select(HomeworkAttempt.lesson_id, HomeworkAttempt.submitted_at, HomeworkAttempt.status)
            .where(
                HomeworkAttempt.lesson_id.in_(lesson_ids),
                or_(
                    HomeworkAttempt.submitted_at >= now - RECENT,
                    # An open sitting counts only while it's recent: one a
                    # student started and abandoned months ago (no timer, so
                    # it never closes) must not keep its lesson "active".
                    and_(HomeworkAttempt.status == "in_progress", HomeworkAttempt.started_at >= now - RECENT),
                ),
            )
        )
        for lesson_id, submitted_at, status in recent.all():
            active.add(lesson_id)
            if status == "submitted" and submitted_at and submitted_at >= now - NEW_RESULTS:
                new_by_lesson[lesson_id] += 1
    today_kz = now.astimezone(KZ).date()
    for lesson, _course in lessons.values():
        if lesson.hw_deadline and task_counts.get(lesson.id):
            deadline = lesson.hw_deadline if lesson.hw_deadline.tzinfo else lesson.hw_deadline.replace(tzinfo=timezone.utc)
            if abs(deadline - now) <= timedelta(days=7):
                active.add(lesson.id)

    manual_pending: list[dict] = []
    flagged: list[dict] = []
    deadlines: list[dict] = []
    problems: list[dict] = []
    position = {lid: i for i, lid in enumerate(lesson_ids)}
    for lesson_id in sorted(active, key=position.__getitem__):
        lesson, course = lessons[lesson_id]
        result_rows, tasks_by_id = await _results_rows(db, lesson, now)
        ref = _lesson_ref(lesson, course)

        waiting = sum(1 for r in result_rows if r["state"] == "manual_pending")
        if waiting:
            manual_pending.append({**ref, "count": waiting})

        flags = _signals(result_rows, tasks_by_id)
        hinted = sum(
            1
            for r in result_rows
            if flags.get(r["student"]["id"]) and r["decision"] not in ("keep", "zero", "edit", "retake")
        )
        if hinted:
            flagged.append({**ref, "count": hinted})

        if lesson.hw_deadline:
            deadline = lesson.hw_deadline if lesson.hw_deadline.tzinfo else lesson.hw_deadline.replace(tzinfo=timezone.utc)
            local = deadline.astimezone(KZ)
            if local.date() in (today_kz, today_kz + timedelta(days=1)) and deadline >= now - timedelta(hours=12):
                missing = [r["student"]["name"] for r in result_rows if r["result"] is None]
                deadlines.append(
                    {
                        **ref,
                        "deadline": deadline,
                        "is_today": local.date() == today_kz,
                        "passed": deadline < now,
                        "students": len(result_rows),
                        "not_submitted": len(missing),
                        "missing_names": missing[:8],
                    }
                )

        recent_rows = [
            r for r in result_rows if r["_best"] is not None and (r["_best"].submitted_at or now) >= now - PROBLEM_WINDOW
        ]
        if recent_rows:
            for item in _problem_items(recent_rows, tasks_by_id):
                if item["total"] >= PROBLEM_MIN_STUDENTS and item["percent"] >= PROBLEM_MIN_PERCENT:
                    problems.append({**ref, **{k: item[k] for k in ("task_number", "task_type", "prompt", "item_label", "percent", "total", "wrong", "common_wrong")}})

    problems.sort(key=lambda p: -p["percent"])
    deadlines.sort(key=lambda d: d["deadline"])
    new_results = [
        {**_lesson_ref(*lessons[lid]), "count": n} for lid, n in sorted(new_by_lesson.items(), key=lambda kv: -kv[1])
    ]
    return {
        "now": now,
        "applications": applications,
        "old_homework_to_check": old_homework,
        "new_results": {"total": sum(new_by_lesson.values()), "lessons": new_results[:5]},
        "manual_pending": {"total": sum(x["count"] for x in manual_pending), "lessons": manual_pending},
        "flagged": {"total": sum(x["count"] for x in flagged), "lessons": flagged},
        "deadlines": deadlines,
        "without_homework": {"total": len(without_homework), "lessons": without_homework[:5]},
        "problems": problems[:5],
        "courses": list(courses.values()),
    }
