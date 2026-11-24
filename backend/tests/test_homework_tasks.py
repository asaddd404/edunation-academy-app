"""Unit tests for app.core.homework_tasks: no database, just the rules."""

import random

import pytest

from app.core.homework_tasks import (
    TaskDataError,
    clean_answer,
    grade,
    is_answered,
    make_layout,
    normalize_task,
    normalize_text,
    parse_gap_template,
    student_view,
    text_matches,
)

# ── text comparison ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "given, accepted",
    [
        ("Туркестан", "туркестан"),
        ("  туркестан. ", "Туркестан"),
        ("«Туркестан»", "Туркестан"),
        ("ёлка", "елка"),
        ("Семипалатинская   область", "Семипалатинская область"),
        ("1,5", "1.5"),
        ("1.50", "1.5"),
        ("−3", "-3"),
        ("Қара сөздер", "қара сөздер"),
    ],
)
def test_equivalent_spellings_match(given, accepted):
    assert text_matches(given, [accepted])


@pytest.mark.parametrize(
    "given, accepted",
    [("", "x"), ("   ", "x"), ("2x", "8x"), ("15", "1.5"), ("Алматы", "Астана"), (None, "x"), (5, "5")],
)
def test_different_answers_do_not_match(given, accepted):
    assert not text_matches(given, [accepted])


def test_case_sensitive_only_when_asked():
    assert text_matches("NaCl", ["nacl"])
    assert not text_matches("nacl", ["NaCl"], case_sensitive=True)


def test_typo_tolerance_is_opt_in_and_skips_short_words_and_numbers():
    assert not text_matches("Туркистан", ["Туркестан"])
    assert text_matches("Туркистан", ["Туркестан"], allow_typo=True)  # substitution
    assert text_matches("Туркестна", ["Туркестан"], allow_typo=True)  # swap
    assert text_matches("Туркеста", ["Туркестан"], allow_typo=True)  # deletion
    assert not text_matches("Тркстан", ["Туркестан"], allow_typo=True)  # two edits
    assert not text_matches("кит", ["кот"], allow_typo=True)  # short word
    assert not text_matches("1846", ["1845"], allow_typo=True)  # numbers are exact


def test_normalize_text_handles_non_strings():
    assert normalize_text(None) == ""
    assert normalize_text(["x"]) == ""


# ── gap template ────────────────────────────────────────────────────────────


def test_gap_template_splits_text_and_variants():
    segs = parse_gap_template("Абай родился в [1845] году, в [Семипалатинской|Семей] области.")
    assert segs == [
        {"t": "Абай родился в "},
        {"gap": 0, "answers": ["1845"]},
        {"t": " году, в "},
        {"gap": 1, "answers": ["Семипалатинской", "Семей"]},
        {"t": " области."},
    ]


def test_escaped_brackets_are_literal():
    segs = parse_gap_template(r"Отрезок \[0; 1\] и ответ [x]")
    assert segs[0] == {"t": "Отрезок [0; 1] и ответ "}
    assert segs[1]["answers"] == ["x"]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("нет пропусков", "хотя бы один"),
        ("открыта [скобка", "не закрыта"),
        ("лишняя ] скобка", "лишняя"),
        ("пусто []", "пустой"),
        ("пусто [ ]", "пустой"),
        ("вариант [a||b]", "пустой вариант"),
        ("вложенный [a [b]]", "внутри"),
    ],
)
def test_bad_templates_explain_the_problem(text, fragment):
    with pytest.raises(TaskDataError) as e:
        parse_gap_template(text)
    assert fragment in str(e.value)


# ── validation ──────────────────────────────────────────────────────────────


def test_single_needs_exactly_one_correct():
    with pytest.raises(TaskDataError):
        normalize_task("single", "Q", {"options": [{"text": "a"}, {"text": "b"}]}, 1)
    with pytest.raises(TaskDataError):
        normalize_task("single", "Q", {"options": [{"text": "a", "correct": True}, {"text": "b", "correct": True}]}, 1)
    _, data, _ = normalize_task("single", "Q", {"options": [{"text": "a", "correct": True}, {"text": "b"}]}, 1)
    assert [o["correct"] for o in data["options"]] == [True, False]
    assert all(o["id"] for o in data["options"])


def test_ids_survive_an_edit_and_duplicates_are_replaced():
    _, data, _ = normalize_task(
        "single", "Q", {"options": [{"id": "keep1", "text": "a", "correct": True}, {"id": "keep1", "text": "b"}]}, 1
    )
    assert data["options"][0]["id"] == "keep1"
    assert data["options"][1]["id"] != "keep1"


def test_match_gives_each_side_its_own_id_and_rejects_duplicate_rights():
    _, data, _ = normalize_task("match", "Q", {"pairs": [{"left": "1465", "right": "ханство"}, {"left": "1991", "right": "независимость"}]}, 2)
    for p in data["pairs"]:
        assert p["id"] != p["rid"]
    with pytest.raises(TaskDataError):
        normalize_task("match", "Q", {"pairs": [{"left": "a", "right": "x"}, {"left": "b", "right": " X "}]}, 2)


def test_essay_points_are_the_sum_of_criteria():
    _, data, points = normalize_task(
        "essay", "Почему?", {"min_words": 50, "criteria": [{"text": "Объяснение", "points": 4}, {"text": "Пример", "points": 3}]}, 1
    )
    assert points == 7
    assert data["min_words"] == 50


@pytest.mark.parametrize(
    "ttype, prompt, data",
    [
        ("short", "Q", {"answers": ["  "]}),
        ("tf", "Q", {}),
        ("order", "Q", {"items": [{"text": "один"}]}),
        ("multi", "Q", {"options": [{"text": "a"}, {"text": "b"}]}),
        ("single", "", {"options": [{"text": "a", "correct": True}, {"text": "b"}]}),
        ("gaps", "", {"text": "без пропусков"}),
        ("bogus", "Q", {}),
    ],
)
def test_invalid_tasks_are_refused(ttype, prompt, data):
    with pytest.raises(TaskDataError):
        normalize_task(ttype, prompt, data, 1)


@pytest.mark.parametrize("points", [0, 101, "abc", True])
def test_points_must_be_in_range(points):
    with pytest.raises(TaskDataError):
        normalize_task("tf", "Q", {"correct": True}, points)


# ── student view never leaks the key ────────────────────────────────────────


def _all_views():
    rng = random.Random(1)
    tasks = {
        "gaps": normalize_task("gaps", "", {"text": "Абай родился в [1845] году"}, 1),
        "single": normalize_task("single", "Q", {"options": [{"text": "верный", "correct": True}, {"text": "нет"}]}, 1),
        "multi": normalize_task("multi", "Q", {"options": [{"text": "a", "correct": True}, {"text": "b"}]}, 1),
        "short": normalize_task("short", "Q", {"answers": ["секрет"]}, 1),
        "match": normalize_task("match", "Q", {"pairs": [{"left": "1", "right": "один"}, {"left": "2", "right": "два"}]}, 1),
        "tf": normalize_task("tf", "Q", {"correct": False}, 1),
        "order": normalize_task("order", "Q", {"items": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}, 1),
    }
    out = {}
    for ttype, (prompt, data, points) in tasks.items():
        out[ttype] = (data, student_view(1, ttype, prompt, data, points, make_layout(ttype, data, rng)))
    return out


def test_student_view_has_no_answer_key():
    for ttype, (data, view) in _all_views().items():
        flat = repr(view)
        assert "correct" not in flat, ttype
        assert "answers" not in flat, ttype
        assert "1845" not in flat
        assert "секрет" not in flat
    _, gaps_view = _all_views()["gaps"]
    assert gaps_view["segments"] == [{"t": "Абай родился в "}, {"gap": 0}, {"t": " году"}]


def test_match_view_shows_rights_under_their_own_ids():
    data, view = _all_views()["match"]
    left_ids = {l["id"] for l in view["lefts"]}
    right_ids = {r["id"] for r in view["rights"]}
    assert left_ids.isdisjoint(right_ids)
    # Answering every left with its own id -- the old exploit -- scores nothing.
    assert grade("match", data, 2, {"pairs": {i: i for i in left_ids}}).earned == 0


def test_order_layout_is_never_already_solved():
    _, data, _ = normalize_task("order", "Q", {"items": [{"text": "a"}, {"text": "b"}]}, 1)
    for seed in range(30):
        assert make_layout("order", data, random.Random(seed))["items"] != [it["id"] for it in data["items"]]


# ── grading ─────────────────────────────────────────────────────────────────


def test_gaps_give_partial_credit_per_gap():
    _, data, _ = normalize_task("gaps", "", {"text": "[a] [b] [c] [d]"}, 4)
    g = grade("gaps", data, 4, {"gaps": ["a", "B", "x"]})
    assert g.earned == 2.0
    assert [i["correct"] for i in g.items] == [True, True, False, False]
    assert not g.full


def test_multi_partial_subtracts_wrong_picks_and_never_goes_negative():
    _, data, _ = normalize_task(
        "multi", "Q", {"options": [{"id": "a", "text": "a", "correct": True}, {"id": "b", "text": "b", "correct": True}, {"id": "c", "text": "c"}]}, 2
    )
    assert grade("multi", data, 2, {"options": ["a", "b"]}).earned == 2.0
    assert grade("multi", data, 2, {"options": ["a"]}).earned == 1.0
    assert grade("multi", data, 2, {"options": ["a", "c"]}).earned == 0.0
    assert grade("multi", data, 2, {"options": ["c"]}).earned == 0.0
    # Ticking everything is not a strategy.
    assert grade("multi", data, 2, {"options": ["a", "b", "c"]}).earned == 1.0


def test_multi_without_partial_is_all_or_nothing():
    _, data, _ = normalize_task(
        "multi", "Q", {"partial": False, "options": [{"id": "a", "text": "a", "correct": True}, {"id": "b", "text": "b", "correct": True}, {"id": "c", "text": "c"}]}, 2
    )
    assert grade("multi", data, 2, {"options": ["a"]}).earned == 0.0
    assert grade("multi", data, 2, {"options": ["b", "a"]}).earned == 2.0


def test_single_short_tf_order():
    _, s, _ = normalize_task("single", "Q", {"options": [{"id": "y", "text": "y", "correct": True}, {"id": "n", "text": "n"}]}, 1)
    assert grade("single", s, 1, {"option": "y"}).full
    assert grade("single", s, 1, {"option": "zzz"}).earned == 0

    _, sh, _ = normalize_task("short", "Q", {"answers": ["8", "восемь"]}, 1)
    assert grade("short", sh, 1, {"text": "Восемь"}).full
    assert grade("short", sh, 1, {"text": "8,0"}).full

    _, tf, _ = normalize_task("tf", "Q", {"correct": False}, 1)
    assert grade("tf", tf, 1, {"value": False}).full
    assert grade("tf", tf, 1, {"value": "false"}).earned == 0

    _, od, _ = normalize_task("order", "Q", {"items": [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}, {"id": "3", "text": "c"}, {"id": "4", "text": "d"}]}, 4)
    assert grade("order", od, 4, {"order": ["1", "2", "3", "4"]}).full
    assert grade("order", od, 4, {"order": ["1", "2", "4", "3"]}).earned == 2.0


def test_manual_tasks_wait_for_the_teacher():
    _, e, p = normalize_task("essay", "Q", {"min_words": 3}, 10)
    g = grade("essay", e, p, {"text": "раз два три четыре"})
    assert g.earned is None and g.max == 10
    assert g.items[0]["words"] == 4
    assert grade("file", {}, 5, {}).earned is None


@pytest.mark.parametrize("answer", [None, "x", [], {"gaps": "x"}, {"option": 5}, {"pairs": ["x"]}])
def test_malformed_answers_score_zero_not_crash(answer):
    for ttype, (data, _) in _all_views().items():
        assert grade(ttype, data, 1, answer).earned == 0, ttype


def test_clean_answer_drops_foreign_fields_and_never_trusts_file_paths():
    assert clean_answer("short", {"text": "8", "evil": "x" * 10_000}) == {"text": "8"}
    assert clean_answer("file", {"file_path": "../../etc/passwd"}) == {}
    assert clean_answer("tf", {"value": "true"}) == {}
    assert len(clean_answer("essay", {"text": "я" * 50_000})["text"]) == 20_000


def test_is_answered():
    assert not is_answered("gaps", {"gaps": ["", "  "]})
    assert is_answered("gaps", {"gaps": ["", "x"]})
    assert is_answered("tf", {"value": False})
    assert not is_answered("short", {})
