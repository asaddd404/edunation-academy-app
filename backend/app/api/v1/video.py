import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import can_watch_lesson_video
from app.core.video import master_playlist_path, segment_path
from app.database import get_db
from app.security import decode_video_ticket

router = APIRouter(prefix="/video", tags=["video"])


def _check_ticket(lesson_id: int, cookie_token: str | None) -> int:
    if not cookie_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к видео")
    try:
        return decode_video_ticket(cookie_token, lesson_id)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка на видео недействительна или истекла")


@router.get("/lessons/{lesson_id}/{filename}")
async def get_video_file(
    lesson_id: int,
    filename: str,
    video_ticket: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serves both the HLS manifest and its .ts segments under one flat path
    so that the plain relative segment URIs ffmpeg writes into master.m3u8
    resolve correctly against this endpoint's own URL. Access is granted
    only by the httpOnly `video_ticket` cookie set when the ticket was
    issued. The old `?token=` query form is gone: nothing in the app used
    it, and a URL carrying a credential is one that can be pasted into a
    chat and played by anyone for the ticket's whole lifetime."""
    user_id = _check_ticket(lesson_id, video_ticket)

    if filename == "master.m3u8":
        # Access is re-checked against the database where playback starts.
        # Not per segment: that is a request every few seconds per viewer,
        # and the playlist is what every (re)start of the player loads.
        if not await can_watch_lesson_video(db, user_id, lesson_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к видео")
        path = master_playlist_path(lesson_id)
        media_type = "application/vnd.apple.mpegurl"
    elif filename.endswith(".ts"):
        path = segment_path(lesson_id, filename)
        media_type = "video/mp2t"
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")

    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")
    # The media type comes from the branch above (our own two shapes), never
    # from the request; nosniff stops a browser overriding it anyway.
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            # Segments are immutable once transcoded, and a student seeking
            # backwards should not re-download what they just watched. The
            # ticket expires long before this does, so caching cannot extend
            # access -- it only avoids refetching bytes already delivered.
            # `private` because the ticket is what authorizes them.
            "Cache-Control": "private, max-age=3600",
        },
    )
