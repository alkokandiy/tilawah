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


def ingest(playlist_url, download_dir, store=None, progress=None, max_items=40):
    ok, hint = deps.yt_dlp()
    if not ok:
        raise PlaylistError(hint)
    dest = Path(str(download_dir)).expanduser() / "Playlist"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["yt-dlp", "--yes-playlist",
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
        line = line.strip()
        m = re.match(r"(.+?) \|\|\| (.+)", line)
        if m:
            title, path = m.group(1).strip(), m.group(2).strip()
            tracks.append({"title": title, "filepath": path, "url": playlist_url})
            if store is not None:
                store.upsert_track(title, playlist_url + "#" + title, path)
            if progress:
                progress(len(tracks), title)
    proc.wait()
    if proc.returncode != 0 and not tracks:
        raise PlaylistError(
            f"yt-dlp exited with code {proc.returncode} — check the playlist URL "
            f"(must be public/unlisted) and your connection.")
    return tracks
