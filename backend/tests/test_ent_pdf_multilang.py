"""Acceptance tests for the fault-tolerant multi-language layer over the FSM.

The layer's whole risk is that "normalizing" a document quietly destroys
it, so most of these tests assert what must *not* happen: a Cyrillic letter
inside a sentence is not a marker, a line break before a marker is not
closed up, and one broken variant out of fifty does not cost the other
forty-nine. The two regressions the FSM was written for live in
``test_ent_pdf_import.py`` and are unchanged.

Invisible characters are written as ``chr(...)`` rather than pasted in:
a test whose subject is a zero-width space cannot afford to have that
space silently eaten by an editor, and the codepoint says which one it is.
"""
import pytest

from app.core import ent_pdf_import
from app.core.ent_pdf_import import (
    EMPTY_TEXT_WARNING,
    canonical_letter,
    join_wrapped_lines,
    normalize_typography,
    parse_ent_pdf_questions,
    preprocess,
    split_options_in_line,
    split_variants,
    to_import_payload,
)

NBSP = chr(0x00A0)
LAQUO, RAQUO = chr(0x00AB), chr(0x00BB)
FIGURE_DASH = chr(0x2012)
EN_DASH, EM_DASH = chr(0x2013), chr(0x2014)
HORIZONTAL_BAR = chr(0x2015)
MINUS_SIGN = chr(0x2212)
NB_HYPHEN = chr(0x2011)
LDQUO, RDQUO, RSQUO = chr(0x201C), chr(0x201D), chr(0x2019)
ZWSP, ZWNJ, ZWJ, BOM = chr(0x200B), chr(0x200C), chr(0x200D), chr(0xFEFF)

# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────

KAZAKH_HOMOGLYPH = """\
1. Қазақстанның астанасы қай қала?
Ә) Астана
B) Алматы
Жауабы: A
"""

FOUR_OPTIONS_ONE_KEY = """\
1. Какая планета ближе всего к Солнцу?
A) Меркурий
B) Венера
C) Земля
D) Марс
Ответ: C
"""

MIXED_TYPOGRAPHY = (
    f"1. {LAQUO}Жидкость{RAQUO} {EM_DASH} это состояние?{NBSP}\n"
    f"| A) {ZWSP}Первый{ZWSP} |\n"
    f"| B) Второй{NB_HYPHEN}третий |\n"
    "Ответ: A\n"
)


def _variant_paper(count: int = 50, broken: int = 23) -> str:
    """`count` variants of two questions each, one of them structurally
    ruined -- the shape of a real ЕНТ collection with one bad scan."""
    blocks: list[str] = []
    for number in range(1, count + 1):
        blocks.append(f"Вариант №{number}")
        if number == broken:
            blocks.append("1. Вопрос без структуры\n))) (((\nОтвет:")
            continue
        blocks.append(
            f"1. Первый вопрос варианта {number}?\n"
            "A) Первый\nB) Второй\nC) Третий\nD) Четвёртый\nОтвет: B"
        )
        blocks.append(f"2. Второй вопрос варианта {number}?\nA) Да\nB) Нет\nОтвет: A")
    return "\n".join(blocks) + "\n"


# ─────────────────────────────────────────────────────────────────────────
# 1. Homoglyphs: a Kazakh label and a Latin key must meet in the middle
# ─────────────────────────────────────────────────────────────────────────


def test_kazakh_option_label_resolves_against_a_latin_key():
    question = parse_ent_pdf_questions(KAZAKH_HOMOGLYPH).questions[0]

    assert [option.label for option in question.options] == ["A", "B"]
    assert question.options[0].raw_label == "Ә", "the printed glyph must survive for the UI"
    assert question.answer_variants == ["A"]
    assert question.qtype == "single_choice"
    assert to_import_payload(question).choices == [("Астана", True), ("Алматы", False)]


@pytest.mark.parametrize("phrase", ["Жауабы", "Дұрыс жауабы", "Жауаптары"], ids=["zhauaby", "durys", "zhauaptary"])
def test_kazakh_key_phrases_are_recognized(phrase):
    question = parse_ent_pdf_questions(f"1. Сұрақ?\nA) Бір\nB) Екі\n{phrase}: B\n").questions[0]

    assert question.answer_variants == ["B"]


def test_kazakh_matching_hint_blocks_the_numeric_split():
    text = (
        "1. Сәйкестендіріңіз:\n"
        "1. Бірінші\n2. Екінші\n"
        "A) Анықтама A\nB) Анықтама B\n"
        "Жауабы: 1-B, 2-A\n"
    )
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 1
    assert result.questions[0].qtype == "matching"


@pytest.mark.parametrize(
    ("glyph", "expected"),
    [
        ("A", "A"),
        ("a", "A"),
        ("Ә", "A"),  # Kazakh -> nearest Latin analogue
        ("Ғ", "G"),
        ("Һ", "H"),
        ("С", "C"),  # Cyrillic es, drawn as Latin C
        ("Б", "B"),  # ...but Б is positional: second letter of А Б В Г
        ("В", "C"),  # ...so В is the third, not Latin B
        ("Ж", "G"),
        ("Ю", None),
        ("7", None),
    ],
    ids=["lat-A", "lat-a", "kaz-AE", "kaz-GH", "kaz-HH", "cyr-S", "cyr-B", "cyr-V", "cyr-ZH", "cyr-YU", "digit"],
)
def test_canonical_letter(glyph, expected):
    assert canonical_letter(glyph) == expected


def test_canonicalization_never_touches_the_body_text():
    """The homoglyph table must be applied to markers only. Applied to the
    document it would rewrite every Russian and Kazakh word containing А,
    В, Е, С, О or Р."""
    text = "1. Сколько ОСНОВНЫХ ТОНОВ?\nA) Семь\nB) Восемь\nОтвет: A\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert question.text == "Сколько ОСНОВНЫХ ТОНОВ?"
    assert [option.text for option in question.options] == ["Семь", "Восемь"]


# ─────────────────────────────────────────────────────────────────────────
# 2. A letter inside a sentence is not an option marker
# ─────────────────────────────────────────────────────────────────────────


def test_single_letter_word_is_not_read_as_an_option():
    text = (
        "1. Учёный проверил гипотезу.\n"
        "А, значит, вывод такой.\n"
        "A) Первый\nB) Второй\nC) Третий\n"
        "Ответ: B\n"
    )
    question = parse_ent_pdf_questions(text).questions[0]

    assert "значит" in question.text, "the sentence belongs to the question, not to an option"
    assert [option.label for option in question.options] == ["A", "B", "C"]
    assert [option.text for option in question.options] == ["Первый", "Второй", "Третий"]


def test_a_lone_marker_far_into_the_alphabet_is_not_an_option():
    """"Д. Значит..." matches the marker regex exactly. Only the run check
    (§3.2) can tell it from option 5, since nothing about the line itself
    is different."""
    text = "1. Вопрос?\nД. Значит, вывод такой.\nA) Первый\nB) Второй\nОтвет: A\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert "Значит" in question.text
    assert [option.label for option in question.options] == ["A", "B"]


@pytest.mark.parametrize(
    ("line", "previous_index", "expected"),
    [
        # With no run behind it a marker may only open at A or B.
        ("A) Первый", None, ["A"]),
        ("Б) Второй", None, ["B"]),
        ("Д. Значит, вывод такой.", None, []),
        ("Е) Пятый", None, []),
        # ...but it is accepted once the run reaches it.
        ("Д) Пятый", 3, ["E"]),
        # One missing option is tolerated, a bigger jump is not.
        ("D) Четвёртый", 1, ["D"]),
        ("E) Пятый", 1, []),
        # Going backwards or repeating is never a continuation.
        ("A) Первый", 2, []),
        ("C) Третий", 2, []),
        # Two or more consecutive markers need no context at all: that is
        # what keeps the column-typeset regression case working.
        ("E) Текст E F) Текст F", None, ["E", "F"]),
    ],
    ids=[
        "opens-at-A",
        "opens-at-B-cyrillic",
        "lone-E-as-sentence",
        "lone-F-too-far",
        "continues-run",
        "one-gap-tolerated",
        "gap-too-wide",
        "goes-backwards",
        "repeats",
        "two-markers-need-no-context",
    ],
)
def test_split_options_in_line_run_validation(line, previous_index, expected):
    assert [o.label for o in split_options_in_line(line, previous_index)] == expected


# ─────────────────────────────────────────────────────────────────────────
# 3. Fifty variants, one broken
# ─────────────────────────────────────────────────────────────────────────


def test_fifty_variants_one_broken_keeps_the_other_fortynine():
    result = parse_ent_pdf_questions(_variant_paper(50, broken=23))

    assert result.stats.variants_detected == 50
    intact = [q for q in result.questions if q.variant_id != 23]
    assert len(intact) == 49 * 2, "a ruined variant must not cost the others a question"
    assert {q.variant_id for q in intact} == set(range(1, 51)) - {23}
    assert all(q.confidence == 0.9 and not q.needs_review for q in intact)

    broken = [q for q in result.questions if q.variant_id == 23]
    assert broken and all(q.needs_review for q in broken), "the bad variant is flagged, not dropped"


def test_variant_label_and_id_reach_the_question():
    result = parse_ent_pdf_questions("Вариант №7\n1. Вопрос?\nA) Да\nB) Нет\nОтвет: A\n")
    question = result.questions[0]

    assert question.variant_id == 7
    assert question.variant_label == "Вариант №7"
    assert to_import_payload(question).variant_label == "Вариант №7"


def test_a_variant_that_raises_keeps_what_it_had_and_names_itself(monkeypatch):
    """Isolation is a property of the loop, not of the input, so it is
    tested by making one variant genuinely raise."""
    real = ent_pdf_import.split_options_in_line

    def exploding(text, previous_index=None):
        if "ВЗРЫВ" in text:
            raise RuntimeError("boom")
        return real(text, previous_index)

    monkeypatch.setattr(ent_pdf_import, "split_options_in_line", exploding)

    text = (
        "Вариант №1\n1. Первый?\nA) Да\nB) Нет\nОтвет: A\n"
        "Вариант №2\n1. Целый?\nA) Да\nB) Нет\nОтвет: B\n"
        "2. Сломанный?\nA) ВЗРЫВ\nB) Нет\nОтвет: A\n"
        "Вариант №3\n1. Третий?\nA) Да\nB) Нет\nОтвет: A\n"
    )
    result = parse_ent_pdf_questions(text)

    by_variant = {q.variant_id: q for q in result.questions}
    assert set(by_variant) == {1, 2, 3}, "variants either side of the failure survive"
    assert by_variant[2].text.startswith("Целый"), "and so does what variant 2 had already read"

    assert [e.variant_id for e in result.stats.variant_errors] == [2]
    assert result.stats.variant_errors[0].variant_label == "Вариант №2"
    assert "boom" in result.stats.variant_errors[0].error


def test_text_before_the_first_variant_header_is_kept():
    text = (
        "1. Вопрос без заголовка?\nA) Да\nB) Нет\nОтвет: A\n"
        "Вариант №1\n2. Вопрос варианта?\nA) Да\nB) Нет\nОтвет: B\n"
    )
    result = parse_ent_pdf_questions(text)

    assert [q.variant_id for q in result.questions] == [0, 1]
    assert result.questions[0].variant_label is None


def test_question_numbering_restarts_in_every_variant():
    """Each variant numbers its questions from 1. Segmenting first is what
    stops the second variant's "1." from looking like a step backwards."""
    text = "".join(
        f"Вариант №{n}\n1. Первый {n}?\nA) Да\nB) Нет\nОтвет: A\n"
        f"2. Второй {n}?\nA) Да\nB) Нет\nОтвет: B\n"
        for n in (1, 2, 3)
    )
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 6
    assert [q.id for q in result.questions] == [f"q_{i}" for i in range(1, 7)]


@pytest.mark.parametrize(
    "header",
    ["Вариант №4", "Вариант 4", "ВАРИАНТ N 4", "4-нұсқа", "Нұсқа №4", "Тест 4"],
    ids=["hash", "bare", "latin-N-upper", "kaz-suffix", "kaz-prefix", "test"],
)
def test_variant_triggers(header):
    lines = join_wrapped_lines(preprocess(f"{header}\n1. Вопрос?\nA) Да\nB) Нет\nОтвет: A\n"))
    segments, duplicates = split_variants(lines)

    assert [s.variant_id for s in segments] == [4]
    assert segments[0].label == header
    assert duplicates == 0


def test_a_variant_word_inside_a_question_does_not_cut_the_file():
    text = "1. Какой вариант 3 является верным?\nA) Да\nB) Нет\nОтвет: A\n"
    result = parse_ent_pdf_questions(text)

    assert result.stats.variants_detected == 1
    assert len(result.questions) == 1


# ─────────────────────────────────────────────────────────────────────────
# 4. Wrapped lines are rejoined -- but never across a marker
# ─────────────────────────────────────────────────────────────────────────


def test_a_wrapped_sentence_is_rejoined():
    lines = join_wrapped_lines(preprocess("1. Вопрос, который не поместился\nв одну строку?\n"))

    assert [line.text for line in lines] == ["1. Вопрос, который не поместился в одну строку?", ""]


def test_a_break_before_a_variant_header_is_not_closed_up():
    text = (
        "Вариант №1\n1. Первый?\nA) Да\nB) Нет\nОтвет: A\n"
        "Продолжение пояснения без точки\n"
        "Вариант №2\n1. Второй?\nA) Да\nB) Нет\nОтвет: B\n"
    )
    result = parse_ent_pdf_questions(text)

    assert result.stats.variants_detected == 2, "the header must not be swallowed by the line above"
    assert {q.variant_id for q in result.questions} == {1, 2}


@pytest.mark.parametrize(
    "marker",
    ["A) Первый", "2. Следующий вопрос?", "Ответ: A", "Вопрос 2: Следующий?", "Вариант №2"],
    ids=["option", "number", "key", "explicit-question", "variant"],
)
def test_a_break_before_any_marker_is_not_closed_up(marker):
    lines = join_wrapped_lines(preprocess(f"Текст без завершающей пунктуации\n{marker}\n"))

    assert [line.text for line in lines][:2] == ["Текст без завершающей пунктуации", marker]


@pytest.mark.parametrize("ending", [".", "!", "?", ":", ";"])
def test_a_finished_sentence_is_not_joined_to_the_next_line(ending):
    lines = join_wrapped_lines(preprocess(f"Законченная мысль{ending}\nСледующая мысль\n"))

    assert [line.text for line in lines][:2] == [f"Законченная мысль{ending}", "Следующая мысль"]


def test_a_dangling_marker_does_not_absorb_the_line_below_it():
    """"A)" alone means the option's text wrapped. Joining downward here
    would move the marker into the previous line and lose the option."""
    lines = join_wrapped_lines(preprocess("1. Вопрос?\nA)\nтекст варианта\n"))

    assert [line.text for line in lines][:3] == ["1. Вопрос?", "A)", "текст варианта"]


# ─────────────────────────────────────────────────────────────────────────
# 5. single_choice, stated explicitly
# ─────────────────────────────────────────────────────────────────────────


def test_four_options_and_one_key_letter_is_single_choice():
    question = parse_ent_pdf_questions(FOUR_OPTIONS_ONE_KEY).questions[0]

    assert question.qtype == "single_choice", "one letter in the key is one correct answer"
    assert question.answer_variants == ["C"]
    assert question.confidence == 0.9
    assert question.needs_review is False

    payload = to_import_payload(question)
    assert payload.qtype == "single"
    assert payload.max_score == 1
    assert sum(1 for _, correct in payload.choices if correct) == 1
    assert payload.choices[2] == ("Земля", True)


def test_the_same_four_options_with_two_key_letters_is_multiple_choice():
    text = FOUR_OPTIONS_ONE_KEY.replace("Ответ: C", "Ответ: A, C")
    question = parse_ent_pdf_questions(text).questions[0]

    assert question.qtype == "multiple_choice"
    assert question.answer_variants == ["A", "C"]


def test_choice_labels_travel_with_the_payload():
    payload = to_import_payload(parse_ent_pdf_questions(KAZAKH_HOMOGLYPH).questions[0])

    assert len(payload.choice_labels) == len(payload.choices)
    assert payload.choice_labels == [("A", "Ә"), ("B", "B")]


# ─────────────────────────────────────────────────────────────────────────
# 6. Typographic junk normalizes without losing text
# ─────────────────────────────────────────────────────────────────────────


def test_mixed_typography_normalizes_without_losing_words():
    result = parse_ent_pdf_questions(MIXED_TYPOGRAPHY)

    assert result.stats.parse_errors == []
    question = result.questions[0]
    assert question.text == '"Жидкость" - это состояние?'
    assert [o.text for o in question.options] == ["Первый", "Второй-третий"]
    assert question.answer_variants == ["A"]
    assert question.confidence == 0.9


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (FIGURE_DASH + EN_DASH + EM_DASH + HORIZONTAL_BAR + MINUS_SIGN, "-----"),
        (LAQUO + LDQUO + RDQUO + RSQUO, '""""'),
        ("два" + NBSP + "слова", "два слова"),
        ("слово" + ZWSP + ZWNJ + ZWJ + BOM, "слово"),
        ("| ячейка |", " ячейка "),
        ("a|b", "a|b"),  # inside a word it is content, not a table rule
        ("строка\r\nвторая", "строка\nвторая"),
    ],
    ids=["dashes", "quotes", "nbsp", "zero-width", "table-pipes", "pipe-in-word", "crlf"],
)
def test_normalize_typography(raw, expected):
    assert normalize_typography(raw) == expected


def test_normalization_preserves_the_line_count():
    """The colour-mark index is keyed by physical line number, so a
    normalization that added or dropped a line would silently misattribute
    every highlight after it."""
    raw = f"первая строка\n{ZWSP}вторая|\nтретья{EM_DASH}строка\n"
    assert normalize_typography(raw).count("\n") == raw.count("\n")


def test_marks_survive_a_join():
    """A highlight that spanned a wrapped option still covers the option
    once the two lines are one."""
    text = "1. Вопрос?\nA) вариант\nпродолжение\nB) второй\nОтвет: A\n"
    marks = {1: ("вариант",), 2: ("продолжение",)}
    question = parse_ent_pdf_questions(text, marks).questions[0]

    assert question.options[0].text == "вариант продолжение"
    assert question.options[0].marked is True
    assert question.options[1].marked is False


# ─────────────────────────────────────────────────────────────────────────
# 7. Extra question-number formats
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "marker",
    ["1.", "1)", "1 -", "[1]", "№1", "Вопрос 1:", "1-сұрақ:"],
    ids=["dot", "paren", "dash", "brackets", "numero", "word", "kazakh"],
)
def test_question_number_formats(marker):
    result = parse_ent_pdf_questions(f"{marker} Вопрос?\nA) Да\nB) Нет\nОтвет: A\n")

    assert len(result.questions) == 1, marker
    assert result.questions[0].text == "Вопрос?"


def test_a_pairing_key_is_not_read_as_a_dash_numbered_question():
    """"1-C, 2-B" and "1 - Текст" differ only by the space after the dash."""
    text = "1. Сопоставьте:\n1. Первое\n2. Второе\nA) A\nB) B\nОтвет: 1-B, 2-A\n"
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 1
    assert len(result.questions[0].match_pairs) == 2


def test_an_all_caps_word_is_not_read_as_a_key_of_letters():
    question = parse_ent_pdf_questions("1. Как называлась страна?\nОтвет: СССР\n").questions[0]

    assert question.qtype == "short_answer"
    assert question.answer_text == "СССР"


# ─────────────────────────────────────────────────────────────────────────
# 8. Degenerate input never raises and never returns a bare empty list
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    ["", "   ", "\n\n\n", ZWSP * 2, "  \n"],
    ids=["empty", "spaces", "newlines", "zero-width-only", "space-and-newline"],
)
def test_a_file_with_no_text_says_so(text):
    result = parse_ent_pdf_questions(text)

    assert result.questions == []
    assert result.warnings == [EMPTY_TEXT_WARNING]


@pytest.mark.parametrize(
    "text",
    [
        "Вариант №1\n" * 500,
        "Вариант №1\nВариант №2\nВариант №3\n1. Вопрос?\nA) Да\nB) Нет\nОтвет: A\n",
        "\x00\x01\x02 мусор\nВариант №1\n" + "|" * 500,
        "Вариант №1\n1. " + "я" * 20_000 + "\nA) " + "x" * 20_000 + "\nОтвет: A\n",
        ZWSP * 5_000 + "\n1. Вопрос?\nA) Да\nB) Нет\nОтвет: A\n",
    ],
    ids=["empty-variants", "consecutive-headers", "control-chars", "huge-lines", "zero-width-flood"],
)
def test_pathological_input_never_raises(text):
    result = parse_ent_pdf_questions(text)

    assert isinstance(result.questions, list)
    for question in result.questions:
        assert 0.0 <= question.confidence <= 1.0
        payload = to_import_payload(question)
        assert payload.qtype in ("single", "multiple", "matching", "short_answer")
        assert len(payload.choice_labels) == len(payload.choices)


def test_segmentation_failure_degrades_to_a_single_variant(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("segmentation died")

    monkeypatch.setattr(ent_pdf_import, "split_variants", explode)
    result = parse_ent_pdf_questions("Вариант №1\n1. Вопрос?\nA) Да\nB) Нет\nОтвет: A\n")

    assert len(result.questions) == 1, "the file is still parsed, just not split"
    assert any("варианты" in w for w in result.warnings)
