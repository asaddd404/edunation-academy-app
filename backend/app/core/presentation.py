"""Lesson presentations.

PowerPoint (.pptx, .ppsx) is shown through Microsoft's Office viewer
(view.officeapps.live.com), which renders it with its layout, fonts and
animations inside an iframe. The viewer downloads the file itself, from a
public URL, so a lesson's file is served under a short-lived signed link
(`/api/v1/presentations/{ticket}/lesson-N.<ext>`) instead of the student's
session. Whoever holds the link before it expires can download the file -- as
can anyone using the viewer's own download menu; that is the trade-off of
using the viewer at all.

A PDF is not sent to Microsoft: the lesson page fetches it from the same kind
of link and shows it in the browser's own PDF viewer.
"""

from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote

from app.config import settings
from app.security import create_presentation_ticket

OFFICE_EMBED_URL = "https://view.officeapps.live.com/op/embed.aspx?src="

PresentationKind = Literal["office", "pdf"]


def presentation_kind(presentation_path: str) -> PresentationKind:
    return "pdf" if PurePosixPath(presentation_path).suffix.lower() == ".pdf" else "office"


def presentation_file_path(lesson_id: int, presentation_path: str) -> str:
    """API-relative path of the file under a fresh ticket. The last segment is
    cosmetic -- the Office viewer shows it as the file's name -- but keeps the
    real extension."""
    ticket = create_presentation_ticket(lesson_id, presentation_path)
    extension = PurePosixPath(presentation_path).suffix.lower()
    return f"/presentations/{ticket}/lesson-{lesson_id}{extension}"


def presentation_link(lesson_id: int, presentation_path: str) -> dict:
    """What the lesson page needs to show the presentation: for PowerPoint the
    Office viewer URL to frame, for a PDF the file path to fetch."""
    file_path = presentation_file_path(lesson_id, presentation_path)
    kind = presentation_kind(presentation_path)
    if kind == "pdf":
        return {"kind": kind, "embed_url": None, "file_path": file_path}
    absolute = f"{settings.public_base_url}/api/v1{file_path}"
    return {"kind": kind, "embed_url": OFFICE_EMBED_URL + quote(absolute, safe=""), "file_path": None}
