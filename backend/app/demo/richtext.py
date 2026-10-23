"""Lesson notes written compactly, stored as the editor's own document format.

The course builder saves TipTap documents; writing the demo notes as raw JSON
would be unreadable, so they are written with three inline conventions and
converted here:

    **bold**                 -> bold mark
    [Термин|Пояснение]       -> glossary term (hover tooltip for the student)
    $x^2$                    -> left in the text; RichTextSpan renders it as KaTeX
"""

import json
import re

_INLINE = re.compile(r"\*\*(.+?)\*\*|\[([^\[\]|]+)\|([^\[\]]+)\]")


def _inline(text: str) -> list[dict]:
    nodes: list[dict] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            nodes.append({"type": "text", "text": text[pos:m.start()]})
        if m.group(1) is not None:
            nodes.append({"type": "text", "text": m.group(1), "marks": [{"type": "bold"}]})
        else:
            nodes.append(
                {"type": "text", "text": m.group(2), "marks": [{"type": "glossaryTerm", "attrs": {"explanation": m.group(3)}}]}
            )
        pos = m.end()
    if pos < len(text):
        nodes.append({"type": "text", "text": text[pos:]})
    return nodes


def h(text: str) -> dict:
    return {"type": "heading", "attrs": {"level": 3}, "content": _inline(text)}


def p(text: str) -> dict:
    return {"type": "paragraph", "content": _inline(text)}


def _list(kind: str, items: tuple[str, ...]) -> dict:
    return {"type": kind, "content": [{"type": "listItem", "content": [p(i)]} for i in items]}


def ul(*items: str) -> dict:
    return _list("bulletList", items)


def ol(*items: str) -> dict:
    return _list("orderedList", items)


def note(text: str, variant: str = "info") -> dict:
    """A callout box: info (brand), success, warning or danger."""
    return {"type": "callout", "attrs": {"variant": variant}, "content": [p(text)]}


def formula(latex: str) -> dict:
    return {"type": "blockMath", "attrs": {"latex": latex}}


def doc(*blocks: dict) -> str:
    return json.dumps({"type": "doc", "content": list(blocks)}, ensure_ascii=False)
