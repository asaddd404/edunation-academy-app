"""Auto-checked homework: task types, validation, the student's view and grading.

Pure functions only -- no database, no request -- so every rule here is unit
tested directly (tests/test_homework_tasks.py) and the API layer just stores
and moves data around.

Nine task types. Seven are graded on submit; `essay` and `file` are graded
by the teacher (``AUTO_TYPES`` vs ``MANUAL_TYPES``).

Shapes, teacher side (``data``)::

    gaps    {"text": "Абай родился в [1845] году", "allow_typo": bool, "case_sensitive": bool}
    single  {"options": [{"id", "text", "correct"}], "shuffle": bool}
    multi   {"options": [{"id", "text", "correct"}], "partial": bool, "shuffle": bool}
    short   {"answers": ["8", "восемь"], "allow_typo": bool, "case_sensitive": bool}
    match   {"pairs": [{"id", "rid", "left", "right"}]}
    tf      {"correct": bool}
    order   {"items": [{"id", "text"}]}                       # in the correct order
    essay   {"min_words": int, "criteria": [{"id", "text", "points"}]}
    file    {}

Answers, student side::

    gaps    {"gaps": ["1845", ...]}          # by gap index
    single  {"option": "<id>"}
    multi   {"options": ["<id>", ...]}
    short   {"text": "8"}
    match   {"pairs": {"<left id>": "<right rid>"}}
    tf      {"value": true}
    order   {"order": ["<id>", ...]}
    essay   {"text": "..."}
    file    {"file_path": ..., "file_name": ...}   # set by the upload endpoint only

A matching pair carries two ids on purpose: the student sees the right-hand
side under ``rid``, never under the pair's own ``id``. With one shared id the
answer ``{x: x}`` would score full marks without reading the question -- the
exploit this codebase already closed once for mini-tests (see match_tokens).

Anything malformed in an answer counts as unanswered (0 points), never as an
error: one bad field must not fail a whole submission.
"""

from __future__ import annotations

import random
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import Any

TASK_TYPES = ("gaps", "single", "multi", "short", "match", "tf", "order", "essay", "file")
MANUAL_TYPES = frozenset({"essay", "file"})
AUTO_TYPES = frozenset(TASK_TYPES) - MANUAL_TYPES

MAX_PROMPT = 2000
MAX_GAP_TEXT = 5000
MAX_GAPS = 60
MAX_VARIANT = 200
MAX_OPTION = 500
MAX_PAIR_SIDE = 300
MAX_ESSAY_ANSWER = 20000
MAX_POINTS = 100


class TaskDataError(ValueError):
    """A teacher-facing validation message, in Russian, safe to show as is."""


# ── Text comparison ─────────────────────────────────────────────────────────

_FOLD = str.maketrans(
    {
        "ё": "е",
        "Ё": "Е",
        "−": "-",  # minus sign
        "–": "-",
        "—": "-",
        "‐": "-",
        " ": " ",
        "×": "*",
    }
)
_EDGE_PUNCT = " .,;:!?\"'«»“”„"
_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def normalize_text(value: Any, *, case_sensitive: bool = False) -> str:
    """What two answers are compared as: same Unicode form, е for ё, one kind
    of dash, single spaces, no punctuation hanging off the ends, and -- unless
    the teacher asked otherwise -- no letter case."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value).translate(_FOLD)
    text = " ".join(text.split()).strip(_EDGE_PUNCT)
    return text if case_sensitive else text.casefold()


def _as_number(text: str) -> float | None:
    compact = text.replace(" ", "").replace(",", ".")
    if not _NUMBER.match(compact):
        return None
    try:
        return float(compact)
    except ValueError:  # pragma: no cover -- the regex already guarantees a float
        return None


def _one_edit_apart(a: str, b: str) -> bool:
    """True when a and b differ by at most one insertion, deletion,
    substitution or swap of two neighbouring letters."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if la > lb:
        a, b = b, a
    # b is one longer: skipping one of its characters must give a.
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1 :]


def text_matches(given: Any, accepted: list[str], *, case_sensitive: bool = False, allow_typo: bool = False) -> bool:
    g = normalize_text(given, case_sensitive=case_sensitive)
    if not g:
        return False
    g_num = _as_number(g)
    for candidate in accepted:
        n = normalize_text(candidate, case_sensitive=case_sensitive)
        if not n:
            continue
        if g == n:
            return True
        n_num = _as_number(n)
        if g_num is not None and n_num is not None:
            if abs(g_num - n_num) < 1e-9:
                return True
            continue  # numbers are never "typos" of each other
        # A typo allowance on a short word turns "кот" into "кит": only words
        # of four letters and more get one.
        if allow_typo and n_num is None and len(n) >= 4 and _one_edit_apart(g, n):
            return True
    return False


# ── Fill-the-gaps template ──────────────────────────────────────────────────


def parse_gap_template(text: str) -> list[dict]:
    """Splits ``"Абай родился в [1845|1845 г.] году"`` into text and gap
    segments: ``[{"t": "Абай родился в "}, {"gap": 0, "answers": ["1845",
    "1845 г."]}, {"t": " году"}]``. ``\\[`` and ``\\]`` are literal brackets."""
    segments: list[dict] = []
    buf: list[str] = []
    gaps = 0
    i, n = 0, len(text)

    def flush() -> None:
        if buf:
            segments.append({"t": "".join(buf)})
            buf.clear()

    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in "[]":
            buf.append(text[i + 1])
            i += 2
            continue
        if c == "]":
            raise TaskDataError("Есть лишняя «]» без пары «[». Проверьте скобки в тексте.")
        if c == "[":
            j = i + 1
            while j < n and text[j] not in "[]":
                j += 1
            if j >= n:
                raise TaskDataError("Скобка «[» не закрыта. У каждого пропуска должна быть пара «[ ]».")
            if text[j] == "[":
                raise TaskDataError("Пропуск внутри пропуска не поддерживается. Проверьте скобки в тексте.")
            variants = [v.strip() for v in text[i + 1 : j].split("|")]
            if not any(variants):
                raise TaskDataError(f"Пропуск {gaps + 1} пустой: впишите правильный ответ внутрь скобок.")
            if not all(variants):
                raise TaskDataError(f"В пропуске {gaps + 1} есть пустой вариант ответа (лишняя «|»).")
            if any(len(v) > MAX_VARIANT for v in variants):
                raise TaskDataError(f"Ответ в пропуске {gaps + 1} слишком длинный (больше {MAX_VARIANT} символов).")
            flush()
            segments.append({"gap": gaps, "answers": variants})
            gaps += 1
            if gaps > MAX_GAPS:
                raise TaskDataError(f"Слишком много пропусков: не больше {MAX_GAPS} в одном задании.")
            i = j + 1
            continue
        buf.append(c)
        i += 1
    flush()
    if gaps == 0:
        raise TaskDataError("Отметьте хотя бы один пропуск: нажмите на слово или возьмите его в квадратные скобки.")
    return segments


def _gap_answers(data: dict) -> list[list[str]]:
    return [s["answers"] for s in parse_gap_template(data["text"]) if "gap" in s]


# ── Validation of what the teacher saves ────────────────────────────────────

_ID = re.compile(r"^[A-Za-z0-9_-]{1,24}$")


def _new_id(taken: set[str]) -> str:
    while True:
        candidate = secrets.token_hex(4)
        if candidate not in taken:
            taken.add(candidate)
            return candidate


def _keep_or_new_id(value: Any, taken: set[str]) -> str:
    if isinstance(value, str) and _ID.match(value) and value not in taken:
        taken.add(value)
        return value
    return _new_id(taken)


def _text(value: Any, label: str, limit: int, *, required: bool = True) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if required and not text:
        raise TaskDataError(f"Заполните поле «{label}».")
    if len(text) > limit:
        raise TaskDataError(f"«{label}»: слишком длинно (больше {limit} символов).")
    return text


def _flag(data: dict, key: str, default: bool) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def _list(data: dict, key: str) -> list:
    value = data.get(key)
    return value if isinstance(value, list) else []


def _int(value: Any, label: str, lo: int, hi: int) -> int:
    if isinstance(value, bool):  # int(True) == 1 would slip through below
        raise TaskDataError(f"«{label}»: нужно целое число.")
    if not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise TaskDataError(f"«{label}»: нужно целое число.") from None
    if not lo <= value <= hi:
        raise TaskDataError(f"«{label}»: число от {lo} до {hi}.")
    return value


def _options(raw: list, *, min_n: int, max_n: int) -> list[dict]:
    if not min_n <= len(raw) <= max_n:
        raise TaskDataError(f"Нужно от {min_n} до {max_n} вариантов ответа.")
    taken: set[str] = set()
    out = []
    for k, item in enumerate(raw):
        item = item if isinstance(item, dict) else {}
        out.append(
            {
                "id": _keep_or_new_id(item.get("id"), taken),
                "text": _text(item.get("text"), f"Вариант {k + 1}", MAX_OPTION),
                "correct": item.get("correct") is True,
            }
        )
    return out


def normalize_task(ttype: str, prompt: Any, data: Any, points: Any) -> tuple[str, dict, int]:
    """Validates and cleans a task as the teacher saves it. Returns
    ``(prompt, data, points)``; raises TaskDataError with a message fit for
    the teacher. Ids already on options/pairs/items are kept, so editing a
    typo in a live task doesn't orphan the answers students already gave."""
    if ttype not in TASK_TYPES:
        raise TaskDataError("Неизвестный тип задания.")
    data = data if isinstance(data, dict) else {}
    points = _int(points if points is not None else 1, "Баллы", 1, MAX_POINTS)

    if ttype == "gaps":
        prompt = _text(prompt, "Инструкция", MAX_PROMPT, required=False)
        text = _text(data.get("text"), "Текст с пропусками", MAX_GAP_TEXT)
        parse_gap_template(text)  # raises on bad brackets
        clean = {"text": text, "allow_typo": _flag(data, "allow_typo", False), "case_sensitive": _flag(data, "case_sensitive", False)}
        return prompt, clean, points

    prompt = _text(prompt, "Вопрос" if ttype != "tf" else "Утверждение", MAX_PROMPT)

    if ttype in ("single", "multi"):
        options = _options(_list(data, "options"), min_n=2, max_n=10 if ttype == "single" else 12)
        correct = sum(o["correct"] for o in options)
        if ttype == "single" and correct != 1:
            raise TaskDataError("Отметьте ровно один правильный вариант.")
        if ttype == "multi" and correct == 0:
            raise TaskDataError("Отметьте хотя бы один правильный вариант.")
        clean = {"options": options, "shuffle": _flag(data, "shuffle", True)}
        if ttype == "multi":
            clean["partial"] = _flag(data, "partial", True)
        return prompt, clean, points

    if ttype == "short":
        answers = [_text(a, "Правильный ответ", MAX_VARIANT, required=False) for a in _list(data, "answers")]
        answers = [a for a in answers if a]
        if not answers:
            raise TaskDataError("Впишите правильный ответ.")
        if len(answers) > 10:
            raise TaskDataError("Не больше 10 вариантов правильного ответа.")
        clean = {"answers": answers, "allow_typo": _flag(data, "allow_typo", False), "case_sensitive": _flag(data, "case_sensitive", False)}
        return prompt, clean, points

    if ttype == "match":
        raw = _list(data, "pairs")
        if not 2 <= len(raw) <= 12:
            raise TaskDataError("Нужно от 2 до 12 пар.")
        taken: set[str] = set()
        pairs = []
        for k, item in enumerate(raw):
            item = item if isinstance(item, dict) else {}
            pairs.append(
                {
                    "id": _keep_or_new_id(item.get("id"), taken),
                    "rid": _keep_or_new_id(item.get("rid"), taken),
                    "left": _text(item.get("left"), f"Пара {k + 1}, левая часть", MAX_PAIR_SIDE),
                    "right": _text(item.get("right"), f"Пара {k + 1}, правая часть", MAX_PAIR_SIDE),
                }
            )
        rights = [normalize_text(p["right"]) for p in pairs]
        if len(set(rights)) != len(rights):
            raise TaskDataError("Правые части пар не должны повторяться — иначе ученик не сможет их различить.")
        return prompt, {"pairs": pairs}, points

    if ttype == "tf":
        if not isinstance(data.get("correct"), bool):
            raise TaskDataError("Отметьте, верно утверждение или нет.")
        return prompt, {"correct": data["correct"]}, points

    if ttype == "order":
        raw = _list(data, "items")
        if not 2 <= len(raw) <= 12:
            raise TaskDataError("Нужно от 2 до 12 пунктов.")
        taken = set()
        items = []
        for k, item in enumerate(raw):
            item = item if isinstance(item, dict) else {}
            items.append({"id": _keep_or_new_id(item.get("id"), taken), "text": _text(item.get("text"), f"Пункт {k + 1}", MAX_OPTION)})
        return prompt, {"items": items}, points

    if ttype == "essay":
        min_words = _int(data.get("min_words") or 0, "Минимум слов", 0, 3000)
        raw = _list(data, "criteria")
        if len(raw) > 10:
            raise TaskDataError("Не больше 10 критериев.")
        taken = set()
        criteria = []
        for k, item in enumerate(raw):
            item = item if isinstance(item, dict) else {}
            criteria.append(
                {
                    "id": _keep_or_new_id(item.get("id"), taken),
                    "text": _text(item.get("text"), f"Критерий {k + 1}", 300),
                    "points": _int(item.get("points") or 1, f"Баллы за критерий {k + 1}", 1, MAX_POINTS),
                }
            )
        if criteria:
            points = sum(c["points"] for c in criteria)
        return prompt, {"min_words": min_words, "criteria": criteria}, points

    return prompt, {}, points  # file


# ── What the student sees ───────────────────────────────────────────────────


def make_layout(ttype: str, data: dict, rng: random.Random) -> dict:
    """The per-attempt presentation order, fixed at start so a reload shows
    the same arrangement (and a re-roll can't be farmed by refreshing)."""
    if ttype in ("single", "multi"):
        ids = [o["id"] for o in data["options"]]
        if data.get("shuffle", True):
            rng.shuffle(ids)
        return {"options": ids}
    if ttype == "match":
        rids = [p["rid"] for p in data["pairs"]]
        rng.shuffle(rids)
        return {"rights": rids}
    if ttype == "order":
        ids = [it["id"] for it in data["items"]]
        correct = list(ids)
        for _ in range(8):  # an "already solved" shuffle would be a free point
            rng.shuffle(ids)
            if ids != correct:
                break
        return {"items": ids}
    return {}


def _ordered(items: list[dict], ids: list[str], key: str = "id") -> list[dict]:
    by_id = {it[key]: it for it in items}
    seen = [by_id[i] for i in ids if i in by_id]
    # Anything added after the attempt started goes last rather than vanishing.
    rest = [it for it in items if it[key] not in set(ids)]
    return seen + rest


def student_view(task_id: int, ttype: str, prompt: str, data: dict, points: int, layout: dict) -> dict:
    """The task as sent to the student's browser: everything needed to
    answer, nothing that gives the answer away."""
    view: dict[str, Any] = {"id": task_id, "type": ttype, "prompt": prompt, "points": points}
    if ttype == "gaps":
        segs = parse_gap_template(data["text"])
        view["segments"] = [{"t": s["t"]} if "t" in s else {"gap": s["gap"]} for s in segs]
        view["gap_count"] = sum(1 for s in segs if "gap" in s)
    elif ttype in ("single", "multi"):
        view["options"] = [{"id": o["id"], "text": o["text"]} for o in _ordered(data["options"], layout.get("options", []))]
    elif ttype == "match":
        view["lefts"] = [{"id": p["id"], "text": p["left"]} for p in data["pairs"]]
        view["rights"] = [{"id": p["rid"], "text": p["right"]} for p in _ordered(data["pairs"], layout.get("rights", []), key="rid")]
    elif ttype == "order":
        view["items"] = [{"id": it["id"], "text": it["text"]} for it in _ordered(data["items"], layout.get("items", []))]
    elif ttype == "essay":
        view["min_words"] = data.get("min_words", 0)
        view["criteria"] = [{"text": c["text"], "points": c["points"]} for c in data.get("criteria", [])]
    return view


# ── Grading ─────────────────────────────────────────────────────────────────


@dataclass
class Graded:
    earned: float | None  # None: waits for the teacher
    max: float
    # Per-item verdicts for the review screen, the class's problem spots and
    # the copy signals: [{"key", "label", "correct", "given"}]. `given` is the
    # normalized free-text answer where there is one (else a readable form).
    items: list[dict] = field(default_factory=list)

    @property
    def full(self) -> bool:
        return self.earned is not None and self.earned >= self.max - 1e-9


def word_count(text: Any) -> int:
    return len(re.findall(r"[\w'-]+", text)) if isinstance(text, str) else 0


def grade(ttype: str, data: dict, points: int, answer: Any) -> Graded:
    answer = answer if isinstance(answer, dict) else {}
    pts = float(points)

    if ttype == "gaps":
        keys = _gap_answers(data)
        given = answer.get("gaps") if isinstance(answer.get("gaps"), list) else []
        items, ok = [], 0
        for i, accepted in enumerate(keys):
            g = given[i] if i < len(given) else ""
            hit = text_matches(g, accepted, case_sensitive=data.get("case_sensitive", False), allow_typo=data.get("allow_typo", False))
            ok += hit
            items.append({"key": f"g{i}", "label": f"Пропуск {i + 1}", "correct": hit, "given": normalize_text(g)})
        return Graded(round(pts * ok / len(keys), 2), pts, items)

    if ttype == "single":
        chosen = answer.get("option")
        correct_id = next(o["id"] for o in data["options"] if o["correct"])
        text_of = {o["id"]: o["text"] for o in data["options"]}
        hit = chosen == correct_id
        return Graded(pts if hit else 0.0, pts, [{"key": "o", "label": "Ответ", "correct": hit, "given": text_of.get(chosen, "")}])

    if ttype == "multi":
        raw = answer.get("options") if isinstance(answer.get("options"), list) else []
        valid = {o["id"] for o in data["options"]}
        chosen = {c for c in raw if isinstance(c, str) and c in valid}
        correct = {o["id"] for o in data["options"] if o["correct"]}
        exact = chosen == correct
        if data.get("partial", True):
            frac = max(0.0, (len(chosen & correct) - len(chosen - correct)) / len(correct))
        else:
            frac = 1.0 if exact else 0.0
        text_of = {o["id"]: o["text"] for o in data["options"]}
        given = ", ".join(sorted(text_of[c] for c in chosen))
        return Graded(round(pts * frac, 2), pts, [{"key": "o", "label": "Ответ", "correct": exact, "given": given}])

    if ttype == "short":
        g = answer.get("text", "")
        hit = text_matches(g, data["answers"], case_sensitive=data.get("case_sensitive", False), allow_typo=data.get("allow_typo", False))
        return Graded(pts if hit else 0.0, pts, [{"key": "a", "label": "Ответ", "correct": hit, "given": normalize_text(g)}])

    if ttype == "match":
        raw = answer.get("pairs") if isinstance(answer.get("pairs"), dict) else {}
        right_text = {p["rid"]: p["right"] for p in data["pairs"]}
        items, ok = [], 0
        for p in data["pairs"]:
            chosen = raw.get(p["id"])
            hit = chosen == p["rid"]
            ok += hit
            items.append({"key": f"m{p['id']}", "label": p["left"], "correct": hit, "given": right_text.get(chosen, "") if isinstance(chosen, str) else ""})
        return Graded(round(pts * ok / len(data["pairs"]), 2), pts, items)

    if ttype == "tf":
        value = answer.get("value")
        hit = isinstance(value, bool) and value == data["correct"]
        given = "" if not isinstance(value, bool) else ("Верно" if value else "Неверно")
        return Graded(pts if hit else 0.0, pts, [{"key": "v", "label": "Ответ", "correct": hit, "given": given}])

    if ttype == "order":
        raw = answer.get("order") if isinstance(answer.get("order"), list) else []
        correct = [it["id"] for it in data["items"]]
        ok = sum(1 for i, cid in enumerate(correct) if i < len(raw) and raw[i] == cid)
        exact = ok == len(correct)
        return Graded(round(pts * ok / len(correct), 2), pts, [{"key": "o", "label": "Порядок", "correct": exact, "given": ""}])

    if ttype == "essay":
        return Graded(None, pts, [{"key": "e", "label": "Ответ", "correct": None, "given": "", "words": word_count(answer.get("text"))}])

    return Graded(None, pts, [{"key": "f", "label": "Файл", "correct": None, "given": answer.get("file_name") or ""}])


def is_answered(ttype: str, answer: Any) -> bool:
    if not isinstance(answer, dict):
        return False
    if ttype == "gaps":
        return any(isinstance(g, str) and g.strip() for g in answer.get("gaps") or [])
    if ttype == "single":
        return isinstance(answer.get("option"), str)
    if ttype == "multi":
        return bool(answer.get("options"))
    if ttype in ("short", "essay"):
        return isinstance(answer.get("text"), str) and bool(answer["text"].strip())
    if ttype == "match":
        return bool(answer.get("pairs"))
    if ttype == "tf":
        return isinstance(answer.get("value"), bool)
    if ttype == "order":
        return bool(answer.get("order"))
    return bool(answer.get("file_path"))


def clean_answer(ttype: str, answer: Any) -> dict:
    """Keeps only the fields a task type reads, bounded in size, so a client
    can't park megabytes in an attempt row. File answers are never taken
    from the client: they're set by the upload endpoint."""
    if not isinstance(answer, dict):
        return {}
    if ttype == "gaps":
        gaps = answer.get("gaps") if isinstance(answer.get("gaps"), list) else []
        return {"gaps": [g[:MAX_VARIANT * 2] if isinstance(g, str) else "" for g in gaps[:MAX_GAPS]]}
    if ttype == "single":
        v = answer.get("option")
        return {"option": v} if isinstance(v, str) and len(v) <= 24 else {}
    if ttype == "multi":
        v = answer.get("options") if isinstance(answer.get("options"), list) else []
        return {"options": [x for x in v[:12] if isinstance(x, str) and len(x) <= 24]}
    if ttype == "short":
        v = answer.get("text")
        return {"text": v[:MAX_VARIANT * 2]} if isinstance(v, str) else {}
    if ttype == "match":
        v = answer.get("pairs") if isinstance(answer.get("pairs"), dict) else {}
        return {"pairs": {k: x for k, x in list(v.items())[:12] if isinstance(k, str) and isinstance(x, str) and len(k) <= 24 and len(x) <= 24}}
    if ttype == "tf":
        v = answer.get("value")
        return {"value": v} if isinstance(v, bool) else {}
    if ttype == "order":
        v = answer.get("order") if isinstance(answer.get("order"), list) else []
        return {"order": [x for x in v[:12] if isinstance(x, str) and len(x) <= 24]}
    if ttype == "essay":
        v = answer.get("text")
        return {"text": v[:MAX_ESSAY_ANSWER]} if isinstance(v, str) else {}
    return {}


def correct_view(ttype: str, data: dict) -> dict:
    """The answer key in a readable form, for the review after the deadline."""
    if ttype == "gaps":
        return {"gaps": [answers for answers in _gap_answers(data)]}
    if ttype in ("single", "multi"):
        return {"options": [o["id"] for o in data["options"] if o["correct"]]}
    if ttype == "short":
        return {"answers": data["answers"]}
    if ttype == "match":
        return {"pairs": {p["id"]: p["rid"] for p in data["pairs"]}}
    if ttype == "tf":
        return {"value": data["correct"]}
    if ttype == "order":
        return {"order": [it["id"] for it in data["items"]]}
    return {}
