"""Auto-checked homework: the teacher's constructor and results, the
student's attempts. Rules of the tasks themselves live in
app.core.homework_tasks; this module stores, schedules and authorizes.

Time rules, all in one place:

- ``hw_opens_at``: before it the homework can't be started.
- the effective deadline: the lesson's ``hw_deadline``, or a later personal
  ``extended_until``. After it, nothing can be started or submitted.
- an attempt's ``expires_at``: the earlier of start + time limit and the
  effective deadline. Answers saved by then (plus a short grace for the
  network) are what gets graded; a late payload is ignored, not refused.
- the answer key is revealed after the deadline *and every extension* has
  passed -- otherwise a classmate's revealed key could be passed on to the
  student who got extra days. Without a deadline it is revealed to a student
  who has used up their attempts or scored full marks on the auto part.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import assert_student_has_category_access, assert_teacher_owns_lesson, get_category_id_for_lesson
from app.core.homework_tasks import (
    AUTO_TYPES,
    MANUAL_TYPES,
    TaskDataError,
    clean_answer,
    correct_view,
    grade,
    make_layout,
    normalize_task,
    student_view,
)
from app.core.notifications import notify
from app.core.progress import get_lesson_progress
from app.core.rate_limit import UPLOAD_BY_USER
from app.core.storage import attachment_response, delete_upload, inline_document_response, resolve_upload_path, save_homework_file
from app.database import get_db
from app.deps import require_role
from app.models.application import Application, ApplicationStatusEnum
from app.models.homework_auto import HomeworkAttempt, HomeworkRecord, HomeworkTask
from app.models.lesson import Lesson
from app.models.user import RoleEnum, User
from app.schemas.homework import file_kind

router = APIRouter(tags=["homework-auto"])

GRACE = timedelta(seconds=30)
MAX_TASKS_PER_LESSON = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite (the no-Docker test backend) hands back naive datetimes."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ── Loading ──────────────────────────────────────────────────────────────────


async def _lesson(db: AsyncSession, lesson_id: int) -> Lesson:
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Урок не найден")
    return lesson


async def _tasks(db: AsyncSession, lesson_id: int) -> list[HomeworkTask]:
    rows = await db.scalars(
        select(HomeworkTask).where(HomeworkTask.lesson_id == lesson_id).order_by(HomeworkTask.order_index, HomeworkTask.id)
    )
    return list(rows)


async def _record(db: AsyncSession, lesson_id: int, student_id: int, *, create: bool) -> HomeworkRecord | None:
    record = await db.scalar(
        select(HomeworkRecord).where(HomeworkRecord.lesson_id == lesson_id, HomeworkRecord.student_id == student_id)
    )
    if record is None and create:
        record = HomeworkRecord(lesson_id=lesson_id, student_id=student_id, manual_scores={})
        db.add(record)
        try:
            await db.flush()
        except IntegrityError:  # a concurrent request created it first
            await db.rollback()
            record = await db.scalar(
                select(HomeworkRecord).where(HomeworkRecord.lesson_id == lesson_id, HomeworkRecord.student_id == student_id)
            )
    return record


async def _attempts(db: AsyncSession, lesson_id: int, student_id: int) -> list[HomeworkAttempt]:
    rows = await db.scalars(
        select(HomeworkAttempt)
        .where(HomeworkAttempt.lesson_id == lesson_id, HomeworkAttempt.student_id == student_id)
        .order_by(HomeworkAttempt.started_at, HomeworkAttempt.id)
    )
    return list(rows)


# ── Time and counting rules ─────────────────────────────────────────────────


def _effective_deadline(lesson: Lesson, record: HomeworkRecord | None) -> datetime | None:
    deadline = _aware(lesson.hw_deadline)
    extended = _aware(record.extended_until) if record else None
    if deadline is None:
        return None
    return max(deadline, extended) if extended else deadline


def _counted(attempts: list[HomeworkAttempt], record: HomeworkRecord | None) -> list[HomeworkAttempt]:
    """Submitted attempts that count toward the limit and the best result:
    a teacher's "retake" makes everything before it not count."""
    reset = _aware(record.attempts_reset_at) if record else None
    return [
        a for a in attempts if a.status == "submitted" and (reset is None or (_aware(a.submitted_at) or _now()) >= reset)
    ]


def _best(counted: list[HomeworkAttempt]) -> HomeworkAttempt | None:
    if not counted:
        return None
    # Highest auto score; on a tie the later attempt (its essay is the newer).
    return max(counted, key=lambda a: (a.auto_earned or 0.0, _aware(a.submitted_at) or _now(), a.id))


def _latest(counted: list[HomeworkAttempt]) -> HomeworkAttempt | None:
    return max(counted, key=lambda a: (_aware(a.submitted_at) or _now(), a.id)) if counted else None


async def _reveal_moment(db: AsyncSession, lesson: Lesson) -> datetime | None:
    deadline = _aware(lesson.hw_deadline)
    if deadline is None:
        return None
    latest_extension = _aware(
        await db.scalar(select(func.max(HomeworkRecord.extended_until)).where(HomeworkRecord.lesson_id == lesson.id))
    )
    return max(deadline, latest_extension) if latest_extension else deadline


def _expiry_for(lesson: Lesson, record: HomeworkRecord | None, started_at: datetime) -> datetime | None:
    candidates = []
    if lesson.hw_time_limit_minutes:
        candidates.append(started_at + timedelta(minutes=lesson.hw_time_limit_minutes))
    deadline = _effective_deadline(lesson, record)
    if deadline is not None:
        candidates.append(deadline)
    return min(candidates) if candidates else None


def _is_expired(attempt: HomeworkAttempt, now: datetime) -> bool:
    expires = _aware(attempt.expires_at)
    return expires is not None and now > expires + GRACE


# ── The task versions an attempt was given ───────────────────────────────────


@dataclass(frozen=True)
class _TaskVersion:
    """A task as frozen into an attempt when it started."""

    id: int
    type: str
    prompt: str
    data: dict
    points: int
    order_index: int = 0


def _snapshot(tasks: list[HomeworkTask]) -> dict:
    return {str(t.id): {"type": t.type, "prompt": t.prompt, "data": t.data, "points": t.points} for t in tasks}


def _attempt_tasks(attempt: HomeworkAttempt, live: dict[int, HomeworkTask]) -> dict[int, Any]:
    """The tasks of this attempt, in its order, as the student saw them.
    Edits and deletions made after the start do not reach an attempt; a task
    missing from the copy (none should be) falls back to the live row."""
    frozen = attempt.tasks_snapshot or {}
    out: dict[int, Any] = {}
    for tid in attempt.task_ids:
        snap = frozen.get(str(tid))
        if snap is not None:
            live_task = live.get(tid)
            out[tid] = _TaskVersion(
                tid, snap["type"], snap["prompt"], snap["data"], snap["points"], live_task.order_index if live_task else 0
            )
        elif tid in live:
            out[tid] = live[tid]
    return out


# ── Grading an attempt ───────────────────────────────────────────────────────


def _grade_attempt(attempt: HomeworkAttempt, tasks_by_id: dict[int, HomeworkTask], now: datetime) -> None:
    auto_earned = auto_max = manual_max = 0.0
    results: dict[str, Any] = {}
    versions = _attempt_tasks(attempt, tasks_by_id)
    for tid in attempt.task_ids:
        task = versions.get(tid)
        if task is None:
            continue
        g = grade(task.type, task.data, task.points, (attempt.answers or {}).get(str(tid)))
        results[str(tid)] = {"earned": g.earned, "max": g.max, "items": g.items}
        if task.type in MANUAL_TYPES:
            manual_max += g.max
        else:
            auto_max += g.max
            auto_earned += g.earned or 0.0
    attempt.results = results
    attempt.auto_earned = round(auto_earned, 2)
    attempt.auto_max = round(auto_max, 2)
    attempt.manual_max = round(manual_max, 2)
    attempt.status = "submitted"
    attempt.submitted_at = now
    started = _aware(attempt.started_at) or now
    end = min(now, _aware(attempt.expires_at) + GRACE) if attempt.expires_at else now
    attempt.duration_seconds = max(0, int((end - started).total_seconds()))


async def _finalize_if_expired(db: AsyncSession, attempt: HomeworkAttempt | None, now: datetime) -> bool:
    """An open sitting whose time ran out is graded on its saved answers the
    next time anyone looks at it -- no background job needed."""
    if attempt is None or attempt.status != "in_progress" or not _is_expired(attempt, now):
        return False
    tasks = {t.id: t for t in await _tasks(db, attempt.lesson_id)}
    _grade_attempt(attempt, tasks, now)
    return True


def _manual_ids(attempt: HomeworkAttempt, tasks_by_id: dict[int, HomeworkTask]) -> list[int]:
    versions = _attempt_tasks(attempt, tasks_by_id)
    return [tid for tid in attempt.task_ids if tid in versions and versions[tid].type in MANUAL_TYPES]


def _summary(
    counted: list[HomeworkAttempt], record: HomeworkRecord | None, tasks_by_id: dict[int, HomeworkTask]
) -> dict | None:
    """The student's result as it stands: best auto score plus the teacher's
    marks for essay/file tasks (taken from the latest attempt), and the
    teacher's override when there is one."""
    best = _best(counted)
    if best is None:
        return None
    latest = _latest(counted)
    manual_ids = _manual_ids(latest, tasks_by_id) if latest else []
    scores = (record.manual_scores if record else None) or {}
    manual_earned: float | None = 0.0
    for tid in manual_ids:
        entry = scores.get(str(tid))
        if not entry or entry.get("attempt_id") != latest.id:
            manual_earned = None
            break
        manual_earned += float(entry.get("earned") or 0)
    versions = _attempt_tasks(latest, tasks_by_id) if latest else {}
    manual_max = sum(versions[tid].points for tid in manual_ids)
    total_max = (best.auto_max or 0) + manual_max
    computed: int | None = None
    if manual_earned is not None and total_max > 0:
        computed = round(100 * ((best.auto_earned or 0) + manual_earned) / total_max)
    override = record.override_grade if record else None
    return {
        "attempt_id": best.id,
        "auto_earned": best.auto_earned,
        "auto_max": best.auto_max,
        "manual_max": manual_max,
        "manual_earned": manual_earned,
        "manual_pending": bool(manual_ids) and manual_earned is None,
        "grade": override if override is not None else computed,
        "computed_grade": computed,
        "overridden": override is not None,
    }


# ── Variants ─────────────────────────────────────────────────────────────────


def _draw_variant(lesson: Lesson, record: HomeworkRecord, tasks: list[HomeworkTask], rng: random.Random) -> list[int]:
    active = [t.id for t in tasks]
    n = lesson.hw_tasks_per_student
    if not n or n >= len(active):
        return active
    kept = [tid for tid in (record.variant_task_ids or []) if tid in active][:n]
    missing = n - len(kept)
    if missing > 0:
        pool = [tid for tid in active if tid not in kept]
        kept += rng.sample(pool, missing)
    order = {tid: i for i, tid in enumerate(active)}
    return sorted(kept, key=order.__getitem__)


# ── Schemas ──────────────────────────────────────────────────────────────────


class SettingsIn(BaseModel):
    opens_at: datetime | None = None
    deadline: datetime | None = None
    time_limit_minutes: int | None = Field(default=None, ge=1, le=600)
    max_attempts: int | None = Field(default=None, ge=1, le=20)
    tasks_per_student: int | None = Field(default=None, ge=1, le=MAX_TASKS_PER_LESSON)


class TaskIn(BaseModel):
    type: str
    prompt: str | None = ""
    data: dict = Field(default_factory=dict)
    points: int = 1


class TaskUpdateIn(BaseModel):
    prompt: str | None = ""
    data: dict = Field(default_factory=dict)
    points: int = 1


class OrderIn(BaseModel):
    task_ids: list[int]


class AnswersIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    away_count: int = Field(default=0, ge=0, le=10_000)


class PracticeIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


class ManualGradeIn(BaseModel):
    task_id: int
    earned: float | None = Field(default=None, ge=0)
    criteria: list[str] | None = None


class DecisionIn(BaseModel):
    action: str  # keep | zero | edit | retake | undo
    grade: int | None = Field(default=None, ge=0, le=100)
    comment: str | None = Field(default=None, max_length=2000)


class ExtensionIn(BaseModel):
    until: datetime | None = None


class AddTimeIn(BaseModel):
    minutes: int = Field(ge=1, le=180)


def _require_aware(value: datetime | None, label: str) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label}: укажите часовой пояс")
    return value


def _task_out(task: HomeworkTask) -> dict:
    return {
        "id": task.id,
        "type": task.type,
        "prompt": task.prompt,
        "data": task.data,
        "points": task.points,
        "order_index": task.order_index,
        "auto": task.type in AUTO_TYPES,
    }


def _settings_out(lesson: Lesson) -> dict:
    return {
        "opens_at": _aware(lesson.hw_opens_at),
        "deadline": _aware(lesson.hw_deadline),
        "time_limit_minutes": lesson.hw_time_limit_minutes,
        "max_attempts": lesson.hw_max_attempts,
        "tasks_per_student": lesson.hw_tasks_per_student,
    }


# ── Teacher: constructor ─────────────────────────────────────────────────────


@router.get("/teacher/lessons/{lesson_id}/auto-homework")
async def teacher_get_homework(
    lesson_id: int, db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
) -> dict:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    tasks = await _tasks(db, lesson_id)
    return {"settings": _settings_out(lesson), "tasks": [_task_out(t) for t in tasks]}


@router.patch("/teacher/lessons/{lesson_id}/auto-homework/settings")
async def teacher_update_settings(
    lesson_id: int,
    payload: SettingsIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    """Every field is sent every time (None switches a rule off). Changing
    the time rules while students are mid-attempt moves their end time
    straight away -- the "+10 minutes for everyone" case included."""
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    opens_at = _require_aware(payload.opens_at, "Дата открытия")
    deadline = _require_aware(payload.deadline, "Срок сдачи")
    if opens_at and deadline and deadline <= opens_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Срок сдачи должен быть позже даты открытия")
    lesson.hw_opens_at = opens_at
    lesson.hw_deadline = deadline
    lesson.hw_time_limit_minutes = payload.time_limit_minutes
    lesson.hw_max_attempts = payload.max_attempts
    lesson.hw_tasks_per_student = payload.tasks_per_student

    open_attempts = await db.scalars(
        select(HomeworkAttempt).where(HomeworkAttempt.lesson_id == lesson_id, HomeworkAttempt.status == "in_progress")
    )
    for attempt in open_attempts:
        record = await _record(db, lesson_id, attempt.student_id, create=False)
        attempt.expires_at = _expiry_for(lesson, record, _aware(attempt.started_at) or _now())
    await db.commit()
    return _settings_out(lesson)


@router.post("/teacher/lessons/{lesson_id}/auto-homework/add-time")
async def teacher_add_time(
    lesson_id: int,
    payload: AddTimeIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    """Extra minutes for everyone who is in the homework right now (a task
    turned out longer than planned). Not a change of the time limit."""
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    now = _now()
    changed = 0
    attempts = await db.scalars(
        select(HomeworkAttempt).where(HomeworkAttempt.lesson_id == lesson_id, HomeworkAttempt.status == "in_progress")
    )
    for attempt in attempts:
        if attempt.expires_at is None or _is_expired(attempt, now):
            continue
        attempt.expires_at = _aware(attempt.expires_at) + timedelta(minutes=payload.minutes)
        changed += 1
    await db.commit()
    return {"updated": changed}


@router.post("/teacher/lessons/{lesson_id}/auto-homework/tasks", status_code=status.HTTP_201_CREATED)
async def teacher_create_task(
    lesson_id: int,
    payload: TaskIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    await _lesson(db, lesson_id)
    count = await db.scalar(select(func.count(HomeworkTask.id)).where(HomeworkTask.lesson_id == lesson_id))
    if count >= MAX_TASKS_PER_LESSON:
        raise HTTPException(status.HTTP_409_CONFLICT, f"В одной домашке не больше {MAX_TASKS_PER_LESSON} заданий")
    try:
        prompt, data, points = normalize_task(payload.type, payload.prompt, payload.data, payload.points)
    except TaskDataError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    next_order = await db.scalar(
        select(func.coalesce(func.max(HomeworkTask.order_index), -1) + 1).where(HomeworkTask.lesson_id == lesson_id)
    )
    task = HomeworkTask(lesson_id=lesson_id, type=payload.type, prompt=prompt, data=data, points=points, order_index=next_order)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_out(task)


async def _owned_task(db: AsyncSession, teacher: User, task_id: int) -> HomeworkTask:
    task = await db.get(HomeworkTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")
    await assert_teacher_owns_lesson(db, teacher, task.lesson_id)
    return task


@router.put("/teacher/auto-homework/tasks/{task_id}")
async def teacher_update_task(
    task_id: int,
    payload: TaskUpdateIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    task = await _owned_task(db, teacher, task_id)
    try:
        prompt, data, points = normalize_task(task.type, payload.prompt, payload.data, payload.points)
    except TaskDataError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    task.prompt, task.data, task.points = prompt, data, points
    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.delete("/teacher/auto-homework/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def teacher_delete_task(
    task_id: int, db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
) -> None:
    task = await _owned_task(db, teacher, task_id)
    await db.delete(task)
    await db.commit()


@router.post("/teacher/auto-homework/tasks/{task_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def teacher_duplicate_task(
    task_id: int, db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
) -> dict:
    task = await _owned_task(db, teacher, task_id)
    tasks = await _tasks(db, task.lesson_id)
    if len(tasks) >= MAX_TASKS_PER_LESSON:
        raise HTTPException(status.HTTP_409_CONFLICT, f"В одной домашке не больше {MAX_TASKS_PER_LESSON} заданий")
    # Fresh ids inside the copy: re-normalizing without them mints new ones.
    data = _strip_ids(task.data)
    prompt, data, points = normalize_task(task.type, task.prompt, data, task.points)
    copy = HomeworkTask(lesson_id=task.lesson_id, type=task.type, prompt=prompt, data=data, points=points)
    db.add(copy)
    position = next(i for i, t in enumerate(tasks) if t.id == task.id)
    ordered = tasks[: position + 1] + [copy] + tasks[position + 1 :]
    for i, t in enumerate(ordered):
        t.order_index = i
    await db.commit()
    await db.refresh(copy)
    return _task_out(copy)


def _strip_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_ids(v) for k, v in value.items() if k not in ("id", "rid")}
    if isinstance(value, list):
        return [_strip_ids(v) for v in value]
    return value


@router.put("/teacher/lessons/{lesson_id}/auto-homework/order")
async def teacher_reorder_tasks(
    lesson_id: int,
    payload: OrderIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[dict]:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    tasks = await _tasks(db, lesson_id)
    by_id = {t.id: t for t in tasks}
    if sorted(payload.task_ids) != sorted(by_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Список заданий изменился — обновите страницу")
    for i, tid in enumerate(payload.task_ids):
        by_id[tid].order_index = i
    await db.commit()
    return [_task_out(by_id[tid]) for tid in payload.task_ids]


# ── Student ─────────────────────────────────────────────────────────────────


async def _student_lesson(db: AsyncSession, student: User, lesson_id: int) -> Lesson:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    await assert_student_has_category_access(db, student, category_id)
    unlocked, _ = await get_lesson_progress(db, student.id, category_id)
    if lesson_id not in unlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Урок ещё заблокирован")
    return await _lesson(db, lesson_id)


def _attempt_payload(attempt: HomeworkAttempt, tasks_by_id: dict[int, HomeworkTask]) -> dict:
    views = []
    versions = _attempt_tasks(attempt, tasks_by_id)
    for tid in attempt.task_ids:
        task = versions.get(tid)
        if task is None:
            continue
        views.append(student_view(task.id, task.type, task.prompt, task.data, task.points, (attempt.layout or {}).get(str(tid), {})))
    answers = {}
    for k, v in (attempt.answers or {}).items():
        # A stored file answer carries the server-side path: show the name only.
        answers[k] = {"file_name": v.get("file_name")} if isinstance(v, dict) and "file_path" in v else v
    return {
        "id": attempt.id,
        "started_at": _aware(attempt.started_at),
        "expires_at": _aware(attempt.expires_at),
        "tasks": views,
        "answers": answers,
        "server_now": _now(),
    }


def _review(attempt: HomeworkAttempt, tasks_by_id: dict[int, HomeworkTask], record: HomeworkRecord | None) -> list[dict]:
    out = []
    scores = (record.manual_scores if record else None) or {}
    versions = _attempt_tasks(attempt, tasks_by_id)
    for tid in attempt.task_ids:
        task = versions.get(tid)
        if task is None:
            continue
        result = (attempt.results or {}).get(str(tid), {})
        view = student_view(task.id, task.type, task.prompt, task.data, task.points, (attempt.layout or {}).get(str(tid), {}))
        answer = (attempt.answers or {}).get(str(tid)) or {}
        if isinstance(answer, dict) and "file_path" in answer:
            answer = {"file_name": answer.get("file_name")}
        earned = result.get("earned")
        if task.type in MANUAL_TYPES:
            entry = scores.get(str(tid))
            earned = entry.get("earned") if entry and entry.get("attempt_id") == attempt.id else None
        out.append(
            {
                "task": view,
                "answer": answer,
                "correct": correct_view(task.type, task.data),
                "items": result.get("items", []),
                "earned": earned,
                "max": result.get("max", task.points),
            }
        )
    return out


async def _state(db: AsyncSession, lesson: Lesson, student: User, now: datetime) -> dict:
    tasks = await _tasks(db, lesson.id)
    tasks_by_id = {t.id: t for t in tasks}
    record = await _record(db, lesson.id, student.id, create=False)
    attempts = await _attempts(db, lesson.id, student.id)
    open_attempt = next((a for a in attempts if a.status == "in_progress"), None)
    if await _finalize_if_expired(db, open_attempt, now):
        await db.commit()
        open_attempt = None
    counted = _counted(attempts, record)
    summary = _summary(counted, record, tasks_by_id)

    deadline = _effective_deadline(lesson, record)
    opens_at = _aware(lesson.hw_opens_at)
    used = len(counted)
    left = None if lesson.hw_max_attempts is None else max(0, lesson.hw_max_attempts - used)

    if opens_at and now < opens_at:
        phase, reason = "not_open", "Домашка ещё не открыта"
    elif deadline and now > deadline:
        phase, reason = "closed", "Срок сдачи прошёл"
    else:
        phase, reason = "open", None
    if phase == "open" and left == 0 and open_attempt is None:
        reason = "Попытки закончились"

    reveal_moment = await _reveal_moment(db, lesson)
    if reveal_moment is not None:
        reveal = now > reveal_moment and summary is not None
    else:
        best = _best(counted)
        full_auto = bool(best and (best.auto_max or 0) > 0 and (best.auto_earned or 0) >= (best.auto_max or 0) - 1e-9)
        reveal = summary is not None and ((left == 0) or full_auto)

    best_attempt = next((a for a in counted if summary and a.id == summary["attempt_id"]), None)
    return {
        "has_homework": bool(tasks),
        "phase": phase,
        "reason": reason,
        "opens_at": opens_at,
        "deadline": deadline,
        "time_limit_minutes": lesson.hw_time_limit_minutes,
        "max_attempts": lesson.hw_max_attempts,
        "attempts_used": used,
        "attempts_left": left,
        "can_start": bool(tasks) and phase == "open" and (left is None or left > 0 or open_attempt is not None),
        "open_attempt": {"id": open_attempt.id, "expires_at": _aware(open_attempt.expires_at)} if open_attempt else None,
        "task_count": min(len(tasks), lesson.hw_tasks_per_student or len(tasks)),
        "has_manual": any(t.type in MANUAL_TYPES for t in tasks),
        "result": summary,
        "teacher_comment": record.teacher_comment if record else None,
        "decision": record.decision if record else None,
        "reveal": reveal,
        "reveal_at": reveal_moment,
        "review": _review(best_attempt, tasks_by_id, record) if reveal and best_attempt else None,
        "server_now": now,
    }


@router.get("/lessons/{lesson_id}/auto-homework")
async def student_state(
    lesson_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> dict:
    lesson = await _student_lesson(db, student, lesson_id)
    return await _state(db, lesson, student, _now())


@router.post("/lessons/{lesson_id}/auto-homework/start")
async def student_start(
    lesson_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
) -> dict:
    lesson = await _student_lesson(db, student, lesson_id)
    now = _now()
    tasks = await _tasks(db, lesson_id)
    if not tasks:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "В этом уроке нет домашки с автопроверкой")
    tasks_by_id = {t.id: t for t in tasks}
    attempts = await _attempts(db, lesson_id, student.id)
    open_attempt = next((a for a in attempts if a.status == "in_progress"), None)
    if open_attempt is not None and not await _finalize_if_expired(db, open_attempt, now):
        return _attempt_payload(open_attempt, tasks_by_id)  # resume, never a second sitting

    record = await _record(db, lesson_id, student.id, create=True)
    opens_at = _aware(lesson.hw_opens_at)
    if opens_at and now < opens_at:
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Домашка ещё не открыта")
    deadline = _effective_deadline(lesson, record)
    if deadline and now > deadline:
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Срок сдачи прошёл")
    used = len(_counted(attempts, record))
    if lesson.hw_max_attempts is not None and used >= lesson.hw_max_attempts:
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Попытки закончились")

    rng = random.Random()
    variant = _draw_variant(lesson, record, tasks, rng)
    record.variant_task_ids = variant
    layout = {str(tid): make_layout(tasks_by_id[tid].type, tasks_by_id[tid].data, rng) for tid in variant}
    attempt = HomeworkAttempt(
        lesson_id=lesson_id,
        student_id=student.id,
        task_ids=variant,
        layout=layout,
        tasks_snapshot=_snapshot([tasks_by_id[tid] for tid in variant]),
        answers={},
        started_at=now,
        expires_at=_expiry_for(lesson, record, now),
    )
    db.add(attempt)
    try:
        await db.commit()
    except IntegrityError:
        # A double click: the other request opened the sitting. Hand it back.
        await db.rollback()
        existing = await db.scalar(
            select(HomeworkAttempt).where(
                HomeworkAttempt.lesson_id == lesson_id,
                HomeworkAttempt.student_id == student.id,
                HomeworkAttempt.status == "in_progress",
            )
        )
        if existing is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Не удалось начать — попробуйте ещё раз") from None
        return _attempt_payload(existing, tasks_by_id)
    await db.refresh(attempt)
    return _attempt_payload(attempt, tasks_by_id)


async def _own_open_attempt(db: AsyncSession, student: User, attempt_id: int) -> HomeworkAttempt:
    attempt = await db.get(HomeworkAttempt, attempt_id)
    if attempt is None or attempt.student_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Попытка не найдена")
    return attempt


def _merge_answers(attempt: HomeworkAttempt, tasks_by_id: dict[int, HomeworkTask], incoming: dict[str, Any]) -> None:
    versions = _attempt_tasks(attempt, tasks_by_id)
    allowed = {str(tid): versions[tid].type for tid in attempt.task_ids if tid in versions}
    merged = dict(attempt.answers or {})
    for key, value in incoming.items():
        ttype = allowed.get(str(key))
        if ttype is None or ttype == "file":
            continue  # file answers come only from the upload endpoint
        merged[str(key)] = clean_answer(ttype, value)
    attempt.answers = merged


@router.put("/auto-homework/attempts/{attempt_id}/answers")
async def student_save_answers(
    attempt_id: int,
    payload: AnswersIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> dict:
    attempt = await _own_open_attempt(db, student, attempt_id)
    if attempt.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Попытка уже отправлена")
    now = _now()
    if await _finalize_if_expired(db, attempt, now):
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Время вышло — отправлены ответы, сохранённые вовремя")
    tasks_by_id = {t.id: t for t in await _tasks(db, attempt.lesson_id)}
    _merge_answers(attempt, tasks_by_id, payload.answers)
    attempt.away_count = max(attempt.away_count or 0, payload.away_count)
    await db.commit()
    return {"saved_at": now, "expires_at": _aware(attempt.expires_at), "server_now": now}


@router.post("/auto-homework/attempts/{attempt_id}/files/{task_id}")
async def student_upload_file(
    attempt_id: int,
    task_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> dict:
    await UPLOAD_BY_USER.enforce(str(student.id))
    attempt = await _own_open_attempt(db, student, attempt_id)
    if attempt.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Попытка уже отправлена")
    now = _now()
    if await _finalize_if_expired(db, attempt, now):
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Время вышло — отправлены ответы, сохранённые вовремя")
    versions = _attempt_tasks(attempt, {t.id: t for t in await _tasks(db, attempt.lesson_id)})
    task = versions.get(task_id)
    if task is None or task.type != "file":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")
    relative_path, original_name = await save_homework_file(file)
    answers = dict(attempt.answers or {})
    previous = answers.get(str(task_id)) or {}
    answers[str(task_id)] = {"file_path": relative_path, "file_name": original_name}
    attempt.answers = answers
    try:
        await db.commit()
    except Exception:
        delete_upload(relative_path)
        raise
    delete_upload(previous.get("file_path") if isinstance(previous, dict) else None)
    return {"file_name": original_name, "file_kind": file_kind(original_name)}


@router.post("/auto-homework/attempts/{attempt_id}/submit")
async def student_submit(
    attempt_id: int,
    payload: AnswersIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> dict:
    attempt = await _own_open_attempt(db, student, attempt_id)
    if attempt.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Попытка уже отправлена")
    now = _now()
    tasks_by_id = {t.id: t for t in await _tasks(db, attempt.lesson_id)}
    late = _is_expired(attempt, now)
    if not late:  # past the end, only what was autosaved in time counts
        _merge_answers(attempt, tasks_by_id, payload.answers)
        attempt.away_count = max(attempt.away_count or 0, payload.away_count)
    _grade_attempt(attempt, tasks_by_id, now)
    await db.commit()
    lesson = await _lesson(db, attempt.lesson_id)
    state = await _state(db, lesson, student, now)
    state["late"] = late
    return state


@router.post("/lessons/{lesson_id}/auto-homework/practice")
async def student_practice(
    lesson_id: int,
    payload: PracticeIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> dict:
    """«Работа над ошибками»: re-answer tasks once the key is open. Checked,
    never stored, never changes the grade."""
    lesson = await _student_lesson(db, student, lesson_id)
    state = await _state(db, lesson, student, _now())
    if not state["reveal"] or not state["result"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Работа над ошибками откроется после срока сдачи")
    best = await db.get(HomeworkAttempt, state["result"]["attempt_id"])
    tasks_by_id = _attempt_tasks(best, {t.id: t for t in await _tasks(db, lesson_id)})
    out = {}
    for key, answer in payload.answers.items():
        try:
            tid = int(key)
        except ValueError:
            continue
        task = tasks_by_id.get(tid)
        if task is None or tid not in best.task_ids or task.type not in AUTO_TYPES:
            continue
        g = grade(task.type, task.data, task.points, clean_answer(task.type, answer))
        out[str(tid)] = {"correct": g.full, "earned": g.earned, "max": g.max, "items": g.items}
    return {"results": out}


@router.get("/auto-homework/attempts/{attempt_id}/files/{task_id}")
async def student_file(
    attempt_id: int, task_id: int, db: AsyncSession = Depends(get_db), student: User = Depends(require_role(RoleEnum.student))
):
    attempt = await _own_open_attempt(db, student, attempt_id)
    return _file_response(attempt, task_id)


def _file_response(attempt: HomeworkAttempt, task_id: int):
    answer = (attempt.answers or {}).get(str(task_id))
    if not isinstance(answer, dict) or not answer.get("file_path"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    path = resolve_upload_path(answer["file_path"])
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    name = answer.get("file_name") or path.name
    if file_kind(name) in ("image", "pdf"):
        return inline_document_response(path, name)
    return attachment_response(path, name)


# ── Teacher: results ─────────────────────────────────────────────────────────


async def _class_students(db: AsyncSession, lesson_id: int) -> list[User]:
    category_id = await get_category_id_for_lesson(db, lesson_id)
    rows = await db.scalars(
        select(User)
        .join(Application, Application.student_id == User.id)
        .where(Application.category_id == category_id, Application.status == ApplicationStatusEnum.approved)
        .order_by(User.last_name, User.first_name, User.id)
    )
    return list(rows)


FAST_SECONDS_PER_TASK = 8
AWAY_SIGNAL = 3
SHARED_WRONG_SIGNAL = 2


def _signals(rows: list[dict], tasks_by_id: dict[int, HomeworkTask]) -> dict[int, list[str]]:
    """Hints for the teacher, never verdicts. Identical *wrong* free-text
    answers are the strong one: right answers coincide for everyone, the
    same misspelt wrong answer rarely does by chance."""
    flags: dict[int, list[str]] = defaultdict(list)
    groups: dict[tuple, set[int]] = defaultdict(set)
    names = {}
    for row in rows:
        sid = row["student"]["id"]
        names[sid] = row["student"]["name"]
        best: HomeworkAttempt | None = row["_best"]
        if best is None:
            continue
        versions = _attempt_tasks(best, tasks_by_id)
        for tid_str, res in (best.results or {}).items():
            task = versions.get(int(tid_str))
            if task is None or task.type not in ("gaps", "short"):
                continue
            for item in res.get("items", []):
                if item.get("correct") is False and item.get("given"):
                    groups[(tid_str, item["key"], item["given"])].add(sid)
        task_count = max(1, len(best.task_ids))
        auto_ratio = (best.auto_earned or 0) / best.auto_max if best.auto_max else 0
        if best.duration_seconds is not None and best.duration_seconds < FAST_SECONDS_PER_TASK * task_count and auto_ratio >= 0.5:
            flags[sid].append(f"Выполнено очень быстро — {_human_duration(best.duration_seconds)} на {task_count} заданий.")
        away = max((a.away_count or 0) for a in row["_counted"]) if row["_counted"] else 0
        if away >= AWAY_SIGNAL:
            flags[sid].append(f"Во время попытки {away} раз уходил(а) со страницы.")
    pair_counts: Counter = Counter()
    for students in groups.values():
        if 2 <= len(students) <= 6:  # a mistake half the class made is a teaching problem, not copying
            ordered = sorted(students)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    pair_counts[(a, b)] += 1
    for (a, b), n in pair_counts.items():
        if n >= SHARED_WRONG_SIGNAL:
            flags[a].append(f"Одинаковые неправильные ответы с учеником {names[b]} в {n} местах.")
            flags[b].append(f"Одинаковые неправильные ответы с учеником {names[a]} в {n} местах.")
    return flags


def _human_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} с"
    minutes, sec = divmod(seconds, 60)
    return f"{minutes} мин {sec} с" if minutes < 10 and sec else f"{minutes} мин"


async def _results_rows(db: AsyncSession, lesson: Lesson, now: datetime) -> tuple[list[dict], dict[int, HomeworkTask]]:
    tasks = await _tasks(db, lesson.id)
    tasks_by_id = {t.id: t for t in tasks}
    students = await _class_students(db, lesson.id)
    all_attempts = list(await db.scalars(select(HomeworkAttempt).where(HomeworkAttempt.lesson_id == lesson.id)))
    finalized = False
    for attempt in all_attempts:
        if attempt.status == "in_progress" and _is_expired(attempt, now):
            _grade_attempt(attempt, tasks_by_id, now)
            finalized = True
    if finalized:
        await db.commit()
    by_student: dict[int, list[HomeworkAttempt]] = defaultdict(list)
    for a in all_attempts:
        by_student[a.student_id].append(a)
    records = {r.student_id: r for r in await db.scalars(select(HomeworkRecord).where(HomeworkRecord.lesson_id == lesson.id))}
    rows = []
    for s in students:
        attempts = sorted(by_student.get(s.id, []), key=lambda a: (_aware(a.started_at) or now, a.id))
        record = records.get(s.id)
        counted = _counted(attempts, record)
        summary = _summary(counted, record, tasks_by_id)
        open_attempt = next((a for a in attempts if a.status == "in_progress"), None)
        if summary is None:
            state = "in_progress" if open_attempt else "not_started"
        elif summary["manual_pending"]:
            state = "manual_pending"
        else:
            state = "done"
        best = _best(counted)
        rows.append(
            {
                "student": {"id": s.id, "name": f"{s.last_name} {s.first_name}", "phone": s.phone},
                "state": state,
                "attempts_used": len(counted),
                "in_progress": open_attempt is not None,
                "result": summary,
                "duration_seconds": best.duration_seconds if best else None,
                "away_count": max((a.away_count or 0) for a in counted) if counted else 0,
                "extended_until": _aware(record.extended_until) if record else None,
                "decision": record.decision if record else None,
                "teacher_comment": record.teacher_comment if record else None,
                "_best": best,
                "_counted": counted,
            }
        )
    return rows, tasks_by_id


@router.get("/teacher/lessons/{lesson_id}/auto-homework/results")
async def teacher_results(
    lesson_id: int, db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
) -> dict:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    now = _now()
    rows, tasks_by_id = await _results_rows(db, lesson, now)
    flags = _signals(rows, tasks_by_id)
    for row in rows:
        row.pop("_best")
        row.pop("_counted")
        dismissed = row["decision"] in ("keep", "zero", "edit", "retake")
        row["flags"] = [] if dismissed else flags.get(row["student"]["id"], [])
    grades = [r["result"]["grade"] for r in rows if r["result"] and r["result"]["grade"] is not None]
    return {
        "lesson": {"id": lesson.id, "title": lesson.title},
        "settings": _settings_out(lesson),
        "reveal_at": await _reveal_moment(db, lesson),
        "summary": {
            "students": len(rows),
            "submitted": sum(1 for r in rows if r["result"]),
            "not_submitted": sum(1 for r in rows if not r["result"]),
            "manual_pending": sum(1 for r in rows if r["state"] == "manual_pending"),
            "flagged": sum(1 for r in rows if r["flags"]),
            "average_grade": round(sum(grades) / len(grades)) if grades else None,
        },
        "rows": rows,
    }


@router.get("/teacher/lessons/{lesson_id}/auto-homework/problems")
async def teacher_problems(
    lesson_id: int, db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
) -> dict:
    """Where the class goes wrong: per task (per gap for fill-the-gaps), the
    share of students who missed it, the most common wrong answer, who."""
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    rows, tasks_by_id = await _results_rows(db, lesson, _now())
    stats: dict[tuple[int, str], dict] = {}
    for row in rows:
        best = row["_best"]
        if best is None:
            continue
        for tid_str, res in (best.results or {}).items():
            task = tasks_by_id.get(int(tid_str))
            if task is None or task.type in MANUAL_TYPES:
                continue
            for item in res.get("items", []):
                key = (task.id, item["key"])
                entry = stats.setdefault(key, {"task": task, "label": item.get("label"), "total": 0, "wrong": [], "answers": Counter()})
                entry["total"] += 1
                if item.get("correct") is False:
                    entry["wrong"].append(row["student"]["name"])
                    if item.get("given"):
                        entry["answers"][item["given"]] += 1
    position = {tid: i for i, tid in enumerate(tasks_by_id)}
    out = []
    for (tid, key), e in stats.items():
        if not e["total"]:
            continue
        task = e["task"]
        common = e["answers"].most_common(1)
        out.append(
            {
                "task_id": tid,
                "task_number": position[tid] + 1,
                "task_type": task.type,
                "prompt": task.prompt,
                "item_label": e["label"] if task.type in ("gaps", "match") else None,
                "total": e["total"],
                "wrong": len(e["wrong"]),
                "percent": round(100 * len(e["wrong"]) / e["total"]),
                "common_wrong": common[0][0] if common else None,
                "common_wrong_count": common[0][1] if common else 0,
                "students": e["wrong"],
                "correct": correct_view(task.type, task.data),
            }
        )
    out.sort(key=lambda r: (-r["percent"], r["task_number"]))
    return {"items": out}


async def _class_student(db: AsyncSession, lesson_id: int, student_id: int) -> User:
    for s in await _class_students(db, lesson_id):
        if s.id == student_id:
            return s
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Ученик не найден в этом курсе")


@router.get("/teacher/lessons/{lesson_id}/auto-homework/students/{student_id}")
async def teacher_student_detail(
    lesson_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    student = await _class_student(db, lesson_id, student_id)
    now = _now()
    tasks_by_id = {t.id: t for t in await _tasks(db, lesson_id)}
    record = await _record(db, lesson_id, student_id, create=False)
    attempts = await _attempts(db, lesson_id, student_id)
    open_attempt = next((a for a in attempts if a.status == "in_progress"), None)
    if await _finalize_if_expired(db, open_attempt, now):
        await db.commit()
    counted = _counted(attempts, record)
    latest = _latest(counted)
    best = _best(counted)
    counted_ids = {a.id for a in counted}

    def task_block(attempt: HomeworkAttempt) -> list[dict]:
        blocks = _review(attempt, tasks_by_id, record)
        versions = _attempt_tasks(attempt, tasks_by_id)
        for b, tid in zip(blocks, [t for t in attempt.task_ids if t in versions]):
            task = versions[tid]
            b["task_full"] = _task_out(task)
            if task.type in MANUAL_TYPES:
                entry = ((record.manual_scores if record else None) or {}).get(str(tid))
                b["manual"] = entry if entry and entry.get("attempt_id") == attempt.id else None
                b["has_file"] = task.type == "file" and bool(((attempt.answers or {}).get(str(tid)) or {}).get("file_path"))
        return blocks

    return {
        "student": {"id": student.id, "name": f"{student.last_name} {student.first_name}", "phone": student.phone},
        "result": _summary(counted, record, tasks_by_id),
        "record": {
            "extended_until": _aware(record.extended_until) if record else None,
            "decision": record.decision if record else None,
            "override_grade": record.override_grade if record else None,
            "teacher_comment": record.teacher_comment if record else None,
            "can_undo_retake": bool(record and record.decision == "retake" and not _started_after(attempts, record.attempts_reset_at)),
        },
        "attempts": [
            {
                "id": a.id,
                "status": a.status,
                "counted": a.id in counted_ids,
                "started_at": _aware(a.started_at),
                "submitted_at": _aware(a.submitted_at),
                "auto_earned": a.auto_earned,
                "auto_max": a.auto_max,
                "duration_seconds": a.duration_seconds,
                "away_count": a.away_count,
            }
            for a in attempts
        ],
        "latest_attempt_id": latest.id if latest else None,
        "best_attempt_id": best.id if best else None,
        "latest": task_block(latest) if latest else None,
        "best": task_block(best) if best and best is not latest else None,
    }


def _started_after(attempts: list[HomeworkAttempt], moment: datetime | None) -> bool:
    moment = _aware(moment)
    return bool(moment) and any((_aware(a.started_at) or _now()) >= moment for a in attempts)


@router.post("/teacher/lessons/{lesson_id}/auto-homework/students/{student_id}/manual")
async def teacher_grade_manual(
    lesson_id: int,
    student_id: int,
    payload: ManualGradeIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    """Marks for an essay or file task, on the student's latest attempt.
    With criteria the teacher ticks boxes and the points add up."""
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    await _class_student(db, lesson_id, student_id)
    live = {t.id: t for t in await _tasks(db, lesson_id)}
    record = await _record(db, lesson_id, student_id, create=True)
    attempts = await _attempts(db, lesson_id, student_id)
    latest = _latest(_counted(attempts, record))
    # Marked against the version the student answered, not today's edit.
    task = _attempt_tasks(latest, live).get(payload.task_id) if latest else None
    if task is None and payload.task_id in live and live[payload.task_id].type in MANUAL_TYPES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ученик ещё не сдавал это задание")
    if task is None or task.type not in MANUAL_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")

    criteria = (task.data or {}).get("criteria") or []
    if payload.criteria is not None and criteria:
        chosen = [c for c in criteria if c["id"] in set(payload.criteria)]
        earned = float(sum(c["points"] for c in chosen))
        chosen_ids = [c["id"] for c in chosen]
    elif payload.earned is not None:
        if payload.earned > task.points:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Не больше {task.points} баллов за это задание")
        earned, chosen_ids = round(payload.earned, 2), []
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Поставьте баллы или отметьте критерии")

    scores = dict(record.manual_scores or {})
    scores[str(task.id)] = {"earned": earned, "criteria": chosen_ids, "attempt_id": latest.id}
    record.manual_scores = scores
    summary = _summary(_counted(attempts, record), record, live)
    if summary and not summary["manual_pending"]:
        notify(
            db,
            student_id,
            "homework_reviewed",
            f"Учитель проверил домашку по уроку «{lesson.title}»"
            + (f": {summary['grade']}/100" if summary["grade"] is not None else ""),
            link=f"/lessons/{lesson_id}",
        )
    await db.commit()
    return {"result": summary}


@router.post("/teacher/lessons/{lesson_id}/auto-homework/students/{student_id}/decision")
async def teacher_decision(
    lesson_id: int,
    student_id: int,
    payload: DecisionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    """The teacher's last word on a piece of work: keep it (and drop the
    copy hints), set another grade, annul it (0), or give a retake on a
    fresh variant. Every one of them can be undone."""
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    await _class_student(db, lesson_id, student_id)
    record = await _record(db, lesson_id, student_id, create=True)
    attempts = await _attempts(db, lesson_id, student_id)
    now = _now()
    comment = (payload.comment or "").strip() or None
    action = payload.action
    message = None

    if action == "undo":
        if record.decision == "retake":
            if _started_after(attempts, record.attempts_reset_at):
                raise HTTPException(status.HTTP_409_CONFLICT, "Ученик уже начал пересдачу — отменить её нельзя")
            record.attempts_reset_at = record.previous_reset_at
            record.variant_task_ids = record.previous_variant
            before = record.previous_decision or {}
            record.previous_reset_at = None
            record.previous_variant = None
            record.previous_decision = None
            # Back to exactly what the teacher had before the retake.
            record.override_grade = before.get("override_grade")
            record.teacher_comment = before.get("teacher_comment")
            record.decision = before.get("decision")
            restored_at = before.get("decided_at")
            record.decided_at = datetime.fromisoformat(restored_at) if restored_at else None
            record.decided_by = before.get("decided_by")
        else:
            record.override_grade = None
            record.teacher_comment = None
            record.decision = None
    elif action == "keep":
        record.decision = "keep"
    elif action in ("zero", "edit"):
        if action == "edit" and payload.grade is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите новую оценку от 0 до 100")
        if not _counted(attempts, record):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ученик ещё ничего не сдал")
        record.override_grade = 0 if action == "zero" else payload.grade
        record.teacher_comment = comment
        record.decision = action
        message = f"Учитель изменил оценку за домашку «{lesson.title}»: {record.override_grade}/100"
    elif action == "retake":
        record.previous_reset_at = record.attempts_reset_at
        record.previous_variant = record.variant_task_ids
        record.previous_decision = {
            "decision": record.decision,
            "override_grade": record.override_grade,
            "teacher_comment": record.teacher_comment,
            "decided_at": _aware(record.decided_at).isoformat() if record.decided_at else None,
            "decided_by": record.decided_by,
        }
        record.attempts_reset_at = now
        record.variant_task_ids = None
        record.override_grade = None
        record.teacher_comment = comment
        record.decision = "retake"
        for a in attempts:  # an unfinished sitting belongs to the old variant
            if a.status == "in_progress":
                await db.delete(a)
        message = f"Учитель разрешил пересдать домашку «{lesson.title}» — у вас новый вариант"
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестное действие")

    if action != "undo":
        record.decided_at = now if record.decision else None
        record.decided_by = teacher.id if record.decision else None
    elif record.decision is None:
        record.decided_at = record.decided_by = None
    if message:
        notify(db, student_id, "homework_decision", message + (f". Комментарий: {comment}" if comment else ""), link=f"/lessons/{lesson_id}")
    await db.commit()
    tasks_by_id = {t.id: t for t in await _tasks(db, lesson_id)}
    return {"decision": record.decision, "result": _summary(_counted(await _attempts(db, lesson_id, student_id), record), record, tasks_by_id)}


@router.post("/teacher/lessons/{lesson_id}/auto-homework/students/{student_id}/extension")
async def teacher_extension(
    lesson_id: int,
    student_id: int,
    payload: ExtensionIn,
    db: AsyncSession = Depends(get_db),
    teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> dict:
    await assert_teacher_owns_lesson(db, teacher, lesson_id)
    lesson = await _lesson(db, lesson_id)
    await _class_student(db, lesson_id, student_id)
    until = _require_aware(payload.until, "Новый срок")
    record = await _record(db, lesson_id, student_id, create=True)
    record.extended_until = until
    open_attempt = await db.scalar(
        select(HomeworkAttempt).where(
            HomeworkAttempt.lesson_id == lesson_id, HomeworkAttempt.student_id == student_id, HomeworkAttempt.status == "in_progress"
        )
    )
    if open_attempt is not None:
        open_attempt.expires_at = _expiry_for(lesson, record, _aware(open_attempt.started_at) or _now())
    if until is not None:
        local = until.astimezone(timezone(timedelta(hours=5)))
        notify(
            db, student_id, "homework_extension", f"Срок сдачи домашки «{lesson.title}» продлён до {local:%d.%m %H:%M}", link=f"/lessons/{lesson_id}"
        )
    await db.commit()
    return {"extended_until": _aware(record.extended_until), "deadline": _effective_deadline(lesson, record)}


@router.get("/teacher/auto-homework/attempts/{attempt_id}/files/{task_id}")
async def teacher_file(
    attempt_id: int, task_id: int, db: AsyncSession = Depends(get_db), teacher: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin))
):
    attempt = await db.get(HomeworkAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    await assert_teacher_owns_lesson(db, teacher, attempt.lesson_id)
    return _file_response(attempt, task_id)
