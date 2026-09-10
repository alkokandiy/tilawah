"""Personal Top-40 shelf: ingest a YouTube playlist URL via yt-dlp.

Runs `yt-dlp` as a subprocess (never a hard dependency): missing binary
produces a one-line install hint instead of a traceback. Downloads audio-only
(opus best-audio, no transcoding so ffmpeg is not required), writes
`<NN> - <title>.<ext>` files into <download_dir>/Playlist/, and registers each
track in the SQLite `playlist` table so the shelf survives restarts.
"""

import re
import subprocess
from pathlib import Path

from . import deps


class PlaylistError(Exception):
    pass


# Built-in default: the app ships ready to fetch this shelf on any device
# (overridable per-user via config youtube_playlist_url or CLI arg).
DEFAULT_PLAYLIST_URL = "https://youtube.com/playlist?list=PLP0jbtgujqzcxv0yaSDOMoKOYNEZTc4Ez"


def _dl_pct(line):
    """yt-dlp '[download] 45.2%' fragment -> float, else None."""
    ms = re.findall(r"\[download\]\s+(\d+(?:\.\d+)?)%", line or "")
    return float(ms[-1]) if ms else None


def list_entries(playlist_url, timeout=120):
    """Video ids in a playlist (fast, no downloads)."""
    ok, hint = deps.yt_dlp()
    if not ok:
        raise PlaylistError(hint)
    try:
        proc = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--no-warnings",
             "--print", "%(id)s", playlist_url],
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise PlaylistError(hint)
    if proc.returncode != 0:
        raise PlaylistError("could not read that playlist - is the URL right?")
    return [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]


def ingest(playlist_url, download_dir, store=None, progress=None, max_items=40,
           file_progress=None, stop=None):
    ok, hint = deps.yt_dlp()
    if not ok:
        raise PlaylistError(hint)
    dest = Path(str(download_dir)).expanduser() / "Playlist"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["yt-dlp", "--yes-playlist", "--newline", "--no-colors",
           "--max-downloads", str(max_items),
           "-f", "bestaudio/best",
           "--no-post-overwrites", "--continue",
           "-o", str(dest / "%(playlist_index)02d - %(title).80s.%(ext)s"),
           "--print", "after_move:%(title)s ||| %(filepath)s",
           playlist_url]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
    except FileNotFoundError:
        raise PlaylistError(hint)
    tracks = []
    for line in proc.stdout or []:
        if stop is not None and stop.is_set():
            try:
                proc.terminate()
            except Exception:
                pass
            break
        line = line.strip()
        m = re.match(r"(.+?) \|\|\| (.+)", line)
        if m:
            title, path = m.group(1).strip(), m.group(2).strip()
            tracks.append({"title": title, "filepath": path, "url": playlist_url})
            if store is not None:
                store.upsert_track(title, playlist_url + "#" + title, path)
            if progress:
                progress(len(tracks), title)
            continue
        if file_progress:
            pct = _dl_pct(line)
            if pct is not None:
                try:
                    file_progress(pct, line[:80])
                except Exception:
                    pass
    proc.wait()
    if proc.returncode != 0 and not tracks:
        raise PlaylistError(
            f"yt-dlp exited with code {proc.returncode} — check the playlist URL "
            f"(must be public/unlisted) and your connection.")
    return tracks
