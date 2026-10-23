/**
 * The video id in a YouTube link, or null -- the client half of
 * app/core/youtube.py. The server already stores only canonical links; this
 * re-derives the id rather than trusting the stored string, so whatever is
 * in the database, the only thing that can reach an <iframe src> is an
 * 11-character id on a fixed player URL.
 */
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
const HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtube-nocookie.com",
  "www.youtube-nocookie.com",
]);
const PATH_PREFIXES = ["/embed/", "/shorts/", "/live/", "/v/"];

export function youtubeVideoId(url: string | null | undefined): string | null {
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url.includes("://") ? url.trim() : `https://${url.trim()}`);
  } catch {
    return null;
  }
  const host = parsed.hostname.toLowerCase();
  let candidate: string | null = null;
  if (host === "youtu.be") candidate = parsed.pathname.replace(/^\//, "").split("/")[0];
  else if (HOSTS.has(host)) {
    if (parsed.pathname === "/watch") candidate = parsed.searchParams.get("v");
    else {
      const prefix = PATH_PREFIXES.find((p) => parsed.pathname.startsWith(p));
      if (prefix) candidate = parsed.pathname.slice(prefix.length).split("/")[0];
    }
  }
  return candidate && VIDEO_ID.test(candidate) ? candidate : null;
}
