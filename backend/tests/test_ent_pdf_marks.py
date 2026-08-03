"""Answers marked by colour instead of a written "Ответ:".

These build real PDFs and read them back through the real extractor, so
they cover the geometry and colour handling rather than a mock of it.
"""
import io

import pytest

from app.core.ent_pdf_import import (
    apply_option_marks,
    extract_pdf_text,
    is_marking_colour,
    parse_ent_pdf_questions,
    split_options_in_line,
    to_import_payload,
)

reportlab = pytest.importorskip("reportlab", reason="PDF-building test dependency")

from reportlab.lib.colors import Color, black  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

YELLOW = Color(1, 1, 0)
RED = Color(1, 0, 0)


def build_pdf(draw) -> bytes:
    """Runs `draw(canvas)` on a single page and returns the PDF bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(420, 320))
    c.setFont("Helvetica", 12)
    c.setFillColor(black)
    draw(c)
    c.save()
    return buf.getvalue()


def question_with(draw_mark=None, *, under=None, options=("A) Berlin", "B) Paris", "C) Madrid")) -> bytes:
    """A plain question whose answer is marked only by the given hook.

    `under` runs before the text (a highlighter sits beneath the glyphs),
    `draw_mark` runs after (an ellipse is drawn over them). Text is drawn
    exactly once either way -- drawing it twice makes pdfplumber read
    doubled glyphs ("BB)) PPaarriiss").

    Content is Latin because the built-in PDF fonts have no Cyrillic
    glyphs. Nothing here depends on the language: mark detection is
    geometric, and the question/option markers are the same either way.
    """

    def draw(c):
        if under:
            under(c)
        c.setFillColor(black)
        c.drawString(40, 270, "1. Capital of France?")
        y = 240
        for option in options:
            c.setFillColor(black)
            c.drawString(40, y, option)
            y -= 20
        if draw_mark:
            draw_mark(c)

    return build_pdf(draw)


# ── colour classification ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "colour",
    [(1, 1, 0), (1, 0, 0), (0, 0.6, 0), (0.2, 0.4, 1.0), (0, 1, 1, 0)],
)
def test_colourful_inks_count_as_marks(colour):
    assert is_marking_colour(colour) is True


@pytest.mark.parametrize(
    "colour",
    [
        None,
        (0,),
        (0, 0, 0),
        (1, 1, 1),
        (0.5, 0.5, 0.5),
        (0.1, 0.12, 0.1),
        "not-a-colour",
        (),
    ],
)
def test_greyscale_and_junk_are_not_marks(colour):
    """Body text is black, table rules and shaded headers are grey. Reading
    those as marks would flag every option on the page."""
    assert is_marking_colour(colour) is False


# ── the three ways a digital PDF marks an answer ─────────────────────────


def test_highlighter_annotation_marks_the_answer():
    pytest.importorskip("pypdf")
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Highlight
    from pypdf.generic import ArrayObject, FloatObject

    base = question_with(lambda c: None)
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(base)))
    # Option B sits at y=220..234 in PDF (bottom-left) coordinates.
    quad = ArrayObject([FloatObject(v) for v in (36, 234, 170, 234, 36, 216, 170, 216)])
    writer.add_annotation(
        page_number=0,
        annotation=Highlight(rect=(36, 216, 170, 234), quad_points=quad, highlight_color="ffff00"),
    )
    out = io.BytesIO()
    writer.write(out)

    extracted = extract_pdf_text(out.getvalue())
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert question.answer_variants == ["B"]
    assert question.key_source == "highlight"
    assert [o.marked for o in question.options] == [False, True, False]


def test_filled_rectangle_under_the_answer_marks_it():
    def mark(c):
        c.setFillColor(YELLOW)
        c.rect(36, 216, 134, 17, stroke=0, fill=1)

    extracted = extract_pdf_text(question_with(under=mark))
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert question.answer_variants == ["B"]
    assert question.key_source == "highlight"


def test_coloured_ink_marks_the_answer():
    def draw(c):
        c.drawString(40, 270, "1. Capital of France?")
        c.drawString(40, 240, "A) Berlin")
        c.setFillColor(RED)
        c.drawString(40, 220, "B) Paris")
        c.setFillColor(black)
        c.drawString(40, 200, "C) Madrid")

    extracted = extract_pdf_text(build_pdf(draw))
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert question.answer_variants == ["B"]
    assert question.key_source == "highlight"


def test_ellipse_around_the_answer_marks_it():
    def mark(c):
        c.setStrokeColor(RED)
        c.setLineWidth(1.5)
        c.ellipse(36, 214, 170, 236, stroke=1, fill=0)

    extracted = extract_pdf_text(question_with(mark))
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert question.answer_variants == ["B"]
    assert question.key_source == "highlight"


# ── interaction with the rest of the parser ──────────────────────────────


def test_unmarked_file_is_unchanged():
    """No colour anywhere must behave exactly as before the feature."""
    extracted = extract_pdf_text(question_with(lambda c: None))
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert extracted.marks == {}
    assert question.key_source == "none"
    assert question.needs_review is True
    assert question.confidence == 0.4


def test_written_key_wins_over_a_colour_mark():
    """A file with both must trust the text: the written key is explicit,
    the colour is only an inference.

    Driven through the parser rather than a built PDF because the key
    phrases are Russian and the built-in PDF fonts carry no Cyrillic.
    """
    text = "1. Столица Франции?\nA) Берлин\nB) Париж\nC) Мадрид\nОтвет: C\n"
    question = parse_ent_pdf_questions(text, {2: ("B) Париж",)}).questions[0]

    assert question.answer_variants == ["C"]
    assert question.key_source == "text"
    # The mark is still recorded -- it just does not become the key.
    assert [o.marked for o in question.options] == [False, True, False]


def test_two_marked_options_become_multiple_choice():
    def draw(c):
        c.drawString(40, 270, "1. Which are European capitals?")
        c.setFillColor(RED)
        c.drawString(40, 240, "A) Berlin")
        c.setFillColor(black)
        c.drawString(40, 220, "B) Cairo")
        c.setFillColor(RED)
        c.drawString(40, 200, "C) Madrid")

    extracted = extract_pdf_text(build_pdf(draw))
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert question.answer_variants == ["A", "C"]
    assert question.qtype == "multiple_choice"

    payload = to_import_payload(question)
    assert payload.qtype == "multiple"
    assert payload.choices == [("Berlin", True), ("Cairo", False), ("Madrid", True)]


def test_mark_on_the_question_text_does_not_pick_an_option():
    """Emphasis on a word in the stem is not an answer."""

    def mark(c):
        c.setFillColor(YELLOW)
        c.rect(36, 266, 150, 17, stroke=0, fill=1)

    extracted = extract_pdf_text(question_with(under=mark))
    question = parse_ent_pdf_questions(extracted.text, extracted.marks).questions[0]

    assert question.key_source == "none"
    assert all(not o.marked for o in question.options)


def test_marking_one_of_several_options_on_a_single_line():
    """Bug #2's column layout, with only one column highlighted."""
    options = split_options_in_line("E) Text E F) Text F G) Text G H) Text H")
    apply_option_marks(options, ("G) Text G",))

    assert [o.marked for o in options] == [False, False, True, False]


def test_partial_mark_below_the_threshold_is_ignored():
    options = split_options_in_line("A) a very long option text that continues on")
    apply_option_marks(options, ("a very",))

    assert options[0].marked is False


# ── robustness ───────────────────────────────────────────────────────────


def test_extractor_never_raises_on_a_non_pdf():
    with pytest.raises(Exception):
        # A corrupt file must fail in the extractor, which the endpoint
        # turns into a 400 -- it must not silently return empty text.
        extract_pdf_text(b"this is not a pdf at all")


def test_parse_tolerates_marks_for_lines_that_no_longer_exist():
    """Marks are keyed by pre-cleaning line number; dropped scaffolding
    lines must not shift or crash the mapping."""
    text = "РАЗДЕЛ I\n1. Capital of France?\nA) Berlin\nB) Paris\n"
    result = parse_ent_pdf_questions(text, {3: ("B) Paris",), 99: ("ghost",)})

    assert result.questions[0].answer_variants == ["B"]
