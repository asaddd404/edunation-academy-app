"""The API contract for POST /teacher/ent/questions/import-pdf.

Verifies that whatever the parser produces survives the mapping into the
response schema -- including the shapes that are *not* directly savable
(unknown type, zero confidence), which must still serialize rather than
500 the teacher's upload.
"""
import pytest

from app.core.ent_pdf_import import parse_ent_pdf_questions, to_import_payload
from app.schemas.ent_import import (
    EntChoiceImportOut,
    EntPdfImportOut,
    EntPdfImportStats,
    EntQuestionImportOut,
    EntVariantErrorOut,
)
from app.schemas.ent_question import EntMatchPairIn, EntQuestionIn

SAMPLE = """\
ПРЕДМЕТ: Биология
==========
1. Сопоставьте заболевание и возбудителя:
1. Дизентерия
2. Малярия
A) Plasmodium
B) Shigella
Ответ: 1-B, 2-A

2. Выберите несколько верных ответов:
E) Текст E   F) Текст F   G) Текст G   H) Текст H
Ответ: E, F

3. Столица Франции?
Ответ: Париж

4. Вопрос без ключа?
A) Первый
B) Второй
"""


def _label_at(labels: list[tuple[str, str]], index: int, part: int) -> str:
    return labels[index][part] if index < len(labels) else ""


def _to_response(text: str, subject_id: int = 1) -> EntPdfImportOut:
    """Mirrors what the router does, minus the auth/upload plumbing."""
    parsed = parse_ent_pdf_questions(text)
    questions = []
    for question in parsed.questions:
        payload = to_import_payload(question)
        questions.append(
            EntQuestionImportOut(
                qtype=payload.qtype,
                text=payload.text,
                max_score=payload.max_score,
                choices=[
                    EntChoiceImportOut(
                        text=t,
                        is_correct=c,
                        label=_label_at(payload.choice_labels, index, 0),
                        raw_label=_label_at(payload.choice_labels, index, 1),
                    )
                    for index, (t, c) in enumerate(payload.choices)
                ],
                match_pairs=[EntMatchPairIn(prompt_text=p, answer_text=a) for p, a in payload.match_pairs],
                answer_variants=payload.answer_variants,
                confidence=payload.confidence,
                needs_review=payload.needs_review,
                detected_qtype=payload.detected_qtype,
                raw_line_range=payload.raw_line_range,
                variant_id=payload.variant_id,
                variant_label=payload.variant_label,
                parse_error=payload.parse_error,
            )
        )
    return EntPdfImportOut(
        subject_id=subject_id,
        questions=questions,
        skipped_count=0,
        warnings=parsed.warnings,
        stats=EntPdfImportStats(
            total_lines=parsed.stats.total_lines,
            total_blocks_detected=parsed.stats.total_blocks_detected,
            needs_review_count=sum(1 for q in questions if q.needs_review),
            parse_errors=parsed.stats.parse_errors,
            variants_detected=parsed.stats.variants_detected,
            variant_errors=[
                EntVariantErrorOut(
                    variant_id=e.variant_id, variant_label=e.variant_label, error=e.error
                )
                for e in parsed.stats.variant_errors
            ],
        ),
    )


def test_response_serializes_with_every_documented_field():
    response = _to_response(SAMPLE)
    dumped = response.model_dump(mode="json")

    assert len(dumped["questions"]) == 4
    assert dumped["stats"]["total_blocks_detected"] == 4
    assert dumped["stats"]["needs_review_count"] == 1
    assert dumped["stats"]["parse_errors"] == []

    for question in dumped["questions"]:
        # Always present, so the preview needs no optional chaining.
        for key in (
            "qtype",
            "text",
            "max_score",
            "choices",
            "match_pairs",
            "answer_variants",
            "confidence",
            "needs_review",
            "detected_qtype",
            "raw_line_range",
            "variant_id",
            "variant_label",
            "parse_error",
        ):
            assert key in question, key
        assert len(question["raw_line_range"]) == 2
        for choice in question["choices"]:
            assert {"text", "is_correct", "label", "raw_label"} <= set(choice)
    for key in ("variants_detected", "variant_errors"):
        assert key in dumped["stats"], key


def test_variant_fields_serialize_for_a_multi_variant_file():
    response = _to_response(
        "Вариант №1\n1. Первый?\nA) Да\nB) Нет\nОтвет: A\n"
        "Вариант №2\n1. Второй?\nӘ) Иә\nB) Жоқ\nЖауабы: A\n"
    )
    dumped = response.model_dump(mode="json")

    assert dumped["stats"]["variants_detected"] == 2
    assert [q["variant_id"] for q in dumped["questions"]] == [1, 2]
    assert [q["variant_label"] for q in dumped["questions"]] == ["Вариант №1", "Вариант №2"]
    # The Kazakh glyph reaches the preview as printed, next to its canonical
    # label -- which is what the answer key was matched against.
    kazakh = dumped["questions"][1]["choices"][0]
    assert (kazakh["label"], kazakh["raw_label"]) == ("A", "Ә")
    assert kazakh["is_correct"] is True


def test_a_multi_variant_file_still_saves_cleanly():
    """Variant metadata is extra baggage EntQuestionIn must ignore, not
    choke on -- the preview posts the whole object back to /bulk-create."""
    response = _to_response(
        "".join(
            f"Вариант №{n}\n1. Вопрос {n}?\nA) Да\nB) Нет\nОтвет: A\n" for n in range(1, 6)
        )
    )

    assert len(response.questions) == 5
    for question in response.questions:
        EntQuestionIn.model_validate(question.model_dump(mode="json"))


def test_confident_questions_are_accepted_by_the_save_validator():
    """A 0.9-confidence question must be savable as-is: if bulk-create would
    reject it, the confidence was a lie."""
    response = _to_response(SAMPLE)

    checked = 0
    for question in response.questions:
        if question.needs_review:
            continue
        EntQuestionIn.model_validate(question.model_dump(mode="json"))
        checked += 1
    assert checked == 3


def test_unknown_type_is_presented_as_editable_single_choice():
    response = _to_response("1. Текст без вариантов и без ключа\n")
    question = response.questions[0]

    assert question.detected_qtype == "unknown"
    assert question.qtype.value == "single"
    assert question.needs_review is True


@pytest.mark.parametrize(
    "text",
    ["", "   ", "\x00\x01", "1.", "мусор", "Ответ: A", "1. " + "я" * 5000],
)
def test_degenerate_files_still_produce_a_valid_response(text):
    response = _to_response(text)
    assert response.model_dump(mode="json")["subject_id"] == 1
