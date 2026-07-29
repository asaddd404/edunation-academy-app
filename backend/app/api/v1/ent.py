import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_student_has_any_course_access
from app.core.question_scoring import grade_question
from app.core.rating import apply_simulation_xp
from app.core.storage import resolve_upload_path
from app.database import get_db
from app.deps import require_role
from app.models.ent_question import EntQuestion
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
    return FileResponse(path)

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
    subjects = (
        await db.scalars(
            select(EntSubject).where(EntSubject.id.in_(payload.subject_ids), EntSubject.is_active.is_(True))
        )
    ).all()
    found_ids = {s.id for s in subjects}
    missing = set(payload.subject_ids) - found_ids
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Предметы не найдены или неактивны: {sorted(missing)}")

    now = datetime.now(timezone.utc)
    simulation = EntSimulation(
        student_id=student.id,
        is_timed=payload.is_timed,
        duration_minutes=payload.duration_minutes,
        expires_at=(now + timedelta(minutes=payload.duration_minutes)) if payload.is_timed else None,
    )
    db.add(simulation)
    await db.flush()

    order_index = 0
    for subject_id in payload.subject_ids:
        question_ids = (
            await db.scalars(
                select(EntQuestion.id)
                .where(EntQuestion.subject_id == subject_id)
                .order_by(func.random())
                .limit(payload.questions_per_subject)
            )
        ).all()
        for question_id in question_ids:
            db.add(EntSimulationQuestion(simulation_id=simulation.id, question_id=question_id, order_index=order_index))
            order_index += 1

    if order_index == 0:
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


@router.get("/leaderboard", response_model=EntLeaderboardOut)
async def get_leaderboard(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    student: User = Depends(require_student_with_course_access),
) -> EntLeaderboardOut:
    limit = max(1, min(limit, 100))

    rows = (
        await db.execute(
            select(StudentRating, User)
            .join(User, User.id == StudentRating.student_id)
            .order_by(StudentRating.total_xp.desc(), StudentRating.student_id)
            .limit(limit)
        )
    ).all()

    entries = [
        EntLeaderboardEntryOut(
            rank=i + 1,
            student_id=rating.student_id,
            first_name=user.first_name,
            last_name=user.last_name,
            total_xp=rating.total_xp,
            simulations_completed=rating.simulations_completed,
            best_score=rating.best_score or 0,
            is_me=(rating.student_id == student.id),
        )
        for i, (rating, user) in enumerate(rows)
    ]

    # Always surface the requesting student's own standing, even when they
    # didn't make the top `limit` rows.
    me = next((e for e in entries if e.is_me), None)
    if me is None:
        my_rating = await db.get(StudentRating, student.id)
        if my_rating is not None:
            better_count = await db.scalar(
                select(func.count()).select_from(StudentRating).where(StudentRating.total_xp > my_rating.total_xp)
            )
            me = EntLeaderboardEntryOut(
                rank=(better_count or 0) + 1,
                student_id=student.id,
                first_name=student.first_name,
                last_name=student.last_name,
                total_xp=my_rating.total_xp,
                simulations_completed=my_rating.simulations_completed,
                best_score=my_rating.best_score or 0,
                is_me=True,
            )

    return EntLeaderboardOut(entries=entries, me=me)
