import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
HOMEWORK_DIR = UPLOAD_ROOT / "homework"

ALLOWED_HOMEWORK_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".txt", ".doc", ".docx"}
MAX_HOMEWORK_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


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

    HOMEWORK_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{extension}"
    (HOMEWORK_DIR / stored_name).write_bytes(contents)

    return f"homework/{stored_name}", original_name


def resolve_upload_path(relative_path: str) -> Path:
    return UPLOAD_ROOT / relative_path
