"""Tests for the ruled-table reading path.

A "Сопоставьте" item in a real ЕНТ paper is a ruled two-column table: the
left cell holds the prompt, the right column the options. Text extraction
reads such a row back in *x* order, which interleaves the two columns --

    A) Никель Катализатор, применяемый для B) Бензол получения полиэтилена

-- and from that string neither half is recoverable, because the boundary
between "Никель" and "Катализатор," is invisible in the text. So the
columns are read from the geometry before the text is flattened, and these
tests pin both halves of that contract: the reordering, and the refusal to
reorder anything that is not an option table.
"""
from app.core.ent_pdf_import import (
    column_ordered_table,
    left_column_prompts,
    parse_ent_pdf_questions,
    recover_unstarted_options,
    run_fsm,
    preprocess,
    split_out_of_order_option,
    QuestionBlock,
)


# ─────────────────────────────────────────────────────────────────────────
# column_ordered_table
# ─────────────────────────────────────────────────────────────────────────


def test_one_row_table_holding_the_whole_option_list():
    """The file's commonest shape: one row, the right cell holding A-D."""
    rows = [["Этиленгликоль\nГлицерин", "A) 11\nB) 14\nC) 13\nD) 9"]]
    assert column_ordered_table(rows) == [
        "Этиленгликоль Глицерин",
        "A) 11",
        "B) 14",
        "C) 13",
        "D) 9",
    ]


def test_prompts_override_the_cell_line_breaks():
    """Geometry, when the caller has it, beats the cell's own newlines."""
    rows = [["Этиленгликоль\nГлицерин", "A) 11\nB) 14"]]
    assert column_ordered_table(rows, ["Этиленгликоль", "Глицерин"]) == [
        "Этиленгликоль",
        "Глицерин",
        "A) 11",
        "B) 14",
    ]


def test_options_spread_down_the_rows():
    rows = [
        ["Катализатор при низком\nдавлении", "A) Никель"],
        ["", "B) Бензол"],
        ["", "C) Ортофосфорная кислота"],
    ]
    assert column_ordered_table(rows) == [
        "Катализатор при низком давлении",
        "A) Никель",
        "B) Бензол",
        "C) Ортофосфорная кислота",
    ]


def test_wrapped_option_text_rejoins_its_marker():
    """A cell line that opens no option is the previous option's tail."""
    rows = [["Промпт", "A) Первый вариант\nс переносом\nB) Второй"]]
    assert column_ordered_table(rows) == [
        "Промпт",
        "A) Первый вариант с переносом",
        "B) Второй",
    ]


def test_single_column_table_is_left_alone():
    """This file rules a box around some question stems; it is not a table."""
    assert column_ordered_table([["36. Установите соответствие"], ["состояния хлора:"]]) is None


def test_data_table_keeps_its_reading_order():
    """Rows that mean something only read across must not be reordered."""
    rows = [["Элемент", "Валентность"], ["Кислород", "II"], ["Азот", "III"]]
    assert column_ordered_table(rows) is None


def test_one_option_is_not_a_run():
    assert column_ordered_table([["Промпт", "A) Единственный"]]) is None


def test_empty_table():
    assert column_ordered_table([]) is None


# ─────────────────────────────────────────────────────────────────────────
# left_column_prompts -- geometry, faked at the shape the caller sees
# ─────────────────────────────────────────────────────────────────────────


class _FakeColumn:
    def __init__(self, x0):
        self.bbox = (x0, 0, x0 + 100, 100)


class _FakeCrop:
    def __init__(self, lines):
        self._lines = lines

    def extract_text_lines(self, **_):
        return self._lines


class _FakePage:
    def __init__(self, lines):
        self._lines = lines
        self.cropped_to = None

    def crop(self, bbox):
        self.cropped_to = bbox
        return _FakeCrop(self._lines)


class _FakeTable:
    bbox = (72.0, 70.0, 523.0, 430.0)
    columns = (_FakeColumn(72.0), _FakeColumn(300.0))


def _line(text, top, height=11.0):
    return {"text": text, "top": top, "bottom": top + height}


def test_prompts_split_on_the_vertical_gap():
    """Two prompts a page apart are two items, not one wrapped one."""
    page = _FakePage([_line("Этиленгликоль", 314.1), _line("Глицерин", 355.2)])
    assert left_column_prompts(page, _FakeTable()) == ["Этиленгликоль", "Глицерин"]


def test_wrapped_prompt_stays_one_item():
    """The same shape in text -- three lines -- but one prompt in print."""
    page = _FakePage(
        [
            _line("Катализатор, применяемый для", 79.6),
            _line("получения полиэтилена при низком", 92.3),
            _line("давлении", 104.9),
        ]
    )
    assert left_column_prompts(page, _FakeTable()) == [
        "Катализатор, применяемый для получения полиэтилена при низком давлении"
    ]


def test_wrapped_prompts_and_a_gap_together():
    """Question 40's left column: two prompts, the first of them wrapped."""
    page = _FakePage(
        [
            _line("Используется в медицине как", 536.6),
            _line("успокаивающее средство:", 551.1),
            _line("Участвует в обмене веществ", 618.8),
            _line("щитовидной железы", 633.3),
        ]
    )
    assert left_column_prompts(page, _FakeTable()) == [
        "Используется в медицине как успокаивающее средство:",
        "Участвует в обмене веществ щитовидной железы",
    ]


def test_only_the_left_column_is_read():
    page = _FakePage([_line("Промпт", 80.0)])
    left_column_prompts(page, _FakeTable())
    assert page.cropped_to == (72.0, 70.0, 300.0, 430.0)


def test_unreadable_layout_falls_back_rather_than_raising():
    class _Broken:
        bbox = (0, 0, 0, 0)

        @property
        def columns(self):
            raise RuntimeError("no columns")

    assert left_column_prompts(_FakePage([]), _Broken()) is None


# ─────────────────────────────────────────────────────────────────────────
# Cell boundaries survive the wrap-joiner
# ─────────────────────────────────────────────────────────────────────────

TABLE_TEXT = """\
38. Установите соответствие, связанное с производством полиэтилена:
Катализатор, применяемый для получения полиэтилена при низком давлении
A) Никель
B) Бензол
C) Ортофосфорная кислота
D) Тетрахлорид титана
Катализатор, применяемый для получения полиэтилена при высоком давлении
A) Никель
B) Бензол
C) Ортофосфорная кислота
D) Тетрахлорид титана
39. Следующий вопрос:
A) Первый
B) Второй
"""
# Every line of the table above is a cell (line 0 is the stem, 11 the next
# question) -- which is what extract_pdf_text reports for this block.
TABLE_CELLS = frozenset(range(1, 11))


def test_a_cell_is_never_merged_into_its_neighbour():
    """Without the cell boundary "D) Тетрахлорид титана" and the prompt
    below it -- adjacent, unpunctuated, neither opening a structure -- merge
    into one line and take the next matching pair with them."""
    lines = preprocess(TABLE_TEXT, None, TABLE_CELLS)
    from app.core.ent_pdf_import import join_wrapped_lines

    joined = [line.text for line in join_wrapped_lines(lines)]
    assert "D) Тетрахлорид титана" in joined
    assert "Катализатор, применяемый для получения полиэтилена при высоком давлении" in joined


def test_table_prompts_become_match_left_items():
    result = parse_ent_pdf_questions(TABLE_TEXT, None, TABLE_CELLS)
    matching = result.questions[0]
    assert matching.qtype == "matching"
    assert matching.match_left_items == [
        "Катализатор, применяемый для получения полиэтилена при низком давлении",
        "Катализатор, применяемый для получения полиэтилена при высоком давлении",
    ]
    assert [option.label for option in matching.options] == ["A", "B", "C", "D"]
    assert matching.text == "Установите соответствие, связанное с производством полиэтилена:"


def test_a_reprinted_option_cycle_is_dropped_not_glued():
    """One table per prompt means the options are printed twice. The second
    "A) Никель" continues no run, and appending it to option D's text is the
    one outcome that loses data."""
    matching = parse_ent_pdf_questions(TABLE_TEXT, None, TABLE_CELLS).questions[0]
    assert [(o.label, o.text) for o in matching.options] == [
        ("A", "Никель"),
        ("B", "Бензол"),
        ("C", "Ортофосфорная кислота"),
        ("D", "Тетрахлорид титана"),
    ]


def test_a_repeated_label_with_new_text_is_kept():
    """Only an identical reprint is dropped: a repeated label carrying
    different text is a real option, however oddly it was labelled."""
    from app.core.ent_pdf_import import ParsedOption, repeats_a_collected_option

    collected = [ParsedOption(label="A", text="Никель")]
    assert repeats_a_collected_option("A) Никель", collected)
    assert not repeats_a_collected_option("A) Платина", collected)


def test_the_question_after_a_table_is_still_its_own_question():
    result = parse_ent_pdf_questions(TABLE_TEXT, None, TABLE_CELLS)
    assert len(result.questions) == 2
    assert result.questions[1].text == "Следующий вопрос:"


def test_plain_text_parses_the_same_without_cells():
    """Passing no geometry must parse exactly as before it existed."""
    assert parse_ent_pdf_questions(TABLE_TEXT).questions


# ─────────────────────────────────────────────────────────────────────────
# Out-of-order option labels (§1.3: the set matters, the order does not)
# ─────────────────────────────────────────────────────────────────────────


def test_backwards_label_fills_a_hole():
    options = split_out_of_order_option("B) Cu(NH₃)₄", ["A", "C", "D"])
    assert [(o.label, o.text) for o in options] == [("B", "Cu(NH₃)₄")]


def test_backwards_label_that_repeats_is_refused():
    assert split_out_of_order_option("A) Снова", ["A", "B", "C"]) == []


def test_forward_label_is_not_this_function_s_business():
    assert split_out_of_order_option("E) Дальше", ["A", "B", "C"]) == []


def test_nothing_taken_yet_means_no_hole_to_fill():
    assert split_out_of_order_option("B) Первый", []) == []


SCRAMBLED = """\
38. Сопоставьте:
A) K₃[Fe(CN)₆]
C) H[AuCl₄]
D) H₂[SiF₆]
B) Cu(NH₃)₄
"""


def test_scrambled_run_is_recovered_and_sorted():
    """A, C, D, B is a printing order, not four options and a corruption."""
    question = parse_ent_pdf_questions(SCRAMBLED).questions[0]
    assert [(o.label, o.text) for o in question.options] == [
        ("A", "K₃[Fe(CN)₆]"),
        ("B", "Cu(NH₃)₄"),
        ("C", "H[AuCl₄]"),
        ("D", "H₂[SiF₆]"),
    ]
    assert "duplicate_option_label" not in question.flags


# ─────────────────────────────────────────────────────────────────────────
# Runs that do not start at A
# ─────────────────────────────────────────────────────────────────────────


def _block(*text_lines):
    block = QuestionBlock()
    block.text_lines = list(text_lines)
    return block


def test_run_starting_at_e_is_recovered():
    block = _block("E) 110", "F) 78", "G) 94", "H) 196")
    recover_unstarted_options(block)
    assert [(o.label, o.text) for o in block.options] == [
        ("E", "110"),
        ("F", "78"),
        ("G", "94"),
        ("H", "196"),
    ]
    assert block.text_lines == []


def test_the_one_option_that_survived_editing():
    block = _block("Количество ароматических углеводородов:", "C) 3")
    recover_unstarted_options(block)
    assert [(o.label, o.text) for o in block.options] == [("C", "3")]
    assert block.text_lines == ["Количество ароматических углеводородов:"]


def test_recovery_never_touches_a_block_that_parsed():
    from app.core.ent_pdf_import import ParsedOption

    block = _block("C) 3")
    block.options = [ParsedOption(label="A", text="Уже есть")]
    recover_unstarted_options(block)
    assert [o.text for o in block.options] == ["Уже есть"]


def test_a_paragraph_is_not_an_option():
    block = _block("В. " + "слово " * 40)
    recover_unstarted_options(block)
    assert block.options == []


def test_repeated_label_is_not_a_run():
    block = _block("C) 3", "C) 4")
    recover_unstarted_options(block)
    assert block.options == []


SINGLE_OPTION = """\
7. Количество ароматических углеводородов среди данных веществ:
CH₄, C₂H₂, C₆H₆, C₇H₈
C) 3
"""


def test_single_surviving_option_is_flagged_and_prefilled():
    """§4.5: the surviving option is almost certainly the right one, so it
    is filled in -- but never silently."""
    question = parse_ent_pdf_questions(SINGLE_OPTION).questions[0]
    assert "single_option_only" in question.flags
    assert question.answer_variants == ["C"]
    assert question.needs_review is True
    assert question.confidence <= 0.5


# ─────────────────────────────────────────────────────────────────────────
# A matching question no longer swallows the rest of its variant
# ─────────────────────────────────────────────────────────────────────────

LOST_MARKER = """\
36. Сопоставьте определения:
Определение первое
A) Электрохимия
B) Гальванотехника
Определение второе
A) Аквакомплексы
B) Ацидокомплексы
38. Следующий вопрос:
A) Первый
B) Второй
"""


def test_a_marker_that_skipped_a_number_still_closes_the_block():
    """Question 37 lost its marker in typesetting. Refusing to let "38."
    close the block costs every question to the end of the variant."""
    result = parse_ent_pdf_questions(LOST_MARKER, None, frozenset({1, 4}))
    assert len(result.questions) == 2
    assert result.questions[1].text == "Следующий вопрос:"
    assert "question_number_gap" in result.questions[1].flags


NUMBERED_PROMPTS = """\
39. Сопоставьте способы получения спиртов:
1. Гидролиз
2. Синтез
A) C₆H₁₂O₆
B) H₂C=CH₂
40. Сопоставьте:
A) 2
B) 8
"""


def test_a_prompt_list_in_cells_does_not_veto_the_next_question():
    """The prompts are numbered 1. and 2., which used to arm the guard that
    then refuses the legitimate "40." -- losing the variant's last question."""
    result = parse_ent_pdf_questions(NUMBERED_PROMPTS, None, frozenset({1, 2}))
    assert len(result.questions) == 2
    assert result.questions[0].match_left_items == ["1. Гидролиз", "2. Синтез"]


def test_a_numbered_prompt_list_still_cannot_split_its_question():
    """The original bug this parser exists for, with no geometry to help."""
    text = (
        "1. Сопоставьте заболевание и возбудителя:\n"
        "1. Дизентерия\n2. Малярия\n3. Холера\n"
        "A) Плазмодий\nB) Шигелла\nC) Вибрион\n"
    )
    assert len(parse_ent_pdf_questions(text).questions) == 1


# ─────────────────────────────────────────────────────────────────────────
# Running page headers, and the diagnostics a teacher acts on
# ─────────────────────────────────────────────────────────────────────────

RUNNING_HEADER = """\
Вариант №1
1. Первый вопрос?
A) Да
B) Нет
Вариант №1
2. Второй вопрос?
A) Да
B) Нет
"""


SPACED_HEADER = RUNNING_HEADER.replace("Вариант №1\n2.", "Вариант № 1\n2.")


def test_a_reprinted_header_matches_through_its_spacing():
    """The file types "Вариант №13" and "Вариант № 13" for the same block."""
    result = parse_ent_pdf_questions(SPACED_HEADER)
    assert result.stats.duplicate_variant_headers == 1
    assert result.stats.variants_detected == 1


def test_a_repeated_header_does_not_cut_its_own_variant():
    """"Вариант №1" printed again at the top of the next page is a running
    header, not a second variant one question long."""
    result = parse_ent_pdf_questions(RUNNING_HEADER)
    assert result.stats.variants_detected == 1
    assert result.stats.duplicate_variant_headers == 1
    assert len(result.questions) == 2


BILINGUAL = """\
Вариант №1
1. Первый вопрос?
A) Да
B) Нет
1 нұсқа
1. Бірінші сұрақ?
A) Иә
B) Жоқ
"""


def test_two_languages_sharing_a_number_stay_two_variants():
    """The dedup keys on the variant that is *open*, not on every number
    seen, so a bilingual paper is not folded in half."""
    result = parse_ent_pdf_questions(BILINGUAL)
    assert result.stats.variants_detected == 2
    assert result.stats.duplicate_variant_headers == 0
    assert [q.variant_label for q in result.questions] == ["Вариант №1", "1 нұсқа"]


def test_question_number_survives_to_the_payload():
    """A pasted key is matched on the printed number, so it has to travel."""
    from app.core.ent_pdf_import import to_import_payload

    result = parse_ent_pdf_questions(RUNNING_HEADER)
    assert [q.question_number for q in result.questions] == [1, 2]
    assert to_import_payload(result.questions[0]).question_number == 1


def test_flags_are_counted_for_the_teacher():
    """2374 missing keys is an evening of pasting; 2374 missing option
    lists is a broken import. The count is what tells them apart."""
    result = parse_ent_pdf_questions(RUNNING_HEADER)
    assert result.stats.by_flag["missing_key"] == 2


def test_flags_and_left_items_reach_the_payload():
    from app.core.ent_pdf_import import to_import_payload

    result = parse_ent_pdf_questions(TABLE_TEXT, None, TABLE_CELLS)
    payload = to_import_payload(result.questions[0])
    assert payload.flags == result.questions[0].flags
    assert len(payload.match_left_items) == 2
