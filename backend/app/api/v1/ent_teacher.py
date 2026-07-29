from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_owns_ent_question, assert_owns_ent_subject
from app.core.slug import slugify
from app.core.storage import delete_upload, save_ent_question_image
from app.database import get_db
from app.deps import require_role
from app.models.ent_question import EntAnswerVariant, EntChoice, EntMatchPair, EntQuestion
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum, User
from app.schemas.ent_question import EntQuestionIn, EntQuestionTeacherOut
from app.schemas.ent_subject import EntSubjectIn, EntSubjectOut, EntSubjectUpdateIn

router = APIRouter(
    prefix="/teacher/ent", tags=["ent-teacher"], dependencies=[Depends(require_role(RoleEnum.teacher, RoleEnum.admin))]
)


@router.get("/subjects", response_model=list[EntSubjectOut])
async def list_subjects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[EntSubjectOut]:
    query = select(EntSubject, func.count(EntQuestion.id)).outerjoin(
        EntQuestion, EntQuestion.subject_id == EntSubject.id
    )
    if user.role != RoleEnum.admin:
        query = query.where(or_(EntSubject.is_active.is_(True), EntSubject.created_by_id == user.id))
    query = query.group_by(EntSubject.id).order_by(EntSubject.name)

    rows = (await db.execute(query)).all()
    result = []
    for subject, question_count in rows:
        out = EntSubjectOut.model_validate(subject)
        out.question_count = question_count
        result.append(out)
    return result


@router.post("/subjects", response_model=EntSubjectOut, status_code=status.HTTP_201_CREATED)
async def create_subject(
    payload: EntSubjectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntSubjectOut:
    slug = payload.slug.strip() if payload.slug else slugify(payload.name)

    existing = await db.scalar(select(EntSubject).where(EntSubject.slug == slug))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Предмет с таким slug уже существует")

    subject = EntSubject(name=payload.name, slug=slug, created_by_id=user.id)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return EntSubjectOut.model_validate(subject)


@router.patch("/subjects/{subject_id}", response_model=EntSubjectOut)
async def update_subject(
    subject_id: int,
    payload: EntSubjectUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntSubjectOut:
    subject = await assert_owns_ent_subject(db, user, subject_id)

    if payload.name is not None:
        subject.name = payload.name
    if payload.is_active is not None:
        subject.is_active = payload.is_active

    await db.commit()
    await db.refresh(subject)
    out = EntSubjectOut.model_validate(subject)
    out.question_count = await db.scalar(
        select(func.count(EntQuestion.id)).where(EntQuestion.subject_id == subject.id)
    )
    return out


@router.get("/subjects/{subject_id}/questions", response_model=list[EntQuestionTeacherOut])
async def list_subject_questions(
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> list[EntQuestionTeacherOut]:
    await assert_owns_ent_subject(db, user, subject_id)

    questions = (
        await db.scalars(
            select(EntQuestion)
            .where(EntQuestion.subject_id == subject_id)
            .options(
                selectinload(EntQuestion.choices),
                selectinload(EntQuestion.match_pairs),
                selectinload(EntQuestion.answer_variants),
            )
            .order_by(EntQuestion.order_index)
        )
    ).all()
    return [EntQuestionTeacherOut.model_validate(q) for q in questions]


@router.post("/subjects/{subject_id}/questions", response_model=EntQuestionTeacherOut, status_code=status.HTTP_201_CREATED)
async def create_subject_question(
    subject_id: int,
    payload: EntQuestionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntQuestionTeacherOut:
    await assert_owns_ent_subject(db, user, subject_id)

    next_order = await db.scalar(
        select(func.coalesce(func.max(EntQuestion.order_index), -1) + 1).where(EntQuestion.subject_id == subject_id)
    )
    question = EntQuestion(
        subject_id=subject_id,
        qtype=payload.qtype,
        text=payload.text,
        max_score=payload.max_score,
        order_index=next_order,
        created_by_id=user.id,
    )
    question.choices = [
        EntChoice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(payload.choices)
    ]
    question.match_pairs = [
        EntMatchPair(prompt_text=p.prompt_text, answer_text=p.answer_text, order_index=i)
        for i, p in enumerate(payload.match_pairs)
    ]
    question.answer_variants = [
        EntAnswerVariant(text=v.strip()) for v in payload.answer_variants if v.strip()
    ]
    db.add(question)
    await db.commit()

    question = await db.scalar(
        select(EntQuestion)
        .where(EntQuestion.id == question.id)
        .options(
            selectinload(EntQuestion.choices),
            selectinload(EntQuestion.match_pairs),
            selectinload(EntQuestion.answer_variants),
        )
    )
    return EntQuestionTeacherOut.model_validate(question)


@router.patch("/questions/{question_id}", response_model=EntQuestionTeacherOut)
async def update_question(
    question_id: int,
    payload: EntQuestionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntQuestionTeacherOut:
    # Full replace, not a partial patch: choices/match_pairs/answer_variants
    # are qtype-specific, so validating (and swapping) anything less than
    # the whole set risks leaving mismatched leftovers from the old qtype.
    await assert_owns_ent_question(db, user, question_id)

    question = await db.scalar(
        select(EntQuestion)
        .where(EntQuestion.id == question_id)
        .options(
            selectinload(EntQuestion.choices),
            selectinload(EntQuestion.match_pairs),
            selectinload(EntQuestion.answer_variants),
        )
    )
    question.qtype = payload.qtype
    question.text = payload.text
    question.max_score = payload.max_score
    question.choices = [
        EntChoice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(payload.choices)
    ]
    question.match_pairs = [
        EntMatchPair(prompt_text=p.prompt_text, answer_text=p.answer_text, order_index=i)
        for i, p in enumerate(payload.match_pairs)
    ]
    question.answer_variants = [EntAnswerVariant(text=v.strip()) for v in payload.answer_variants if v.strip()]
    await db.commit()

    question = await db.scalar(
        select(EntQuestion)
        .where(EntQuestion.id == question_id)
        .options(
            selectinload(EntQuestion.choices),
            selectinload(EntQuestion.match_pairs),
            selectinload(EntQuestion.answer_variants),
        )
    )
    return EntQuestionTeacherOut.model_validate(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> None:
    await assert_owns_ent_question(db, user, question_id)
    question = await db.get(EntQuestion, question_id)
    image_path = question.image_path
    await db.delete(question)
    await db.commit()
    # Only after the row is gone, so a failed commit can't leave a live
    # question pointing at a deleted file.
    delete_upload(image_path)


async def _load_question_with_relations(db: AsyncSession, question_id: int) -> EntQuestion:
    return await db.scalar(
        select(EntQuestion)
        .where(EntQuestion.id == question_id)
        .options(
            selectinload(EntQuestion.choices),
            selectinload(EntQuestion.match_pairs),
            selectinload(EntQuestion.answer_variants),
        )
    )


@router.post("/questions/{question_id}/image", response_model=EntQuestionTeacherOut)
async def upload_question_image(
    question_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntQuestionTeacherOut:
    await assert_owns_ent_question(db, user, question_id)

    question = await _load_question_with_relations(db, question_id)
    old_path = question.image_path
    question.image_path = await save_ent_question_image(file)
    await db.commit()
    delete_upload(old_path)

    return EntQuestionTeacherOut.model_validate(await _load_question_with_relations(db, question_id))


@router.delete("/questions/{question_id}/image", response_model=EntQuestionTeacherOut)
async def delete_question_image(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntQuestionTeacherOut:
    await assert_owns_ent_question(db, user, question_id)

    question = await _load_question_with_relations(db, question_id)
    old_path = question.image_path
    if old_path:
        question.image_path = None
        await db.commit()
        delete_upload(old_path)

    return EntQuestionTeacherOut.model_validate(await _load_question_with_relations(db, question_id))
