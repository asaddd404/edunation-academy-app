"""Lesson presentations: a teacher attaches a .pptx, a student with access to
the lesson gets a link to Microsoft's Office viewer, and the file behind that
link is served only under a short-lived ticket bound to the stored file."""

import io
import zipfile
from urllib.parse import parse_qs, urlparse

import pytest

from app.core import storage
from app.core.presentation import OFFICE_EMBED_URL
from app.models.lesson import Lesson
from app.security import create_video_ticket
from tests.test_homework_review import _course


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(storage, "PRESENTATION_DIR", tmp_path / "presentations")
    return tmp_path


def _package(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name in names:
            package.writestr(name, "<x/>")
    return buffer.getvalue()


PPTX = _package("[Content_Types].xml", "ppt/presentation.xml", "ppt/slides/slide1.xml")
DOCX = _package("[Content_Types].xml", "word/document.xml")


async def _upload(client, lesson_id, name="Урок 1.pptx", body=PPTX):
    return await client.post(
        f"/api/v1/teacher/lessons/{lesson_id}/presentation", files={"file": (name, body)}
    )


def _file_path_from(embed_url: str) -> str:
    assert embed_url.startswith(OFFICE_EMBED_URL)
    src = parse_qs(urlparse(embed_url).query)["src"][0]
    return urlparse(src).path


async def _student_link(client, lesson_id):
    return await client.post(f"/api/v1/lessons/{lesson_id}/presentation/link")


async def test_teacher_uploads_and_student_views_through_office(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "pres-view")
    login_as(teacher)
    uploaded = await _upload(client, lesson.id)
    assert uploaded.status_code == 200
    assert uploaded.json()["presentation_name"] == "Урок 1.pptx"
    assert uploaded.json()["presentation_size"] == len(PPTX)

    login_as(student)
    detail = (await client.get(f"/api/v1/lessons/{lesson.id}")).json()
    assert detail["presentation_name"] == "Урок 1.pptx"

    link = await _student_link(client, lesson.id)
    assert link.status_code == 200
    file_path = _file_path_from(link.json()["embed_url"])
    assert file_path.endswith(f"/lesson-{lesson.id}.pptx")

    # Fetched with no session at all -- that is how the viewer asks for it.
    login_as(teacher)  # irrelevant to the public route; proves no auth is read
    served = await client.get(file_path)
    assert served.status_code == 200
    assert served.content == PPTX
    assert served.headers["content-type"] == storage.PRESENTATION_MEDIA_TYPES[".pptx"]
    assert served.headers["content-disposition"].startswith("attachment")
    assert served.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(("name", "body"), [("deck.ppt", PPTX), ("deck.pptx", DOCX), ("deck.pptx", b"not a zip")])
async def test_only_real_pptx_files_are_accepted(client, db_session, make_user, login_as, name, body):
    teacher, _, lesson, _ = await _course(db_session, make_user, f"pres-bad-{name}-{len(body)}")
    login_as(teacher)
    assert (await _upload(client, lesson.id, name, body)).status_code == 400


async def test_too_large_file_is_refused(client, db_session, make_user, login_as, monkeypatch):
    monkeypatch.setattr(storage, "MAX_PRESENTATION_SIZE", len(PPTX) - 1)
    teacher, _, lesson, _ = await _course(db_session, make_user, "pres-big")
    login_as(teacher)
    assert (await _upload(client, lesson.id)).status_code == 400


async def test_replacing_removes_old_file_and_kills_old_links(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "pres-replace")
    login_as(teacher)
    await _upload(client, lesson.id, "old.pptx")
    old_stored = (await db_session.get(Lesson, lesson.id, populate_existing=True)).presentation_path
    login_as(student)
    old_link = _file_path_from((await _student_link(client, lesson.id)).json()["embed_url"])

    login_as(teacher)
    assert (await _upload(client, lesson.id, "new.pptx")).status_code == 200

    assert not storage.resolve_upload_path(old_stored).exists()
    assert (await client.get(old_link)).status_code == 404
    login_as(student)
    new_link = _file_path_from((await _student_link(client, lesson.id)).json()["embed_url"])
    assert (await client.get(new_link)).status_code == 200


async def test_removing_the_presentation(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "pres-remove")
    login_as(teacher)
    await _upload(client, lesson.id)
    stored = (await db_session.get(Lesson, lesson.id, populate_existing=True)).presentation_path
    login_as(student)
    link = _file_path_from((await _student_link(client, lesson.id)).json()["embed_url"])

    login_as(teacher)
    removed = await client.delete(f"/api/v1/teacher/lessons/{lesson.id}/presentation")
    assert removed.status_code == 200
    assert removed.json()["presentation_name"] is None
    assert not storage.resolve_upload_path(stored).exists()
    assert (await client.get(link)).status_code == 404

    login_as(student)
    assert (await _student_link(client, lesson.id)).status_code == 404


async def test_a_student_without_access_gets_no_link(client, db_session, make_user, login_as):
    teacher, _, lesson, _ = await _course(db_session, make_user, "pres-noaccess")
    login_as(teacher)
    await _upload(client, lesson.id)

    from app.models.user import RoleEnum

    outsider = await make_user(RoleEnum.student)
    login_as(outsider)
    assert (await _student_link(client, lesson.id)).status_code == 403


async def test_another_teacher_cannot_upload(client, db_session, make_user, login_as):
    _, _, lesson, _ = await _course(db_session, make_user, "pres-other-teacher")
    from app.models.user import RoleEnum

    stranger = await make_user(RoleEnum.teacher)
    login_as(stranger)
    assert (await _upload(client, lesson.id)).status_code in (403, 404)


async def test_forged_or_foreign_tickets_are_refused(client, db_session, make_user, login_as):
    teacher, _, lesson, _ = await _course(db_session, make_user, "pres-forged")
    login_as(teacher)
    await _upload(client, lesson.id)

    assert (await client.get("/api/v1/presentations/not-a-token/x.pptx")).status_code == 403
    # A video ticket is signed with the same key but is not a presentation ticket.
    video = create_video_ticket(lesson.id)
    assert (await client.get(f"/api/v1/presentations/{video}/x.pptx")).status_code == 403


async def test_deleting_lesson_or_section_removes_the_file(client, db_session, make_user, login_as):
    teacher, _, lesson, _ = await _course(db_session, make_user, "pres-cascade")
    login_as(teacher)
    await _upload(client, lesson.id)
    stored = storage.resolve_upload_path((await db_session.get(Lesson, lesson.id, populate_existing=True)).presentation_path)
    assert stored.is_file()
    assert (await client.delete(f"/api/v1/teacher/sections/{lesson.section_id}")).status_code == 204
    assert stored.is_file()  # in the trash
    assert (await client.delete(f"/api/v1/teacher/trash/section/{lesson.section_id}")).status_code == 204
    assert not stored.exists()


async def test_teacher_can_preview(client, db_session, make_user, login_as):
    teacher, _, lesson, _ = await _course(db_session, make_user, "pres-preview")
    login_as(teacher)
    assert (await client.post(f"/api/v1/teacher/lessons/{lesson.id}/presentation/link")).status_code == 404
    await _upload(client, lesson.id)
    preview = await client.post(f"/api/v1/teacher/lessons/{lesson.id}/presentation/link")
    assert preview.status_code == 200
    assert (await client.get(_file_path_from(preview.json()["embed_url"]))).status_code == 200


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def test_ppsx_goes_through_the_office_viewer(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "pres-ppsx")
    login_as(teacher)
    assert (await _upload(client, lesson.id, "Показ.ppsx", PPTX)).status_code == 200

    login_as(student)
    link = (await _student_link(client, lesson.id)).json()
    assert link["kind"] == "office"
    file_path = _file_path_from(link["embed_url"])
    assert file_path.endswith(f"/lesson-{lesson.id}.ppsx")
    served = await client.get(file_path)
    assert served.status_code == 200
    assert served.headers["content-type"] == storage.PRESENTATION_MEDIA_TYPES[".ppsx"]


async def test_pdf_is_served_directly_not_through_microsoft(client, db_session, make_user, login_as):
    teacher, student, lesson, _ = await _course(db_session, make_user, "pres-pdf")
    login_as(teacher)
    uploaded = await _upload(client, lesson.id, "Слайды.pdf", PDF)
    assert uploaded.status_code == 200
    assert uploaded.json()["presentation_name"] == "Слайды.pdf"

    login_as(student)
    link = (await _student_link(client, lesson.id)).json()
    assert link["kind"] == "pdf"
    assert link["embed_url"] is None
    assert link["file_path"].endswith(f"/lesson-{lesson.id}.pdf")
    served = await client.get(f"/api/v1{link['file_path']}")
    assert served.status_code == 200
    assert served.content == PDF
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["content-disposition"].startswith("attachment")
    assert served.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("name", "body"),
    [("fake.pdf", b"<html><script>alert(1)</script>"), ("deck.pdf", PPTX), ("slides.ppsx", PDF), ("deck.pptm", PPTX)],
)
async def test_contents_must_match_the_extension(client, db_session, make_user, login_as, name, body):
    teacher, _, lesson, _ = await _course(db_session, make_user, f"pres-mismatch-{name}")
    login_as(teacher)
    assert (await _upload(client, lesson.id, name, body)).status_code == 400
