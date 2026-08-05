import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import assert_owns_ent_question, assert_owns_ent_subject
from app.core.ent_language import UnknownLanguageError, parse_language
from app.core.ent_pdf_import import (
    EMPTY_TEXT_WARNING,
    extract_pdf_text,
    parse_ent_pdf_questions,
    to_import_payload,
)
from app.core.pagination import PageParams, fetch_page, page_params
from app.core.slug import slugify
from app.core.storage import delete_upload, save_ent_question_image
from app.database import get_db
from app.deps import require_role
from app.models.ent_question import EntAnswerVariant, EntChoice, EntLanguage, EntMatchPair, EntQuestion
from app.models.ent_subject import EntSubject
from app.models.user import RoleEnum, User
from app.schemas.ent_import import (
    EntBulkCreateIn,
    EntBulkCreateOut,
    EntBulkCreateSkip,
    EntChoiceImportOut,
    EntMatchOptionOut,
    EntPdfImportOut,
    EntPdfImportStats,
    EntQuestionImportOut,
    EntVariantErrorOut,
)
from app.schemas.ent_question import (
    EntBulkDeleteIn,
    EntBulkDeleteOut,
    EntBulkDeleteSkip,
    EntChoiceIn,
    EntMatchPairIn,
    EntQuestionIn,
    EntQuestionTeacherOut,
)
from app.schemas.ent_subject import EntSubjectIn, EntSubjectOut, EntSubjectUpdateIn
from app.schemas.pagination import Page

MAX_ENT_PDF_SIZE = 15 * 1024 * 1024  # 15 MB
MAX_BULK_DELETE_BATCH = 500


def _label_at(labels: list[tuple[str, str]], index: int, part: int) -> str:
    """A choice's printed letter, or "" when the parser had none for it."""
    return labels[index][part] if index < len(labels) else ""

logger = logging.getLogger(__name__)

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
    if payload.single_choice_count is not None:
        subject.single_choice_count = payload.single_choice_count
    if payload.multiple_choice_count is not None:
        subject.multiple_choice_count = payload.multiple_choice_count
    if payload.matching_count is not None:
        subject.matching_count = payload.matching_count
    if payload.short_answer_count is not None:
        subject.short_answer_count = payload.short_answer_count

    await db.commit()
    await db.refresh(subject)
    out = EntSubjectOut.model_validate(subject)
    out.question_count = await db.scalar(
        select(func.count(EntQuestion.id)).where(EntQuestion.subject_id == subject.id)
    )
    return out


@router.get("/subjects/{subject_id}/questions", response_model=Page[EntQuestionTeacherOut])
async def list_subject_questions(
    subject_id: int,
    language: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
    params: PageParams = Depends(page_params),
) -> Page[EntQuestionTeacherOut]:
    """The subject's questions, optionally narrowed to one language, one
    page at a time -- an imported bank can run into the thousands, and this
    is the same `Page`/`fetch_page` convention every other list in the app
    already uses rather than a bespoke one for just this screen.

    Omitting `language` returns the whole bank -- the "Все" tab, and what
    every caller written before the ru/kk split asks for."""
    await assert_owns_ent_subject(db, user, subject_id)

    filters = [EntQuestion.subject_id == subject_id]
    if language is not None:
        try:
            filters.append(EntQuestion.language == parse_language(language))
        except UnknownLanguageError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    query = (
        select(EntQuestion)
        .where(*filters)
        .options(
            selectinload(EntQuestion.choices),
            selectinload(EntQuestion.match_pairs),
            selectinload(EntQuestion.answer_variants),
        )
        .order_by(EntQuestion.order_index)
    )
    questions, total = await fetch_page(db, query, params)
    return Page.of([EntQuestionTeacherOut.model_validate(q) for q in questions], total, params.page, params.per_page)


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
        language=payload.language,
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
    question.language = payload.language
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


@router.post("/questions/bulk-delete", response_model=EntBulkDeleteOut)
async def bulk_delete_questions(
    payload: EntBulkDeleteIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntBulkDeleteOut:
    """Deletes a teacher-selected batch of questions in one action.

    Ownership is checked per subject touched by the batch, and a single
    foreign id fails the *whole* request (403, nothing deleted) rather than
    silently dropping just that id -- a bulk action is exactly the place a
    partial-authorization result would be easy to misread as "it worked".
    Ids that don't exist (already deleted by an earlier call, or never did)
    are not an authorization failure -- they land in `failed` with
    `not_found` so retrying a batch is safe.
    """
    ids = set(payload.question_ids)
    if len(ids) > MAX_BULK_DELETE_BATCH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Не более {MAX_BULK_DELETE_BATCH} вопросов за один запрос"
        )

    questions = (await db.scalars(select(EntQuestion).where(EntQuestion.id.in_(ids)))).all()
    found_by_id = {q.id: q for q in questions}
    not_found = ids - found_by_id.keys()

    # Checked before anything is touched: if any subject in the batch isn't
    # the caller's, the request is rejected outright rather than deleting
    # just the ids that did belong to them.
    for subject_id in {q.subject_id for q in questions}:
        await assert_owns_ent_subject(db, user, subject_id)

    image_paths = [q.image_path for q in questions if q.image_path]
    for question in questions:
        await db.delete(question)
    await db.commit()
    # Only after the rows are gone, matching the single-delete endpoint's
    # ordering -- a failed commit can't leave a live question pointing at a
    # file that was already removed.
    for path in image_paths:
        delete_upload(path)

    deleted_ids = sorted(found_by_id.keys())
    logger.info(
        "ENT bulk delete: user_id=%s role=%s deleted %d question(s), %d not found",
        user.id, user.role.value, len(deleted_ids), len(not_found),
    )

    return EntBulkDeleteOut(
        deleted=deleted_ids,
        failed=[EntBulkDeleteSkip(id=qid, reason="not_found") for qid in sorted(not_found)],
    )


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


@router.post("/questions/import-pdf", response_model=EntPdfImportOut)
async def import_questions_from_pdf(
    subject_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntPdfImportOut:
    """Extracts question text from a PDF and classifies it into ЕНТ question
    types. This runs a state-machine parser, not a real LLM call (no LLM
    provider is configured for this project yet) -- every question in the
    response carries a `confidence`/`needs_review` the teacher must confirm
    in the preview screen before /bulk-create actually saves anything.

    Parsing never fails the request: an unreadable file comes back as 200
    with an empty `questions` and an explanatory warning, and a single
    unparseable question comes back with `confidence: 0.0` and its
    `parse_error` rather than being dropped."""
    await assert_owns_ent_subject(db, user, subject_id)

    is_pdf = (file.content_type or "") in ("application/pdf", "application/x-pdf") or (
        file.filename or ""
    ).lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл должен быть в формате PDF")

    contents = await file.read(MAX_ENT_PDF_SIZE + 1)
    if len(contents) > MAX_ENT_PDF_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 15 МБ)")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")

    try:
        extracted = extract_pdf_text(contents)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не удалось прочитать PDF-файл") from e

    text = extracted.text

    # Dumped at INFO so `docker compose logs backend` shows exactly what
    # pdfplumber read from the file -- the fastest way to see why the
    # regex heuristic did or didn't recognize a given PDF's layout.
    logger.info(
        "ENT PDF import: subject_id=%s file=%r extracted %d chars, %d marked line(s):\n%s",
        subject_id, file.filename, len(text), len(extracted.marks), text,
    )

    warnings: list[str] = []

    def warn(message: str) -> None:
        # The parser reports some of the same conditions the router checks
        # for; deduping here keeps the teacher from reading the same
        # sentence twice.
        if message not in warnings:
            warnings.append(message)

    if not text.strip():
        warn(EMPTY_TEXT_WARNING)

    # The parser is written not to raise, but a 500 here would lose a
    # teacher's whole upload -- so the endpoint degrades to an empty,
    # explained result even if that guarantee is ever broken.
    questions: list[EntQuestionImportOut] = []
    stats = EntPdfImportStats()
    try:
        parsed = parse_ent_pdf_questions(text, extracted.marks, extracted.cells)
        stats = EntPdfImportStats(
            total_lines=parsed.stats.total_lines,
            total_blocks_detected=parsed.stats.total_blocks_detected,
            parse_errors=parsed.stats.parse_errors,
            variants_detected=parsed.stats.variants_detected,
            variant_errors=[
                EntVariantErrorOut(
                    variant_id=error.variant_id,
                    variant_label=error.variant_label,
                    error=error.error,
                )
                for error in parsed.stats.variant_errors
            ],
            by_flag=parsed.stats.by_flag,
            duplicate_variant_headers=parsed.stats.duplicate_variant_headers,
        )
        for message in parsed.warnings:
            warn(message)
        for question in parsed.questions:
            payload = to_import_payload(question)
            questions.append(
                EntQuestionImportOut(
                    qtype=payload.qtype,
                    text=payload.text,
                    language=payload.language,
                    max_score=payload.max_score,
                    # Indexed rather than zipped: `choice_labels` is a
                    # parallel list, and a zip would silently drop choices
                    # if it ever fell short instead of just losing labels.
                    choices=[
                        EntChoiceImportOut(
                            text=t,
                            is_correct=c,
                            label=_label_at(payload.choice_labels, index, 0),
                            raw_label=_label_at(payload.choice_labels, index, 1),
                        )
                        for index, (t, c) in enumerate(payload.choices)
                    ],
                    match_pairs=[
                        EntMatchPairIn(prompt_text=p, answer_text=a) for p, a in payload.match_pairs
                    ],
                    answer_variants=payload.answer_variants,
                    confidence=payload.confidence,
                    needs_review=payload.needs_review,
                    detected_qtype=payload.detected_qtype,
                    raw_line_range=payload.raw_line_range,
                    variant_id=payload.variant_id,
                    variant_label=payload.variant_label,
                    question_number=payload.question_number,
                    flags=payload.flags,
                    match_left_items=payload.match_left_items,
                    match_options=[
                        EntMatchOptionOut(label=label, raw_label=raw, text=text)
                        for label, raw, text in payload.match_options
                    ],
                    parse_error=payload.parse_error,
                    key_source=payload.key_source,
                )
            )
        # Counted from the mapped questions, not the raw parse: the number
        # the teacher is told to check must match what is on their screen
        # (the mapping can flag a question the parser was happy with).
        stats.needs_review_count = sum(1 for q in questions if q.needs_review)
    except Exception:
        logger.exception("ENT PDF import: parser failed for subject_id=%s file=%r", subject_id, file.filename)
        questions = []
        warn("Не удалось разобрать структуру файла — попробуйте другой PDF или добавьте вопросы вручную")

    logger.info(
        "ENT PDF import: subject_id=%s recognized %d question block(s) across %d variant(s), "
        "%d need review, %d detected as Kazakh",
        subject_id, len(questions), stats.variants_detected, stats.needs_review_count,
        sum(1 for q in questions if q.language == EntLanguage.kk),
    )
    if not questions and text.strip():
        warn("Не удалось распознать ни одного вопроса — проверьте нумерацию вопросов в файле")
    if stats.parse_errors:
        warn(f"Не удалось полностью разобрать вопросов: {len(stats.parse_errors)}")
    if stats.variant_errors:
        # Named, not counted: with fifty variants on screen "один вариант
        # не разобрался" is not actionable, "Вариант №23" is.
        broken = ", ".join(e.variant_label or f"№{e.variant_id}" for e in stats.variant_errors)
        warn(f"Не удалось полностью разобрать варианты: {broken}")

    return EntPdfImportOut(
        subject_id=subject_id,
        questions=questions,
        skipped_count=0,
        warnings=warnings,
        stats=stats,
    )


@router.post("/questions/bulk-create", response_model=EntBulkCreateOut, status_code=status.HTTP_201_CREATED)
async def bulk_create_questions(
    payload: EntBulkCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(RoleEnum.teacher, RoleEnum.admin)),
) -> EntBulkCreateOut:
    """Saves a batch of teacher-confirmed questions (typically from the PDF
    import preview) in one transaction. Each item is independently validated
    against the same rules as the manual question form; a malformed item is
    skipped with its error rather than failing the whole batch."""
    await assert_owns_ent_subject(db, user, payload.subject_id)

    next_order = await db.scalar(
        select(func.coalesce(func.max(EntQuestion.order_index), -1) + 1).where(
            EntQuestion.subject_id == payload.subject_id
        )
    )

    skipped: list[EntBulkCreateSkip] = []
    new_questions: list[EntQuestion] = []
    for index, raw in enumerate(payload.questions):
        try:
            q_in = EntQuestionIn.model_validate(raw)
        except ValidationError as e:
            skipped.append(EntBulkCreateSkip(index=index, error="; ".join(err["msg"] for err in e.errors())))
            continue

        question = EntQuestion(
            subject_id=payload.subject_id,
            qtype=q_in.qtype,
            text=q_in.text,
            # Whatever the teacher left the flag on in the preview -- the
            # detector's guess only reached them as a default.
            language=q_in.language,
            max_score=q_in.max_score,
            order_index=next_order,
            created_by_id=user.id,
        )
        question.choices = [
            EntChoice(text=c.text, is_correct=c.is_correct, order_index=i) for i, c in enumerate(q_in.choices)
        ]
        question.match_pairs = [
            EntMatchPair(prompt_text=p.prompt_text, answer_text=p.answer_text, order_index=i)
            for i, p in enumerate(q_in.match_pairs)
        ]
        question.answer_variants = [EntAnswerVariant(text=v.strip()) for v in q_in.answer_variants if v.strip()]
        new_questions.append(question)
        next_order += 1

    for question in new_questions:
        db.add(question)
    if new_questions:
        await db.commit()

    return EntBulkCreateOut(created_count=len(new_questions), skipped=skipped)
