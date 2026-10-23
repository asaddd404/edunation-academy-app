"""YouTube links on lessons, reduced to the one thing that is safe to keep.

A lesson's `video_url` is typed by a teacher and later becomes the `src` of
an <iframe> in every student's browser. So nothing from the string survives
except an 11-character video id matched against a fixed pattern: the stored
value is rebuilt from that id, and the player URL is rebuilt again from it on
the client. A link to any other site, or anything after the id, never
reaches a frame.
"""

import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}
_PATH_PREFIXES = ("/embed/", "/shorts/", "/live/", "/v/")


def youtube_video_id(url: str) -> str | None:
    """The video id in a youtube.com / youtu.be link, or None."""
    parsed = urlparse(url.strip() if "://" in url else f"https://{url.strip()}")
    host = (parsed.hostname or "").lower()
    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in _HOSTS:
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            for prefix in _PATH_PREFIXES:
                if parsed.path.startswith(prefix):
                    candidate = parsed.path[len(prefix):].split("/")[0]
                    break
    return candidate if candidate and _VIDEO_ID.match(candidate) else None


def normalize_youtube_url(value: str | None) -> str | None:
    """For a schema validator: None stays None (field not sent), "" means
    "remove the video", anything else must be a YouTube video link and is
    stored in canonical form."""
    if value is None:
        return None
    if not value.strip():
        return ""
    video_id = youtube_video_id(value)
    if video_id is None:
        raise ValueError("Укажите ссылку на видео YouTube, например https://www.youtube.com/watch?v=…")
    return f"https://www.youtube.com/watch?v={video_id}"
