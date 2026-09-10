"""Resumable, polite downloader with real progress bars (stdlib only).

- Skips files that already exist with a plausible size (>32KB).
- Resumes partial files with HTTP Range (server sends Accept-Ranges: bytes).
- One connection at a time + small delay between files; never parallel-hammer.
- Progress callback receives (downloaded_bytes, total_bytes_or_0).
"""

import time
import urllib.request
from pathlib import Path

from . import api

UA = api.UA
GAP_BETWEEN_FILES = 0.25
CHUNK = 64 * 1024
MIN_VALID = 32 * 1024


class DownloadError(Exception):
    pass


class Cancelled(Exception):
    """Raised by progress callbacks to abort a download mid-file.

    The partial file stays on disk so the next attempt resumes via Range.
    """


def _local_name(download_dir, reciter_name, surah_number):
    safe = "".join(c if (c.isalnum() or c in " -_") else "_" for c in reciter_name).strip()
    return Path(str(download_dir)).expanduser() / safe / f"{int(surah_number):03d}.mp3"


def already_cached(path):
    try:
        return Path(path).stat().st_size > MIN_VALID
    except OSError:
        return False


def fetch(url, dest, progress=None, timeout=30):
    """Download one URL to dest with resume. Returns dest path."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if already_cached(dest):
        if progress:
            sz = dest.stat().st_size
            progress(sz, sz)
        return dest
    start = dest.stat().st_size if dest.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if start:
        req.add_header("Range", f"bytes={start}-")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        raise DownloadError(f"download failed for {url}: {e}")
    total = resp.headers.get("Content-Length")
    total = (int(total) + start) if total else 0
    mode = "ab" if start and resp.status == 206 else "wb"
    if mode == "wb":
        start = 0
    downloaded = start
    try:
        with open(dest, mode) as fh:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if dest.stat().st_size <= MIN_VALID:
        raise DownloadError(f"downloaded file too small, likely an error page: {url}")
    return dest


def download_surah(server, reciter_name, surah_number, download_dir, progress=None):
    url = api.audio_url(server, surah_number)
    dest = _local_name(download_dir, reciter_name, surah_number)
    time.sleep(GAP_BETWEEN_FILES)
    return fetch(url, dest, progress=progress)


def download_reciter(reciter, moshaf_index, download_dir, progress=None, only=()):
    """Download a whole reciter/moshaf (or a subset `only` of surah numbers)."""
    moshaf = reciter["moshaf"][moshaf_index]
    surahs = [s for s in api.available_surahs(moshaf) if (not only or s in set(only))]
    results = []
    for i, s in enumerate(surahs):
        def cb(d, t, i=i, s=s):
            if progress:
                progress(s, i, len(surahs), d, t)
        try:
            results.append(str(download_surah(
                moshaf["server"], reciter["name"], s, download_dir, progress=cb)))
        except DownloadError as e:
            results.append(f"ERROR {s}: {e}")
    return results


def bar(downloaded, total, width=24):
    if not total:
        return "[" + "?" * width + "]"
    fill = int(width * downloaded / total)
    return "[" + "#" * fill + "-" * (width - fill) + "]"
