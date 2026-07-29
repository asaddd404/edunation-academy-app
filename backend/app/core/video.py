import asyncio
import json
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
RAW_VIDEO_DIR = UPLOAD_ROOT / "video_raw"
HLS_DIR = UPLOAD_ROOT / "hls"

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
MAX_VIDEO_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB
HLS_SEGMENT_SECONDS = 6


class VideoProcessingError(Exception):
    """Raised when ffmpeg/ffprobe fails; message is safe to show a teacher."""


def hls_dir_for(lesson_id: int) -> Path:
    return HLS_DIR / str(lesson_id)


def master_playlist_path(lesson_id: int) -> Path:
    return hls_dir_for(lesson_id) / "master.m3u8"


def segment_path(lesson_id: int, filename: str) -> Path:
    """Rejects any filename that isn't a bare HLS segment name -- callers pass
    this straight through from the URL path, so it must not be able to escape
    hls_dir_for(lesson_id) via '..' or an absolute path."""
    if "/" in filename or "\\" in filename or not filename.endswith(".ts"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сегмент не найден")
    return hls_dir_for(lesson_id) / filename


async def save_raw_video(lesson_id: int, upload: UploadFile) -> Path:
    """Streams the uploaded file to disk in chunks, enforcing the size cap
    without ever holding the whole video in memory."""
    original_name = upload.filename or "video"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый формат видео")

    raw_dir = RAW_VIDEO_DIR / str(lesson_id)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{uuid.uuid4().hex}{extension}"

    size = 0
    try:
        with dest.open("wb") as f:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_VIDEO_FILE_SIZE:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл слишком большой (максимум 2 ГБ)")
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")

    return dest


async def _run(*args: str, cwd: Path | None = None) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        raise VideoProcessingError(f"{args[0]} не установлен на сервере")
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout, stderr


async def probe_duration_seconds(path: Path) -> int | None:
    returncode, stdout, _ = await _run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)
    )
    if returncode != 0:
        return None
    try:
        data = json.loads(stdout)
        return round(float(data["format"]["duration"]))
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


async def transcode_to_hls(lesson_id: int, raw_path: Path) -> int | None:
    """Transcodes the raw upload into a single-rendition (max 720p) HLS
    stream: an .m3u8 playlist plus .ts segments. Raises VideoProcessingError
    with a teacher-facing message on failure."""
    out_dir = hls_dir_for(lesson_id)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    playlist = out_dir / "master.m3u8"

    # Segment filenames are passed bare (not as absolute paths) with cwd set
    # to out_dir, so the .m3u8 references plain "segment_000.ts" style URIs
    # that resolve correctly against the manifest's own URL on the client.
    returncode, _, stderr = await _run(
        "ffmpeg", "-y", "-i", str(raw_path.resolve()),
        "-vf", "scale='min(1280,iw)':-2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-hls_time", str(HLS_SEGMENT_SECONDS),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", "segment_%03d.ts",
        "master.m3u8",
        cwd=out_dir,
    )
    if returncode != 0 or not playlist.is_file():
        shutil.rmtree(out_dir, ignore_errors=True)
        message = stderr.decode(errors="replace").strip().splitlines()[-1:] if stderr else []
        raise VideoProcessingError(message[0] if message else "Ошибка обработки видео (ffmpeg)")

    return await probe_duration_seconds(raw_path)


def delete_video_assets(lesson_id: int) -> None:
    shutil.rmtree(hls_dir_for(lesson_id), ignore_errors=True)
    shutil.rmtree(RAW_VIDEO_DIR / str(lesson_id), ignore_errors=True)
