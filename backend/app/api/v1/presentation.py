import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import presentation_response, resolve_upload_path
from app.database import get_db
from app.models.lesson import Lesson
from app.security import decode_presentation_ticket

# No session dependency: the caller is Microsoft's Office viewer, and the
# signed ticket in the path is the whole authorization (see core.presentation).
router = APIRouter(prefix="/presentations", tags=["presentations"])


@router.get("/{ticket}/{filename}")
async def get_presentation_file(ticket: str, filename: str, db: AsyncSession = Depends(get_db)) -> FileResponse:
    try:
        lesson_id, path = decode_presentation_ticket(ticket)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка на презентацию недействительна или истекла")

    lesson = await db.get(Lesson, lesson_id)
    # The ticket names the file it was issued for; a replaced or removed
    # presentation no longer matches, so old links stop working at once.
    if lesson is None or lesson.presentation_path != path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Презентация не найдена")
    file_path = resolve_upload_path(path)
    if not file_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Презентация не найдена")
    return presentation_response(file_path, f"lesson-{lesson_id}{file_path.suffix.lower()}")
