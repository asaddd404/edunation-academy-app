"""Helpers for the TipTap-JSON rich text stored in `Lesson.description` and
`Lesson.homework_assignment`.

The column stays plain TEXT and holds either a JSON document (new rich
content) or legacy plain text -- the frontend decides how to render by
sniffing it (see frontend/src/utils/richContent.ts). Everything here must
therefore treat "not valid JSON" as a normal case, not an error.
"""

import json
from typing import Any

_IMAGE_PREFIX = "lesson-content/"


def _walk(node: Any, found: set[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, found)
        return
    if not isinstance(node, dict):
        return

    if node.get("type") == "image":
        src = (node.get("attrs") or {}).get("src")
        # Only ever collect our own uploads. An external https:// image the
        # teacher pasted in must never be turned into a filesystem path.
        if isinstance(src, str) and src.startswith(_IMAGE_PREFIX) and "/" not in src[len(_IMAGE_PREFIX) :]:
            found.add(src)

    _walk(node.get("content"), found)


def extract_image_paths(raw: str | None) -> set[str]:
    """Every uploaded-image path referenced by a rich text document.

    Legacy plain text and malformed JSON both yield an empty set: neither can
    reference an upload, so "references nothing" is the honest answer."""
    if not raw:
        return set()
    try:
        document = json.loads(raw)
    except (ValueError, TypeError):
        return set()

    found: set[str] = set()
    _walk(document, found)
    return found


def orphaned_image_paths(old_raw: str | None, new_raw: str | None) -> set[str]:
    """Images the old version of a document referenced and the new one does
    not -- i.e. files that are now safe to delete.

    Note the deliberate asymmetry: an unreadable *old* value yields nothing to
    delete, while an unreadable *new* value orphans everything the old one
    held. The latter is correct rather than reckless -- whatever replaced the
    document cannot render those images either way -- but it does mean a
    client that PATCHes garbage into `description` also drops its images."""
    return extract_image_paths(old_raw) - extract_image_paths(new_raw)
