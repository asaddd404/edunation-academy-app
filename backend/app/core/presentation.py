"""Lesson presentations, shown through Microsoft's Office viewer.

The viewer (view.officeapps.live.com) renders a PowerPoint file with its
layout, fonts and animations inside an iframe. It downloads the file itself,
from a public URL, so a lesson's file is served under a short-lived signed
link (`/api/v1/presentations/{ticket}/{name}.pptx`) instead of the student's
session. Whoever holds the link before it expires can download the file --
as can anyone using the viewer's own download menu; that is the trade-off of
using the viewer at all.
"""

from urllib.parse import quote

from app.config import settings
from app.security import create_presentation_ticket

OFFICE_EMBED_URL = "https://view.officeapps.live.com/op/embed.aspx?src="


def presentation_file_url(lesson_id: int, presentation_path: str) -> str:
    ticket = create_presentation_ticket(lesson_id, presentation_path)
    # The last segment is cosmetic: the viewer shows it as the file's name.
    return f"{settings.public_base_url}/api/v1/presentations/{ticket}/lesson-{lesson_id}.pptx"


def presentation_embed_url(lesson_id: int, presentation_path: str) -> str:
    return OFFICE_EMBED_URL + quote(presentation_file_url(lesson_id, presentation_path), safe="")
