import random
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_student_has_any_course_access
from app.core.ent_language import (
    QuestionShortage,
    UnknownLanguageError,
    parse_language,
    question_pool_filters,
    shortage_message,
)
from app.core.question_scoring import grade_question
from app.core.rating import apply_simulation_xp
from app.core.storage import image_response, resolve_upload_path
from app.database import get_db
from app.deps import require_role
from app.models.ent_question import EntQuestion, EntQuestionType
from app.models.ent_simulation import EntSimulation, EntSimulationQuestion, EntSimulationStatus
from app.models.ent_subject import EntSubject
from app.models.student_rating import StudentRating
from app.models.user import RoleEnum, User
from app.schemas.ent_question import EntAnswerVariantOut, EntChoiceTeacherOut, EntMatchPairTeacherOut
from app.schemas.ent_rating import EntLeaderboardEntryOut, EntLeaderboardOut
from app.schemas.ent_simulation import (
    EntAnswerIn,
    EntChoiceOut,
    EntMatchItemOut,
    EntQuestionStudentOut,
    EntSimulationOut,
    EntSimulationResultAnswerOut,
    EntSimulationResultOut,
    EntSimulationStartIn,
    EntSimulationSubmitIn,
    EntSimulationSummaryOut,
)
from app.schemas.ent_subject import EntSubjectOut


async def require_student_with_course_access(
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_role(RoleEnum.student)),
) -> User:
    await assert_student_has_any_course_access(db, student)
    return student


router = APIRouter(prefix="/ent", tags=["ent"], dependencies=[Depends(require_student_with_course_access)])

# Separate router so the image route escapes the student-only dependency above:
# a plain <img src> can't attach the bearer token, and teachers need to preview
# the same file from the question bank.
public_router = APIRouter(prefix="/ent", tags=["ent"])


@public_router.get("/questions/{question_id}/image")
async def get_ent_question_image(
    question_id: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    question = await db.get(EntQuestion, question_id)
    if question is None or not question.image_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")

    path = resolve_upload_path(question.image_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")
    return image_response(path)

_QUESTION_LOAD_OPTIONS = (
    selectinload(EntQuestion.subject),
    selectinload(EntQuestion.choices),
    selectinload(EntQuestion.match_pairs),
    selectinload(EntQuestion.answer_variants),
)


def _build_student_question(question: EntQuestion) -> EntQuestionStudentOut:
    match_prompts: list[EntMatchItemOut] = []
    match_answers: list[EntMatchItemOut] = []
    if question.match_pairs:
        match_prompts = [EntMatchItemOut(id=p.id, text=p.prompt_text) for p in question.match_pairs]
        shuffled = list(question.match_pairs)
        random.shuffle(shuffled)
        match_answers = [EntMatchItemOut(id=p.id, text=p.answer_text) for p in shuffled]

    return EntQuestionStudentOut(
        id=question.id,
        subject_id=question.subject_id,
        subject_name=question.subject.name,
        qtype=question.qtype,
        text=question.text,
        has_image=question.has_image,
        max_score=question.max_score,
        choices=[EntChoiceOut(id=c.id, text=c.text) for c in question.choices],
        match_prompts=match_prompts,
        match_answers=match_answers,
    )


def _subject_quotas(subject: EntSubject) -> dict[EntQuestionType, int]:
    """How many questions of each type the subject wants in a simulation.
    All zeroes means unconfigured -- see start_simulation's legacy branch."""
    return {
        EntQuestionType.single: subject.single_choice_count,
        EntQuestionType.multiple: subject.multiple_choice_count,
        EntQuestionType.matching: subject.matching_count,
        EntQuestionType.short_answer: subject.short_answer_count,
    }


def _remaining_seconds(simulation: EntSimulation) -> int | None:
    if not simulation.is_timed or simulation.expires_at is None:
        return None
    delta = simulation.expires_at - datetime.now(timezone.utc)
    return max(0, int(delta.total_seconds()))


@router.get("/subjects", response_model=list[EntSubjectOut])
async def list_subjects(db: AsyncSession = Depends(get_db)) -> list[EntSubjectOut]:
    rows = (
        await db.execute(
            select(EntSubject, func.count(EntQuestion.id))
            .outerjoin(EntQuestion, EntQuestion.subject_id == EntSubject.id)
            .where(EntSubject.is_active.is_(True))
            .group_by(EntSubject.id)
            .order_by(EntSubject.name)
        )
    ).all()
    result = []
    for subject, question_count in rows:
        out = EntSubjectOut.model_validate(subject)
        out.question_count = question_count
        result.append(out)
    return result


@router.post("/simulations", response_model=EntSimulationOut, status_code=status.HTTP_201_CREATED)
async def start_simulation(
    payload: EntSimulationStartIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> EntSimulationOut:
    try:
        language = parse_language(payload.language)
    except UnknownLanguageError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    subjects = (
        await db.scalars(
            select(EntSubject).where(EntSubject.id.in_(payload.subject_ids), EntSubject.is_active.is_(True))
        )
    ).all()
    found_ids = {s.id for s in subjects}
    missing = set(payload.subject_ids) - found_ids
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Предметы не найдены или неактивны: {sorted(missing)}")

    subjects_by_id = {s.id: s for s in subjects}

    async def available(subject_id: int, qtype: EntQuestionType | None = None) -> int:
        return await db.scalar(
            select(func.count(EntQuestion.id)).where(*question_pool_filters(subject_id, language, qtype))
        )

    # Checked for every subject *before* anything is written, so a bank that
    # is short in the chosen language is reported in full ("Химия нужно 20,
    # доступно 6") instead of one subject at a time, and never leaves a
    # half-built attempt behind.
    shortages: list[QuestionShortage] = []
    for subject_id in payload.subject_ids:
        subject = subjects_by_id[subject_id]
        quotas = _subject_quotas(subject)
        if any(quotas.values()):
            for qtype, count in quotas.items():
                if count <= 0:
                    continue
                have = await available(subject_id, qtype)
                if have < count:
                    shortages.append(QuestionShortage(subject.name, count, have, qtype))
        else:
            have = await available(subject_id)
            if have < payload.questions_per_subject:
                shortages.append(QuestionShortage(subject.name, payload.questions_per_subject, have))

    if shortages:
        # Not a silently shorter exam and not a 500: the caller is told which
        # subject to import questions for, in which language, and how many.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, shortage_message(language, shortages))

    now = datetime.now(timezone.utc)
    simulation = EntSimulation(
        student_id=student.id,
        is_timed=payload.is_timed,
        duration_minutes=payload.duration_minutes,
        language=language,
        expires_at=(now + timedelta(minutes=payload.duration_minutes)) if payload.is_timed else None,
    )
    db.add(simulation)
    await db.flush()

    order_index = 0
    for subject_id in payload.subject_ids:
        subject = subjects_by_id[subject_id]
        quotas = _subject_quotas(subject)

        if any(quotas.values()):
            # Quota-configured subject: draw `count` random questions per
            # qtype. The counts above already proved the pool can cover them.
            question_ids: list[int] = []
            for qtype, count in quotas.items():
                if count <= 0:
                    continue
                ids = (
                    await db.scalars(
                        select(EntQuestion.id)
                        .where(*question_pool_filters(subject_id, language, qtype))
                        .order_by(func.random())
                        .limit(count)
                    )
                ).all()
                question_ids.extend(ids)
            # Interleave qtypes instead of leaving them grouped block-by-block.
            random.shuffle(question_ids)
        else:
            # Legacy/unconfigured subject: flat random sample across all types.
            question_ids = (
                await db.scalars(
                    select(EntQuestion.id)
                    .where(*question_pool_filters(subject_id, language))
                    .order_by(func.random())
                    .limit(payload.questions_per_subject)
                )
            ).all()

        for question_id in question_ids:
            db.add(EntSimulationQuestion(simulation_id=simulation.id, question_id=question_id, order_index=order_index))
            order_index += 1

    if order_index == 0:
        # Unreachable while the shortage check above holds (it fails first on
        # an empty pool), kept as the backstop for a subject whose quotas and
        # questions_per_subject are both zero.
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "В выбранных предметах пока нет вопросов")

    await db.commit()

    simulation = await db.scalar(
        select(EntSimulation)
        .where(EntSimulation.id == simulation.id)
        .options(selectinload(EntSimulation.items).selectinload(EntSimulationQuestion.question).options(*_QUESTION_LOAD_OPTIONS))
    )
    return EntSimulationOut(
        id=simulation.id,
        is_timed=simulation.is_timed,
        duration_minutes=simulation.duration_minutes,
        language=simulation.language,
        status=simulation.status,
        started_at=simulation.started_at,
        expires_at=simulation.expires_at,
        remaining_seconds=_remaining_seconds(simulation),
        questions=[_build_student_question(item.question) for item in simulation.items],
    )


async def _get_own_simulation(db: AsyncSession, student: User, simulation_id: int) -> EntSimulation:
    simulation = await db.scalar(
        select(EntSimulation)
        .where(EntSimulation.id == simulation_id, EntSimulation.student_id == student.id)
        .options(selectinload(EntSimulation.items).selectinload(EntSimulationQuestion.question).options(*_QUESTION_LOAD_OPTIONS))
    )
    if simulation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Симуляция не найдена")
    return simulation


@router.get("/simulations", response_model=list[EntSimulationSummaryOut])
async def list_simulations(
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> list[EntSimulationSummaryOut]:
    simulations = (
        await db.scalars(
            select(EntSimulation)
            .where(EntSimulation.student_id == student.id)
            .order_by(EntSimulation.started_at.desc())
        )
    ).all()
    return [EntSimulationSummaryOut.model_validate(s) for s in simulations]


@router.get("/simulations/{simulation_id}", response_model=EntSimulationOut)
async def get_simulation(
    simulation_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> EntSimulationOut:
    simulation = await _get_own_simulation(db, student, simulation_id)
    if simulation.status != EntSimulationStatus.in_progress:
        raise HTTPException(status.HTTP_409_CONFLICT, "Симуляция уже сдана, смотрите /ent/simulations/{id}/result")

    return EntSimulationOut(
        id=simulation.id,
        is_timed=simulation.is_timed,
        duration_minutes=simulation.duration_minutes,
        language=simulation.language,
        status=simulation.status,
        started_at=simulation.started_at,
        expires_at=simulation.expires_at,
        remaining_seconds=_remaining_seconds(simulation),
        questions=[_build_student_question(item.question) for item in simulation.items],
    )


def _result_out(simulation: EntSimulation) -> EntSimulationResultOut:
    answers = []
    for item in simulation.items:
        question = item.question
        answers.append(
            EntSimulationResultAnswerOut(
                question_id=question.id,
                subject_id=question.subject_id,
                subject_name=question.subject.name,
                qtype=question.qtype,
                text=question.text,
                has_image=question.has_image,
                max_score=question.max_score,
                score_awarded=item.score_awarded or 0,
                is_correct=(item.score_awarded or 0) == question.max_score,
                given_answer=item.answer_data,
                choices=[EntChoiceTeacherOut.model_validate(c) for c in question.choices],
                match_pairs=[EntMatchPairTeacherOut.model_validate(p) for p in question.match_pairs],
                answer_variants=[EntAnswerVariantOut.model_validate(v) for v in question.answer_variants],
            )
        )
    return EntSimulationResultOut(
        id=simulation.id,
        is_timed=simulation.is_timed,
        duration_minutes=simulation.duration_minutes,
        language=simulation.language,
        time_expired=simulation.time_expired,
        status=simulation.status,
        started_at=simulation.started_at,
        submitted_at=simulation.submitted_at,
        total_score=simulation.total_score or 0,
        max_score=simulation.max_score or 0,
        xp_earned=simulation.xp_earned or 0,
        answers=answers,
    )


@router.post("/simulations/{simulation_id}/submit", response_model=EntSimulationResultOut)
async def submit_simulation(
    simulation_id: int,
    payload: EntSimulationSubmitIn,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> EntSimulationResultOut:
    simulation = await _get_own_simulation(db, student, simulation_id)
    if simulation.status != EntSimulationStatus.in_progress:
        raise HTTPException(status.HTTP_409_CONFLICT, "Симуляция уже сдана")

    answers_by_question: dict[int, EntAnswerIn] = {a.question_id: a for a in payload.answers}

    total_score = 0
    max_score = 0
    for item in simulation.items:
        answer = answers_by_question.get(item.question_id)
        answer_data = answer.model_dump(exclude_none=True, exclude={"question_id"}) if answer else None
        score = grade_question(item.question, answer_data)
        item.answer_data = answer_data
        item.score_awarded = score
        total_score += score
        max_score += item.question.max_score

    now = datetime.now(timezone.utc)
    simulation.status = EntSimulationStatus.submitted
    simulation.submitted_at = now
    simulation.time_expired = bool(simulation.is_timed and simulation.expires_at and now > simulation.expires_at)
    simulation.total_score = total_score
    simulation.max_score = max_score
    simulation.xp_earned = await apply_simulation_xp(db, simulation)

    await db.commit()
    simulation = await _get_own_simulation(db, student, simulation_id)
    return _result_out(simulation)


@router.get("/simulations/{simulation_id}/result", response_model=EntSimulationResultOut)
async def get_simulation_result(
    simulation_id: int,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> EntSimulationResultOut:
    simulation = await _get_own_simulation(db, student, simulation_id)
    if simulation.status != EntSimulationStatus.submitted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Симуляция ещё не сдана")
    return _result_out(simulation)


LeaderboardPeriod = Literal["week", "month", "all"]

_PERIOD_DAYS: dict[str, int] = {"week": 7, "month": 30}


def _period_totals_query(cutoff: datetime):
    """Per-student totals over submitted attempts since `cutoff`.

    `StudentRating` only ever holds the lifetime aggregate, so a week/month
    board has to be summed from the attempts themselves. `xp_earned` is frozen
    on each attempt at submit time, which is what makes this equal to the
    running total when the window covers everything."""
    return (
        select(
            EntSimulation.student_id.label("student_id"),
            func.coalesce(func.sum(EntSimulation.xp_earned), 0).label("total_xp"),
            func.count().label("simulations_completed"),
            func.coalesce(func.max(EntSimulation.total_score), 0).label("best_score"),
        )
        .where(
            EntSimulation.status == EntSimulationStatus.submitted,
            EntSimulation.submitted_at.is_not(None),
            EntSimulation.submitted_at >= cutoff,
        )
        .group_by(EntSimulation.student_id)
    )


@router.get("/leaderboard", response_model=EntLeaderboardOut)
async def get_leaderboard(
    limit: int = 20,
    period: LeaderboardPeriod = "all",
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> EntLeaderboardOut:
    limit = max(1, min(limit, 100))

    if period == "all":
        # Fast path: the running aggregate is already what we want.
        source = select(
            StudentRating.student_id.label("student_id"),
            StudentRating.total_xp.label("total_xp"),
            StudentRating.simulations_completed.label("simulations_completed"),
            func.coalesce(StudentRating.best_score, 0).label("best_score"),
        ).subquery()
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_PERIOD_DAYS[period])
        source = _period_totals_query(cutoff).subquery()

    # `student_id` tiebreaker, as everywhere else that paginates in this app:
    # ties on XP are common (a fresh period starts everyone at 0) and without
    # it Postgres is free to reorder equal rows between requests.
    rows = (
        await db.execute(
            select(source, User)
            .join(User, User.id == source.c.student_id)
            .order_by(source.c.total_xp.desc(), source.c.student_id)
            .limit(limit)
        )
    ).all()

    entries = [
        EntLeaderboardEntryOut(
            rank=i + 1,
            student_id=row.student_id,
            first_name=row.User.first_name,
            last_name=row.User.last_name,
            total_xp=row.total_xp,
            simulations_completed=row.simulations_completed,
            best_score=row.best_score,
            is_me=(row.student_id == student.id),
            has_avatar=row.User.avatar_path is not None,
        )
        for i, row in enumerate(rows)
    ]

    # Always surface the requesting student's own standing, even when they
    # didn't make the top `limit` rows.
    me = next((e for e in entries if e.is_me), None)
    if me is None:
        my_row = (
            await db.execute(select(source).where(source.c.student_id == student.id))
        ).one_or_none()
        if my_row is not None:
            better_count = await db.scalar(
                select(func.count()).select_from(source).where(source.c.total_xp > my_row.total_xp)
            )
            me = EntLeaderboardEntryOut(
                rank=(better_count or 0) + 1,
                student_id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                total_xp=my_row.total_xp,
                simulations_completed=my_row.simulations_completed,
                best_score=my_row.best_score,
                is_me=True,
                has_avatar=student.avatar_path is not None,
            )

    return EntLeaderboardOut(entries=entries, me=me)
