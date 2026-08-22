import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.file_type import assert_matches_extension

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
HOMEWORK_DIR = UPLOAD_ROOT / "homework"
CATEGORY_IMAGE_DIR = UPLOAD_ROOT / "categories"
AVATAR_DIR = UPLOAD_ROOT / "avatars"
ENT_QUESTION_IMAGE_DIR = UPLOAD_ROOT / "ent-questions"
LESSON_CONTENT_IMAGE_DIR = UPLOAD_ROOT / "lesson-content"

ALLOWED_HOMEWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt", ".doc", ".docx"}
MAX_HOMEWORK_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_CATEGORY_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_AVATAR_SIZE = 3 * 1024 * 1024  # 3 MB
MAX_ENT_QUESTION_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_LESSON_CONTENT_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


async def save_homework_file(upload: UploadFile) -> tuple[str, str]:
    """Validates and stores an uploaded homework attachment. Returns
    (relative_path, original_filename). Never trusts the client-supplied
    filename for the on-disk name — generates one to avoid path traversal
    or overwrite collisions."""
    original_name = upload.filename or "file"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_HOMEWORK_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый тип файла")

    contents = await upload.read(MAX_HOMEWORK_FILE_SIZE + 1)
    if len(contents) > MAX_HOMEWORK_FILE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 10 МБ)")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    # The extension is whatever the uploader typed; the bytes are not. An
    # .html renamed to .png passes the check above and nothing else.
    assert_matches_extension(contents, extension, "Содержимое файла не соответствует его расширению")

    HOMEWORK_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    (HOMEWORK_DIR / stored_name).write_bytes(contents)

    return f"homework/{stored_name}", original_name


async def save_category_image(upload: UploadFile) -> str:
    """Validates and stores an uploaded category cover image. Returns the
    relative path; caller is responsible for deleting the category's
    previous image (if any) once the new one is safely written."""
    original_name = upload.filename or "image"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый формат изображения (jpg, png, webp)")

    contents = await upload.read(MAX_CATEGORY_IMAGE_SIZE + 1)
    if len(contents) > MAX_CATEGORY_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 5 МБ)")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    assert_matches_extension(contents, extension, "Файл не является изображением в заявленном формате")

    CATEGORY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    (CATEGORY_IMAGE_DIR / stored_name).write_bytes(contents)

    return f"categories/{stored_name}"


async def save_avatar_image(upload: UploadFile) -> str:
    """Validates and stores an uploaded profile avatar. Returns the relative
    path; caller is responsible for deleting the user's previous avatar (if
    any) once the new one is safely written."""
    original_name = upload.filename or "avatar"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый формат изображения (jpg, png, webp)")

    contents = await upload.read(MAX_AVATAR_SIZE + 1)
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 3 МБ)")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    assert_matches_extension(contents, extension, "Файл не является изображением в заявленном формате")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    (AVATAR_DIR / stored_name).write_bytes(contents)

    return f"avatars/{stored_name}"


async def save_ent_question_image(upload: UploadFile) -> str:
    """Validates and stores an illustration for a ЕНТ question (graph, map,
    diagram). Returns the relative path; caller deletes the question's
    previous image once the new one is safely written."""
    original_name = upload.filename or "image"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый формат изображения (jpg, png, webp)")

    contents = await upload.read(MAX_ENT_QUESTION_IMAGE_SIZE + 1)
    if len(contents) > MAX_ENT_QUESTION_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 5 МБ)")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    assert_matches_extension(contents, extension, "Файл не является изображением в заявленном формате")

    ENT_QUESTION_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    (ENT_QUESTION_IMAGE_DIR / stored_name).write_bytes(contents)

    return f"ent-questions/{stored_name}"


async def save_lesson_content_image(upload: UploadFile) -> str:
    """Validates and stores an image embedded in a lesson's rich description
    or homework text. Returns the relative path, which the caller writes into
    the rich-text document's image node.

    Unlike the other image savers there is no "previous image" to delete: one
    lesson body can hold many images, and which of them became unreferenced is
    only knowable by diffing the document (see app.core.rich_content)."""
    original_name = upload.filename or "image"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый формат изображения (jpg, png, webp)")

    contents = await upload.read(MAX_LESSON_CONTENT_IMAGE_SIZE + 1)
    if len(contents) > MAX_LESSON_CONTENT_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 5 МБ)")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    assert_matches_extension(contents, extension, "Файл не является изображением в заявленном формате")

    LESSON_CONTENT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    (LESSON_CONTENT_IMAGE_DIR / stored_name).write_bytes(contents)

    return f"lesson-content/{stored_name}"


def resolve_upload_path(relative_path: str) -> Path:
    return UPLOAD_ROOT / relative_path


def delete_upload(relative_path: str | None) -> None:
    """Best-effort removal of a stored upload. Missing files are fine -- the
    goal is only to stop rows from leaving orphaned bytes on disk."""
    if relative_path:
        resolve_upload_path(relative_path).unlink(missing_ok=True)


_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def image_response(path: Path) -> FileResponse:
    """Serves a stored image with the content type derived from *our* stored
    filename, never from anything the uploader supplied, and with sniffing
    turned off.

    Without `nosniff` a browser is free to ignore the declared type and
    execute a file whose bytes look like HTML -- which is how an "image"
    upload becomes stored XSS on the app's own origin, with the session
    cookie and localStorage of whoever opens it.
    """
    return FileResponse(
        path,
        media_type=_IMAGE_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'"},
    )


def attachment_response(path: Path, filename: str) -> FileResponse:
    """Serves a user-uploaded document as a download, never as a page.

    `Content-Disposition: attachment` plus `nosniff` is what keeps a .txt or
    .docx homework file that happens to contain markup from rendering on the
    app's origin. The declared type is deliberately generic: the uploader's
    `Content-Type` is not trusted here at all.
    """
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=filename,
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'"},
    )
