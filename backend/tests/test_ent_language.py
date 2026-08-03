"""Acceptance tests for splitting the bank and the simulations by language.

The layer answers one question -- "is this question Russian or Kazakh?" --
and the ways it can be wrong are asymmetric, so that is how the tests are
weighted:

* labelling a Kazakh question `ru` hides it from every Kazakh simulation,
  which looks like a missing question rather than a mislabelled one;
* labelling a Russian question `kk` puts foreign text in a Kazakh exam.

Both come from the same mistake -- deciding a question's language on the
question's own text, which is often blank of any signal -- so most of what
follows checks the *variant* is what decides, and that a single question may
only overrule it on evidence Russian cannot produce.

Nothing here needs a database: the parts the router leans on (the pool
filter, the shortage wording, the language parsing) are functions in
`app.core.ent_language` precisely so they can be asserted directly.
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.ent_language import (
    QuestionShortage,
    UnknownLanguageError,
    parse_language,
    question_pool_filters,
    shortage_message,
)
from app.core.ent_pdf_import import (
    KAZAKH,
    RUSSIAN,
    detect_language,
    detect_variant_language,
    kazakh_signal,
    parse_ent_pdf_questions,
    question_language,
    to_import_payload,
)
from app.models.ent_question import EntLanguage, EntQuestion, EntQuestionType
from app.schemas.ent_import import EntQuestionImportOut
from app.schemas.ent_question import EntQuestionIn

# ─────────────────────────────────────────────────────────────────────────
# Fixtures: whole papers, because the unit under test is the variant
# ─────────────────────────────────────────────────────────────────────────


def _kazakh_question(number: int) -> str:
    return (
        f"{number}. Қазақстан тарихы бойынша {number}-сұрақ қандай?\n"
        "A) Астана\nB) Алматы\nЖауабы: A\n"
    )


def _russian_question(number: int) -> str:
    return f"{number}. Вопрос номер {number} по истории?\nA) Первый\nB) Второй\nОтвет: A\n"


# A question that is the same text in both languages: no letters to go on,
# which is exactly the case §2.1 says must inherit rather than default.
NEUTRAL_QUESTION = "10. 2 + 2 = ?\nA) 3\nB) 4\nОтвет: B\n"


def kazakh_paper_with_one_neutral_question() -> str:
    return "Вариант №1\n" + "".join(_kazakh_question(n) for n in range(1, 10)) + NEUTRAL_QUESTION


def russian_paper_with_one_kazakh_question() -> str:
    """A Kazakh item pasted into a Russian variant -- with its own answer
    key, the way a question travels when it is copied from another paper."""
    return (
        "Вариант №2\n"
        + "".join(_russian_question(n) for n in range(1, 10))
        + "10. Тәуелсіздік қай жылы жарияланды?\nA) 1991\nB) 1995\nЖауабы: A\n"
    )


def _languages(text: str) -> list[str]:
    return [q.language for q in parse_ent_pdf_questions(text).questions]


# ─────────────────────────────────────────────────────────────────────────
# 1. The variant decides; a question inherits
# ─────────────────────────────────────────────────────────────────────────


def test_a_neutral_question_inherits_the_kazakh_variant():
    """The headline case: nine Kazakh questions and one that is nothing but
    digits. Classified on its own text the tenth is indistinguishable from a
    Russian one, and would be dropped from every Kazakh simulation."""
    languages = _languages(kazakh_paper_with_one_neutral_question())

    assert len(languages) == 10
    assert languages == [KAZAKH] * 10


def test_a_kazakh_paper_of_mostly_formulas_is_still_kazakh():
    """A maths variant carries very little prose. What prose it has is the
    whole evidence, so questions with no Cyrillic at all must not be allowed
    to outvote it."""
    text = (
        "1. Дұрыс жауапты таңдаңыз: 2 + 2\nA) 3\nB) 4\nЖауабы: B\n"
        "2. 5 * 5\nA) 20\nB) 25\nЖауабы: B\n"
        "3. 9 / 3\nA) 2\nB) 3\nЖауабы: B\n"
    )
    assert _languages(text) == [KAZAKH] * 3


def test_a_file_with_no_kazakh_signal_anywhere_is_russian():
    assert _languages("".join(_russian_question(n) for n in (1, 2, 3))) == [RUSSIAN] * 3


def test_each_variant_of_a_bilingual_file_is_classified_on_its_own():
    """The same collection printed twice, Russian block then Kazakh block --
    the shape this whole feature exists for."""
    text = (
        "Вариант №1\n" + "".join(_russian_question(n) for n in (1, 2, 3))
        + "Вариант №2\n" + "".join(_kazakh_question(n) for n in (1, 2, 3))
    )
    result = parse_ent_pdf_questions(text)

    by_variant = {q.variant_id: q.language for q in result.questions}
    assert by_variant == {1: RUSSIAN, 2: KAZAKH}
    assert [q.language for q in result.questions] == [RUSSIAN] * 3 + [KAZAKH] * 3


# ─────────────────────────────────────────────────────────────────────────
# 2. ...unless the question proves otherwise, in the one provable direction
# ─────────────────────────────────────────────────────────────────────────


def test_one_kazakh_question_pasted_into_a_russian_variant_overrules_it():
    languages = _languages(russian_paper_with_one_kazakh_question())

    assert languages[:9] == [RUSSIAN] * 9, "one imported question must not relabel the other nine"
    assert languages[9] == KAZAKH


def test_kazakh_names_in_a_russian_question_do_not_overrule_the_variant():
    """"Абай Құнанбаев" is two distinct Kazakh letters in an otherwise
    Russian sentence, and a Russian История Казахстана paper is made of such
    names -- which is why letters alone do not overrule a variant."""
    text = "".join(_russian_question(n) for n in (1, 2, 3)) + (
        "4. В каком году родился Абай Құнанбаев?\n"
        "A) Ыбырай Алтынсарин\nB) Әлихан Бөкейханов\nОтвет: A\n"
    )
    assert _languages(text) == [RUSSIAN] * 4


def test_a_kazakh_question_under_a_russian_answer_key_keeps_the_variants_label():
    """The stated cost of that stricter bar, pinned down rather than left to
    be discovered: with no Kazakh scaffolding word in the block, the question
    inherits `ru` and the teacher flips the flag in the preview."""
    text = "".join(_russian_question(n) for n in (1, 2, 3)) + (
        "4. Тәуелсіздік қай жылы жарияланды?\nA) 1991\nB) 1995\nОтвет: A\n"
    )
    assert _languages(text) == [RUSSIAN] * 4


def test_a_russian_question_inside_a_kazakh_variant_keeps_the_kazakh_label():
    """The asymmetry, stated as a test: Russian has no letter Kazakh lacks,
    so "this one is Russian" is never provable from the text and the parser
    does not pretend otherwise -- the teacher flips it in the preview."""
    text = (
        "Вариант №1\n" + "".join(_kazakh_question(n) for n in range(1, 10))
        + "10. Столица Франции?\nA) Париж\nB) Лион\nОтвет: A\n"
    )
    assert _languages(text)[9] == KAZAKH


@pytest.mark.parametrize(
    ("variant_language", "text", "expected"),
    [
        (RUSSIAN, "Вопрос без сигналов", RUSSIAN),
        # Letters and a scaffolding word: Kazakh prose, not a Kazakh noun.
        (RUSSIAN, "Қай қала астана? Дұрыс жауабы: Астана", KAZAKH),
        (RUSSIAN, "Город Өскемен", RUSSIAN),
        (RUSSIAN, "Кто такой Абай Құнанбаев?", RUSSIAN),
        (KAZAKH, "Вопрос без сигналов", KAZAKH),
        (KAZAKH, "Қай қала?", KAZAKH),
    ],
    ids=["neutral-in-ru", "kazakh-prose-in-ru", "one-name-in-ru", "two-names-in-ru", "neutral-in-kk", "kk-in-kk"],
)
def test_question_language(variant_language, text, expected):
    assert question_language(text, variant_language) == expected


# ─────────────────────────────────────────────────────────────────────────
# 3. The signals themselves
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    ["Дұрыс жауабы", "Қала", "Сәйкестендіріңіз", "Ұлытау", "Төмендегі"],
    ids=["durys", "qala", "match", "ulytau", "tomendegi"],
)
def test_kazakh_only_letters_are_the_primary_signal(text):
    assert detect_language(text) == KAZAKH


@pytest.mark.parametrize(
    "text",
    ["Жауабы: A", "Тапсырма 5", "9 сынып", "Жауап"],
    ids=["zhauaby", "tapsyrma", "synyp", "zhauap"],
)
def test_kazakh_words_spelled_with_russian_letters_are_caught_by_the_keyword_list(text):
    """These carry none of the nine letters, which is the only reason the
    keyword list exists -- everything else is already covered."""
    assert kazakh_signal(text).letters == 0
    assert detect_language(text) == KAZAKH


@pytest.mark.parametrize(
    "text",
    [
        "Столица Франции?",
        "Выберите правильный ответ:",
        "Ответ: Париж",
        "2 + 2 = ?",
        "",
    ],
    ids=["question", "instruction", "key", "formula", "empty"],
)
def test_russian_and_neutral_text_carry_no_signal(text):
    assert detect_language(text) is None, "neutral text must abstain, not vote Russian"


def test_a_repeated_word_is_one_piece_of_evidence_not_forty():
    once = kazakh_signal("Қала")
    many = kazakh_signal("Қала " * 40)

    assert once.letters == many.letters == 1


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        ([], RUSSIAN),
        (["2 + 2 = ?", "5 * 5"], RUSSIAN),  # nothing to go on
        (["Қандай қала?", "2 + 2 = ?"], KAZAKH),  # the abstainer does not outvote
        (["Қандай қала?", "Столица Франции?"], RUSSIAN),  # a tie is not a majority
        (["Қандай қала?", "Қай жыл?", "Столица Франции?"], KAZAKH),
    ],
    ids=["no-questions", "all-neutral", "abstention-ignored", "tie", "majority"],
)
def test_detect_variant_language(texts, expected):
    assert detect_variant_language(texts) == expected


# ─────────────────────────────────────────────────────────────────────────
# 4. The label survives the trip to the preview and back into the bank
# ─────────────────────────────────────────────────────────────────────────


def test_language_reaches_the_import_payload_and_the_response_schema():
    question = parse_ent_pdf_questions(kazakh_paper_with_one_neutral_question()).questions[0]
    payload = to_import_payload(question)

    assert payload.language == KAZAKH
    assert EntQuestionImportOut(
        qtype=payload.qtype,
        text=payload.text,
        language=payload.language,
        max_score=payload.max_score,
        confidence=payload.confidence,
        needs_review=payload.needs_review,
        detected_qtype=payload.detected_qtype,
    ).language is EntLanguage.kk


def test_a_teacher_override_is_what_gets_saved():
    """The preview posts its own cards back to /bulk-create, so whatever the
    teacher left the flag on -- not what the detector guessed -- is what
    EntQuestionIn validates and the router writes."""
    question = parse_ent_pdf_questions(kazakh_paper_with_one_neutral_question()).questions[0]
    card = EntQuestionImportOut(
        qtype="single",
        text=question.text,
        language=to_import_payload(question).language,
        max_score=1,
        choices=[{"text": "Астана", "is_correct": True}, {"text": "Алматы", "is_correct": False}],
        confidence=0.9,
        needs_review=False,
        detected_qtype="single_choice",
    ).model_dump()
    assert card["language"] is EntLanguage.kk

    card["language"] = "ru"  # the teacher flips the flag on the card
    assert EntQuestionIn.model_validate(card).language is EntLanguage.ru


def test_a_question_saved_without_a_language_is_russian():
    """Every client that predates the split -- and the manual question form
    on its default -- keeps working."""
    saved = EntQuestionIn.model_validate(
        {
            "qtype": "single",
            "text": "Столица Франции?",
            "choices": [{"text": "Париж", "is_correct": True}, {"text": "Лион", "is_correct": False}],
        }
    )
    assert saved.language is EntLanguage.ru


@pytest.mark.parametrize("value", ["kz", "RU", "russian", "", "en"])
def test_an_unknown_language_is_rejected_at_the_api_boundary(value):
    with pytest.raises(ValidationError):
        EntQuestionIn.model_validate(
            {
                "qtype": "single",
                "text": "Вопрос?",
                "language": value,
                "choices": [{"text": "Да", "is_correct": True}, {"text": "Нет", "is_correct": False}],
            }
        )


# ─────────────────────────────────────────────────────────────────────────
# 5. What the simulation endpoint leans on
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("value", "expected"), [("ru", EntLanguage.ru), ("kk", EntLanguage.kk)])
def test_parse_language_accepts_the_two_supported_values(value, expected):
    assert parse_language(value) is expected


@pytest.mark.parametrize("value", ["kz", "RU", "kazakh", "", "ru ", None])
def test_parse_language_rejects_anything_else(value):
    with pytest.raises(UnknownLanguageError) as excinfo:
        parse_language(value)

    assert "'ru'" in str(excinfo.value) and "'kk'" in str(excinfo.value), "say what is allowed"


def test_the_language_filter_narrows_the_subject_query_rather_than_replacing_it():
    """Losing the subject condition would draw Kazakh questions from every
    subject in the bank -- a bug that produces a plausible-looking exam."""
    sql = str(
        select(EntQuestion.id)
        .where(*question_pool_filters(7, EntLanguage.kk, EntQuestionType.single))
        .compile(compile_kwargs={"literal_binds": True})
    )

    assert "ent_questions.subject_id = 7" in sql
    assert "ent_questions.language = 'kk'" in sql
    assert "ent_questions.qtype = 'single'" in sql


def test_the_qtype_filter_is_optional():
    sql = str(
        select(EntQuestion.id)
        .where(*question_pool_filters(7, EntLanguage.ru))
        .compile(compile_kwargs={"literal_binds": True})
    )

    assert "ent_questions.subject_id = 7" in sql
    assert "ent_questions.language = 'ru'" in sql
    assert "qtype" not in sql


def test_the_shortage_message_names_the_subject_and_both_numbers():
    message = shortage_message(EntLanguage.kk, [QuestionShortage("Химия", needed=20, available=6)])

    assert "казахском" in message
    assert "«Химия»" in message
    assert "нужно 20" in message and "доступно 6" in message


def test_the_shortage_message_names_the_question_type_when_quotas_are_configured():
    message = shortage_message(
        EntLanguage.kk,
        [QuestionShortage("Физика", needed=10, available=3, qtype=EntQuestionType.matching)],
    )

    assert "«Физика»" in message and "сопоставление" in message


def test_every_short_subject_is_reported_at_once():
    """One subject at a time would mean starting the simulation, reading the
    error, importing, and hitting the next one."""
    message = shortage_message(
        EntLanguage.ru,
        [QuestionShortage("Химия", 20, 6), QuestionShortage("Биология", 15, 0)],
    )

    assert "«Химия»" in message and "«Биология»" in message


# ─────────────────────────────────────────────────────────────────────────
# 6. Degenerate input still comes back labelled
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Вариант №1\n",
        "1. Вопрос без структуры\n))) (((\nОтвет:\n",
        "Вариант №1\n1. Сұрақ?\n))) (((\nЖауабы:\n",
    ],
    ids=["empty", "header-only", "ruined-ru", "ruined-kk"],
)
def test_every_question_comes_back_with_a_valid_language(text):
    for question in parse_ent_pdf_questions(text).questions:
        assert question.language in (RUSSIAN, KAZAKH)
        assert to_import_payload(question).language == question.language
