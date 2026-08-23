import jwt
from fastapi import APIRouter, Cookie, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.video import master_playlist_path, segment_path
from app.security import decode_video_ticket

router = APIRouter(prefix="/video", tags=["video"])


def _check_ticket(lesson_id: int, token: str | None, cookie_token: str | None) -> None:
    ticket = token or cookie_token
    if not ticket:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к видео")
    try:
        decode_video_ticket(ticket, lesson_id)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ссылка на видео недействительна или истекла")


@router.get("/lessons/{lesson_id}/{filename}")
async def get_video_file(
    lesson_id: int,
    filename: str,
    token: str | None = Query(default=None),
    video_ticket: str | None = Cookie(default=None),
) -> FileResponse:
    """Serves both the HLS manifest and its .ts segments under one flat path
    so that the plain relative segment URIs ffmpeg writes into master.m3u8
    resolve correctly against this endpoint's own URL. Access is granted
    either by a `token` query param or by the `video_ticket` cookie set when
    the ticket was issued -- the cookie is what makes plain <video>/native
    HLS playback (which can't attach query params to segment requests) work."""
    _check_ticket(lesson_id, token, video_ticket)

    if filename == "master.m3u8":
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
