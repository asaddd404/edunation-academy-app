"""Acceptance tests for the FSM-based ЕНТ PDF question parser.

The two regressions this rewrite exists for are covered first (a matching
question's own numbered list must not split it; column-typeset options on
one line must not merge), followed by the robustness guarantees: nothing
raises, nothing is silently dropped.
"""
import pytest

from app.core.ent_pdf_import import (
    ParsedOption,
    classify_line,
    determine_qtype,
    parse_ent_pdf_questions,
    parse_key,
    preprocess,
    run_fsm,
    score_confidence,
    split_options_in_line,
    to_import_payload,
)

# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────

MATCHING_WITH_NUMBERED_LIST = """\
1. Сопоставьте заболевание и возбудителя:
1. Дизентерия
2. Малярия
3. Туберкулёз
4. Холера
A) Plasmodium
B) Shigella
C) Mycobacterium
D) Vibrio
Ответ: 1-B, 2-A, 3-C, 4-D
"""

COLUMN_OPTIONS = """\
1. Укажите несколько верных ответов о клетке:
E) Текст E   F) Текст F   G) Текст G   H) Текст H
Ответ: E, F
"""

NO_KEY = """\
1. Столица Франции?
A) Париж
B) Лондон
C) Берлин
"""


def _build_reference_exam(count: int = 20) -> str:
    """A 20-question document mixing every supported shape, including the
    two patterns that used to break the parser."""
    blocks: list[str] = ["ПРЕДМЕТ: Биология", "=========="]
    for number in range(1, count + 1):
        if number % 5 == 1:
            blocks.append(
                f"{number}. Сопоставьте понятие и определение:\n"
                "1. Первое\n2. Второе\n3. Третье\n"
                "A) Определение A\nB) Определение B\nC) Определение C\n"
                f"Ответ: 1-C, 2-A, 3-B"
            )
        elif number % 5 == 2:
            blocks.append(
                f"{number}. Выберите несколько верных утверждений:\n"
                "E) Текст E   F) Текст F   G) Текст G   H) Текст H\n"
                "Ответ: E, G"
            )
        elif number % 5 == 3:
            blocks.append(f"{number}. Вопрос с кратким ответом номер {number}?\nОтвет: Астана")
        else:
            blocks.append(
                f"{number}. Обычный вопрос номер {number}?\n"
                "A) Первый\nB) Второй\nC) Третий\nD) Четвёртый\n"
                "Ответ: B"
            )
        if number % 7 == 0:
            blocks.append(f"Страница {number} из {count}")
    return "\n\n".join(blocks) + "\n"


# ─────────────────────────────────────────────────────────────────────────
# 1. Regression: bug #1 -- false split
# ─────────────────────────────────────────────────────────────────────────


def test_matching_question_with_numbered_list_stays_one_block():
    result = parse_ent_pdf_questions(MATCHING_WITH_NUMBERED_LIST)

    assert len(result.questions) == 1, "numbered prompt list must not split the question"
    question = result.questions[0]
    assert question.qtype == "matching"
    assert "Дизентерия" in question.text and "Холера" in question.text
    assert [option.label for option in question.options] == ["A", "B", "C", "D"]
    assert [(pair.left, pair.right) for pair in question.match_pairs] == [
        ("1", "B"),
        ("2", "A"),
        ("3", "C"),
        ("4", "D"),
    ]
    assert question.confidence == 0.9
    assert question.needs_review is False


def test_matching_hint_blocks_numeric_split_even_after_options():
    """The "Сопоставьте" guard holds while options are already being read."""
    text = (
        "1. Соотнесите органы и системы:\n"
        "A) Сердце\nB) Лёгкие\n"
        "1. Кровообращение\n2. Дыхание\n"
        "Ответ: 1-A, 2-B\n"
    )
    result = parse_ent_pdf_questions(text)
    assert len(result.questions) == 1


def test_domain_payload_resolves_matching_pairs_to_text():
    question = parse_ent_pdf_questions(MATCHING_WITH_NUMBERED_LIST).questions[0]
    payload = to_import_payload(question)

    assert payload.qtype == "matching"
    assert payload.max_score == 2
    assert payload.match_pairs == [
        ("Дизентерия", "Shigella"),
        ("Малярия", "Plasmodium"),
        ("Туберкулёз", "Mycobacterium"),
        ("Холера", "Vibrio"),
    ]


# ─────────────────────────────────────────────────────────────────────────
# 2. Regression: bug #2 -- false merge
# ─────────────────────────────────────────────────────────────────────────


def test_column_typeset_options_split_into_four():
    result = parse_ent_pdf_questions(COLUMN_OPTIONS)

    assert len(result.questions) == 1
    question = result.questions[0]
    assert [option.label for option in question.options] == ["E", "F", "G", "H"]
    assert [option.text for option in question.options] == [
        "Текст E",
        "Текст F",
        "Текст G",
        "Текст H",
    ]
    assert question.qtype == "multiple_choice"
    assert question.answer_variants == ["E", "F"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        # Single option on its own line.
        ("A) Один вариант", [("A", "Один вариант")]),
        # Bug #2, as it appears in the PDF (wide column gaps)...
        (
            "E) Текст E   F) Текст F   G) Текст G   H) Текст H",
            [("E", "Текст E"), ("F", "Текст F"), ("G", "Текст G"), ("H", "Текст H")],
        ),
        # ...and after preprocessing has collapsed those gaps, which is the
        # form the FSM actually sees.
        (
            "E) Текст E F) Текст F G) Текст G H) Текст H",
            [("E", "Текст E"), ("F", "Текст F"), ("G", "Текст G"), ("H", "Текст H")],
        ),
        # Prose that merely contains "A)" and "B)": not an options line,
        # because it does not START with a marker. Pinned deliberately --
        # see Rule B in the parser docstring.
        ("Компания A) владеет патентом B) нет", []),
        # A non-consecutive mid-line letter belongs to the option's text.
        ("A. Точка Z) не маркер", [("A", "Точка Z) не маркер")]),
        # Cyrillic labels are canonicalized to their Latin position.
        ("Б) Второй", [("B", "Второй")]),
        # Lowercase is accepted at the start of a line.
        ("a) Первый", [("A", "Первый")]),
        ("Обычная строка текста", []),
    ],
)
def test_split_options_in_line(line, expected):
    assert [(o.label, o.text) for o in split_options_in_line(line)] == expected


def test_wrapped_option_continues_previous_option():
    text = "1. Вопрос?\nA. вариант\nпродолжение варианта\nB. второй\nОтвет: A\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert [o.text for o in question.options] == ["вариант продолжение варианта", "второй"]


# ─────────────────────────────────────────────────────────────────────────
# 3. A question without a key survives, flagged
# ─────────────────────────────────────────────────────────────────────────


def test_question_without_key_is_kept_and_flagged():
    result = parse_ent_pdf_questions(NO_KEY)

    assert len(result.questions) == 1
    question = result.questions[0]
    assert question.needs_review is True
    assert question.confidence == 0.4
    assert question.qtype == "single_choice"
    assert result.stats.needs_review_count == 1


def test_keyless_question_does_not_swallow_the_next_one():
    text = NO_KEY + "2. Столица Италии?\nA) Рим\nB) Милан\nОтвет: A\n"
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 2
    assert result.questions[0].needs_review is True
    assert result.questions[1].confidence == 0.9


# ─────────────────────────────────────────────────────────────────────────
# 4. The first question of a file has no preceding key
# ─────────────────────────────────────────────────────────────────────────


def test_first_question_in_file_is_recognized():
    text = (
        "ПРЕДМЕТ: География\n"
        "==========\n"
        "1. Какая река самая длинная?\n"
        "A) Нил\nB) Амазонка\n"
        "Ответ: A\n"
    )
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 1
    assert result.questions[0].text.startswith("Какая река")
    assert result.questions[0].confidence == 0.9


def test_explicit_marker_opens_a_question_from_any_state():
    text = "Вопрос 1: Первый?\nA) Да\nB) Нет\nВопрос 2: Второй?\nA) Да\nB) Нет\nОтвет: A\n"
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 2


# ─────────────────────────────────────────────────────────────────────────
# 5. A broken block must not sink the import
# ─────────────────────────────────────────────────────────────────────────


def test_malformed_input_never_raises():
    for text in (
        "",
        "\x00\x01\x02 мусор без структуры",
        "1.",
        "1. \n\n\n",
        "Ответ: ",
        "A) сирота без вопроса",
        "1. Вопрос?\nA) " + "x" * 50_000,
        "\n".join(f"{i}." for i in range(200)),
    ):
        result = parse_ent_pdf_questions(text)
        assert isinstance(result.questions, list)
        for question in result.questions:
            assert 0.0 <= question.confidence <= 1.0


def test_failing_block_is_returned_with_zero_confidence(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.core.ent_pdf_import.determine_qtype", explode)
    result = parse_ent_pdf_questions(NO_KEY)

    assert len(result.questions) == 1, "a block that fails to parse still comes back"
    question = result.questions[0]
    assert question.qtype == "unknown"
    assert question.confidence == 0.0
    assert question.needs_review is True
    assert question.parse_error is not None and "boom" in question.parse_error
    assert result.stats.parse_errors and "boom" in result.stats.parse_errors[0]
    # The teacher still gets the raw text to fix by hand.
    assert "Столица Франции" in question.text


def test_total_failure_returns_empty_result_not_an_exception(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("preprocess died")

    monkeypatch.setattr("app.core.ent_pdf_import.preprocess", explode)
    result = parse_ent_pdf_questions(NO_KEY)

    assert result.questions == []
    assert result.stats.parse_errors == ["RuntimeError: preprocess died"]


def test_import_payload_never_raises_on_a_broken_question():
    result = parse_ent_pdf_questions("1. Вопрос без ничего\n")
    payload = to_import_payload(result.questions[0])

    assert payload.qtype in ("single", "multiple", "matching", "short_answer")
    assert payload.needs_review is True


# ─────────────────────────────────────────────────────────────────────────
# 6. Integration: a 20-question reference document
# ─────────────────────────────────────────────────────────────────────────


def test_reference_exam_yields_exactly_twenty_questions():
    result = parse_ent_pdf_questions(_build_reference_exam(20))

    assert len(result.questions) == 20, [q.text[:40] for q in result.questions]
    assert result.stats.total_blocks_detected == 20
    assert result.stats.parse_errors == []

    by_type: dict[str, int] = {}
    for question in result.questions:
        by_type[question.qtype] = by_type.get(question.qtype, 0) + 1
    assert by_type == {"matching": 4, "multiple_choice": 4, "short_answer": 4, "single_choice": 8}

    # No false merges: every choice question kept all of its options.
    for question in result.questions:
        if question.qtype == "single_choice":
            assert len(question.options) == 4
        if question.qtype == "multiple_choice":
            assert len(question.options) == 4

    assert result.stats.needs_review_count == 0


def test_reference_exam_maps_cleanly_to_the_save_payload():
    result = parse_ent_pdf_questions(_build_reference_exam(20))
    payloads = [to_import_payload(question) for question in result.questions]

    assert len(payloads) == 20
    for payload in payloads:
        assert payload.text
        assert payload.max_score in (1, 2)
        if payload.qtype == "single":
            assert sum(1 for _, correct in payload.choices if correct) == 1
        elif payload.qtype == "multiple":
            assert sum(1 for _, correct in payload.choices if correct) >= 2
            assert payload.max_score == 2
        elif payload.qtype == "matching":
            assert len(payload.match_pairs) >= 2
            assert payload.max_score == 2
        elif payload.qtype == "short_answer":
            assert payload.answer_variants


# ─────────────────────────────────────────────────────────────────────────
# 7. Formats the previous parser already handled must keep working
# ─────────────────────────────────────────────────────────────────────────


def test_cyrillic_options_and_key():
    text = "1. Столица Казахстана?\nА) Алматы\nБ) Астана\nВ) Шымкент\nОтвет: Б\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert [o.text for o in question.options] == ["Алматы", "Астана", "Шымкент"]
    assert question.answer_variants == ["B"]
    payload = to_import_payload(question)
    assert payload.choices == [("Алматы", False), ("Астана", True), ("Шымкент", False)]


def test_key_in_the_other_alphabet_than_the_options():
    """Options labelled in Latin, key typed on a Russian keyboard."""
    text = "1. Вопрос?\nA) Первый\nB) Второй\nC) Третий\nОтвет: В\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert question.answer_variants == ["B"], "Cyrillic В must resolve to Latin B, not C"


def test_short_answer():
    text = "1. Столица Франции?\nОтвет: Париж\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert question.qtype == "short_answer"
    assert question.answer_text == "Париж"
    assert question.confidence == 0.9
    assert to_import_payload(question).answer_variants == ["Париж"]


def test_answer_starting_with_an_option_letter_is_not_read_as_a_key_letter():
    question = parse_ent_pdf_questions("1. Столица Казахстана?\nОтвет: Астана\n").questions[0]

    assert question.qtype == "short_answer"
    assert question.answer_text == "Астана"


def test_word_beginning_like_a_key_phrase_is_not_a_key():
    text = "1. Что такое ответственность - это качество личности?\nA) Да\nB) Нет\nОтвет: A\n"
    question = parse_ent_pdf_questions(text).questions[0]

    assert "ответственность" in question.text
    assert question.answer_variants == ["A"]


@pytest.mark.parametrize(
    "stem",
    [
        "Выберите несколько верных ответов:",
        "Укажите правильные ответы:",
        "Отметьте все верные ответы:",
    ],
)
def test_instruction_ending_in_key_words_is_not_a_key(stem):
    """An instruction ends in the same words a key starts with. Reading it
    as a key used to discard the whole question's options."""
    text = f"1. {stem}\nA) Первый\nB) Второй\nC) Третий\nОтвет: A, B\n"
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 1
    question = result.questions[0]
    assert len(question.options) == 3, "the instruction must not swallow the options"
    assert question.answer_variants == ["A", "B"]
    assert question.qtype == "multiple_choice"


def test_question_and_key_on_one_line_keeps_them_apart():
    question = parse_ent_pdf_questions("5. Столица Франции? Ответ: Париж\n").questions[0]

    assert question.text == "Столица Франции?"
    assert question.answer_text == "Париж"


def test_key_followed_by_the_next_question_on_the_same_line():
    text = "1. Первый?\nA) Да\nB) Нет\nОтвет: A 2. Второй?\nA) Да\nB) Нет\nОтвет: B\n"
    result = parse_ent_pdf_questions(text)

    assert len(result.questions) == 2
    assert result.questions[1].text.startswith("Второй")


def test_key_wrapped_onto_a_second_line():
    text = (
        "1. Сопоставьте:\n1. Первое\n2. Второе\n3. Третье\n4. Четвёртое\n"
        "A) A\nB) B\nC) C\nD) D\n"
        "Ответ: 1-A, 2-B\n3-C, 4-D\n"
    )
    question = parse_ent_pdf_questions(text).questions[0]

    assert len(question.match_pairs) == 4


def test_six_options_with_a_single_letter_key_is_single_choice():
    text = (
        "1. Вопрос?\nA) 1\nB) 2\nC) 3\nD) 4\nE) 5\nF) 6\nОтвет: C\n"
    )
    question = parse_ent_pdf_questions(text).questions[0]

    assert question.qtype == "single_choice"
    assert to_import_payload(question).qtype == "single"


# ─────────────────────────────────────────────────────────────────────────
# Unit coverage for the individual stages
# ─────────────────────────────────────────────────────────────────────────


def test_preprocess_collapses_spaces_drops_scaffolding_and_numbers_lines():
    text = "РАЗДЕЛ IV\r\n----------\r\n1.   Вопрос   с   пробелами\r\nСтраница 2 из 9\r\n1. Дизентерия\r\n"
    lines = preprocess(text)

    assert [line.text for line in lines] == ["1. Вопрос с пробелами", "1. Дизентерия", ""]
    assert [line.index for line in lines] == [0, 1, 2]


def test_preprocess_keeps_a_numbered_line_that_carries_content():
    assert preprocess("1. Дизентерия\n")[0].text == "1. Дизентерия"


@pytest.mark.parametrize(
    ("line", "kind", "explicit"),
    [
        ("", "blank", False),
        ("Ответ: A", "key", False),
        ("Ключ: 1-A", "key", False),
        ("Правильный ответ: B", "key", False),
        ("A) вариант", "option", False),
        ("1. Вопрос", "question_marker", False),
        ("Вопрос 3: Текст", "question_marker", True),
        ("[7] Текст", "question_marker", True),
        ("просто текст", "text", False),
    ],
)
def test_classify_line(line, kind, explicit):
    result = classify_line(line)
    assert result.kind.value == kind
    assert result.explicit is explicit


def test_classify_line_reports_a_mid_line_key():
    result = classify_line("5. Столица Франции? Ответ: Париж")
    assert result.kind.value == "question_marker"
    assert result.key_start > 0
    assert result.key_payload == "Париж"


@pytest.mark.parametrize(
    ("payload", "pairs", "variants", "answer_text"),
    [
        ("1-C, 2-B, 3-A, 4-D", [("1", "C"), ("2", "B"), ("3", "A"), ("4", "D")], [], None),
        ("A, B, C", [], ["A", "B", "C"], None),
        ("AC", [], ["A", "C"], None),
        ("B", [], ["B"], None),
        ("Париж", [], [], "Париж"),
        ("42", [], [], "42"),
        ("Астана", [], [], "Астана"),
        ("", [], [], None),
    ],
)
def test_parse_key(payload, pairs, variants, answer_text):
    key = parse_key(payload)
    assert [(p.left, p.right) for p in key.match_pairs] == pairs
    assert key.answer_variants == variants
    assert key.answer_text == answer_text


def test_parse_key_returns_the_tail_after_the_key():
    key = parse_key("A 2. Следующий вопрос?")
    assert key.answer_variants == ["A"]
    assert key.tail == "2. Следующий вопрос?"


def test_run_fsm_records_the_line_range_of_each_block():
    lines = preprocess(MATCHING_WITH_NUMBERED_LIST)
    blocks = run_fsm(lines)

    assert len(blocks) == 1
    assert blocks[0].first_line == 0
    assert blocks[0].last_line == 9


@pytest.mark.parametrize(
    ("options", "key_payload", "text", "expected"),
    [
        ([], "1-A, 2-B", "Сопоставьте", "matching"),
        (["A", "B", "C", "D", "E", "F"], "", "Вопрос", "multiple_choice"),
        (["A", "B"], "A, B", "Вопрос", "multiple_choice"),
        (["A", "B", "C"], "A", "Вопрос", "single_choice"),
        (["A", "B", "C"], "", "Вопрос", "single_choice"),
        ([], "Париж", "Вопрос", "short_answer"),
        ([], "", "Вопрос", "unknown"),
    ],
)
def test_determine_qtype(options, key_payload, text, expected):
    parsed_options = [ParsedOption(label=label, text=label) for label in options]
    key = parse_key(key_payload) if key_payload else None
    assert determine_qtype(text, parsed_options, key) == expected


@pytest.mark.parametrize(
    ("text", "options", "key_payload", "qtype", "expected"),
    [
        ("Вопрос", ["A", "B"], "A", "single_choice", (0.9, False)),
        ("Вопрос", ["A", "B"], "", "single_choice", (0.4, True)),
        ("Вопрос", [], "A", "unknown", (0.4, True)),
        ("Вопрос", [], "", "unknown", (0.3, True)),
        ("", [], "", "unknown", (0.0, True)),
        ("Вопрос", [], "Париж", "short_answer", (0.9, False)),
    ],
)
def test_score_confidence(text, options, key_payload, qtype, expected):
    parsed_options = [ParsedOption(label=label, text=label) for label in options]
    key = parse_key(key_payload) if key_payload else None
    assert score_confidence(text, parsed_options, key, qtype) == expected


def test_stats_are_reported():
    result = parse_ent_pdf_questions(MATCHING_WITH_NUMBERED_LIST + NO_KEY)

    assert result.stats.total_blocks_detected == 2
    assert result.stats.total_lines > 0
    assert result.stats.needs_review_count == 1
    assert result.stats.parse_errors == []


def test_every_question_object_has_all_contract_fields():
    question = parse_ent_pdf_questions(NO_KEY).questions[0]

    for attribute in (
        "id",
        "raw_line_range",
        "qtype",
        "text",
        "options",
        "match_pairs",
        "answer_variants",
        "answer_text",
        "confidence",
        "needs_review",
        "parse_error",
    ):
        assert hasattr(question, attribute), attribute
    assert question.id == "q_1"
    assert len(question.raw_line_range) == 2
