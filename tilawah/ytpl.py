"""Personal Top-40 shelf: ingest a YouTube playlist URL via yt-dlp.

Runs `yt-dlp` as a subprocess (never a hard dependency): missing binary
produces a one-line install hint instead of a traceback. Downloads audio-only
(opus best-audio, no transcoding so ffmpeg is not required), writes
`<NN> - <title>.<ext>` files into <download_dir>/Playlist/, and registers each
track in the SQLite `playlist` table so the shelf survives restarts.
"""

import glob as _glob
import os
import re
import subprocess
from pathlib import Path

from . import deps


class PlaylistError(Exception):
    pass


# Built-in default: the app ships ready to fetch this shelf on any device
# (overridable per-user via config youtube_playlist_url or CLI arg).
DEFAULT_PLAYLIST_URL = "https://youtube.com/playlist?list=PLP0jbtgujqzcxv0yaSDOMoKOYNEZTc4Ez"




# The author's Top picks: stable catalog (video ids never change, even
# when YouTube reorders the playlist). Titles refresh from YouTube when
# available; local files + DB rows always win for playback.
SHELF_TRACKS = [
    {"idx": 1, "id": "SEn5bCcGYnI", "title": "Surah Al-Mursalat in a tearful Saba maqam! A recitation by Sheikh Dr. Yasser Al-Dosari"},
    {"idx": 2, "id": "1ML6jXT86EM", "title": "- ذِكْرُ رَحْمَتِ رَبِّكَ عَبْدَهُۥ زَكَرِيَّآ -"},
    {"idx": 3, "id": "6p2RHWO98HM", "title": "Remember me I'll Remember you | Sheikh Muhammad Al-Luhaidan | Surah Al-Baqarah | Ayah 150-157 | 1446 هـ"},
    {"idx": 4, "id": "FNQRnioFicc", "title": "Is not God sufficient for His servant?"},
    {"idx": 5, "id": "4G2fvDs47A0", "title": "Surah At-Tur (Complete | 1-49) by Muhammad Al-Luhaidan - QURAN is LIFE"},
    {"idx": 6, "id": "9PiDwWDuiQw", "title": "سورة المؤمنون (63-98) || شيخ ابو بكر الشاطري"},
    {"idx": 7, "id": "oEVOnkfjqlY", "title": "أواخر سورة المؤمنون (آية 99-118) || شيخ ابو بكر الشاطري"},
    {"idx": 8, "id": "tPnSQG7Kmn4", "title": "Juz Amma | Sheikh Yasser Al-Dossary"},
    {"idx": 9, "id": "hKWl4ZIXvmU", "title": "Al Kahf | سورة الكهف | Sheikh Yasser al Dosari | English Translation | الشيخ ياسر الدوسري"},
    {"idx": 10, "id": "dBPTe0tBT-A", "title": "Surah Al-Qalam (Complete | 1-52) by Sheikh Saud Al-Juma'a - QURAN is LIFE"},
    {"idx": 11, "id": "PI2Tro8hWsE", "title": "﴿ ألا بذكر الله تطمئن القلوب﴾  من أجمل التلاوات ~ تلاوة تفوق الوصف للقارئ الشيخ د. ياسر الدوسري"},
    {"idx": 12, "id": "i6qFGD8014I", "title": "Surah Ahzab - Abu Bakr Shatri - Taraweeh Edition HD"},
    {"idx": 13, "id": "1OEAkSq6fug", "title": "﴿بديع السماوات والأرض﴾ تلاوة عراقية تاريخية لا توصف أبكت القلوب للقارئ الشيخ د. ياسر الدوسري"},
    {"idx": 14, "id": "Mg9gkMrgqro", "title": "Surah Al-Furqan [61-77] Muhammad Al Luhaidan | ‎سورة الفرقان محمد اللحيدان وكان الله غفورا رحيما"},
    {"idx": 15, "id": "WzOV_7FMPPk", "title": "تلاوة بترتيل مؤثر ومنفرد في غاية الإبداع والخشوع سيخلدها التاريخ للقارئ الشيخ د. ياسر الدوسري"},
    {"idx": 16, "id": "34z7usvHT8k", "title": "Soothing recitation of Surah Waqiah by Yasser al Dosari, MUST WATCH!!!"},
    {"idx": 17, "id": "HVVJUy2JfC4", "title": "Amazing recitation of Surah Rahman by Yasser al dosari | صورة الرحمان - ياسر الدوسري"},
    {"idx": 18, "id": "YgNNPPYZ22Y", "title": "SURAH AT-TUR | SHEIKH YASSER DOSSARY"},
    {"idx": 19, "id": "WVMQC9E2j8A", "title": "سورة مريم كاملة في تلاوة مبكية وخاشعة من الآسر د. ياسر الدوسري | ليالي رمضان 1441هـ"},
    {"idx": 20, "id": "I_23MR3sIRI", "title": "خشوع تلاوات أبو بكر الشاطري 🌌🎑"},
    {"idx": 21, "id": "kf0GA8FGTHQ", "title": "Surah Maryam | Ahmad Al Amin"},
    {"idx": 22, "id": "ZCy0IOS-HSY", "title": "قارئ ابو بكر الشاطري «وقال الذي آمن يا قوم» | تلاوة نادرة"},
    {"idx": 23, "id": "k01iJta6MS0", "title": "\"And by the ten days\" | Emotional Recitation of Al-Fajr | Sheikh Yasser al-Dosari | #ياسر_الدوسري"},
    {"idx": 24, "id": "fdROzfNYtQY", "title": "- إِنَّ هَٰذَا الْقُرْآنَ يَهْدِي لِلَّتِي هِيَ أَقْوَمُ -"},
    {"idx": 25, "id": "gwfzShOk3y8", "title": "Muhammad Al luhaidan Surah Al Baqarah 54-59 محمد اللحيدان سورة البقرة ٥٤-٥٩"},
    {"idx": 26, "id": "dCS3M-vbA24", "title": "Rare recitation of Sheikh Yasser al Dossari from 1425 / Surah al Ahzab 35-40 / #youtube #shorts"},
    {"idx": 27, "id": "9FUCJgpXmD4", "title": "تلاوه رائعه للشيخ ياسر الدوسري(امن يجيب المضطر إذا دعاه)"},
    {"idx": 28, "id": "t7AdDiNxP3I", "title": "استمع إلى جمال الترتيل بصوت فضيلة الشيخ ياسر الدوسري. 🎧🤍"},
    {"idx": 29, "id": "L810GLkAw9Y", "title": "Taraweeh Ahmad Ameen Quran Recitation at NOOR Islamic Cultural Center"},
    {"idx": 30, "id": "clWdGIecnOI", "title": "Who is Allah? 😔❤️"},
    {"idx": 31, "id": "Gn_s_gNxzLo", "title": "سورة : الإسراء - Al-Isrā | لفضيلة الشيخ الدكتور ياسر الدوسري 1425 ه‍ـ"},
    {"idx": 32, "id": "A0mZ_XCEhuo", "title": "سورة الأنعام - الشيخ ياسر الدوسري - 1425 هـ"},
    {"idx": 34, "id": "dXneZvtmlDU", "title": "Surah Taha | Yasser al Dosari Mesmerizing Recitation"},
    {"idx": 36, "id": "qcm168-WltA", "title": "Surah Luqman by Yasser Al-Dosari | Quran Recitation"},
    {"idx": 37, "id": "UVzbB8RjSbc", "title": "Muhammad al-Luhaydan - Surah 19 «Maryam»"},
    {"idx": 39, "id": "V0ojLtxOiYM", "title": "ASH-SHU‘ARĀ’ (I Poeti) – سورة الشعراء | Yasser Al‑Dosari | Traduzione Italiana"},
]

def watch_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def _present(path):
    try:
        return bool(path) and os.path.exists(path) and os.path.getsize(path) > 1024
    except OSError:
        return False


def shelf_status(store, download_dir):
    """The 36 top picks with live saved/missing state, plus the user's own
    extra links. Identity order per entry: new DB key -> old DB title ->
    NN file prefix (original playlist order) -> title glob -> missing.
    Local files and DB rows always win over YouTube (videos can even leave
    the online playlist and keep working). Never raises."""
    dest = Path(str(download_dir)).expanduser() / "Playlist"
    try:
        rows = store.get_playlist()
    except Exception:
        rows = []
    by_url = {}
    by_title = {}
    for t in rows:
        by_url.setdefault(t.get("url", "").split("#")[0], t)
        title = str(t.get("title", "")).strip().lower()
        if title:
            by_title.setdefault(title, t)
    try:
        files = [f for f in os.listdir(dest)
                 if os.path.isfile(os.path.join(dest, f))]
    except OSError:
        files = []
    used_urls, used_paths, out = set(), set(), []
    for e in SHELF_TRACKS:
        url = watch_url(e["id"])
        fp, hit = "", None
        hit = by_url.get(url)
        if hit and _present(hit.get("filepath", "")):
            fp = hit["filepath"]
        if not fp:
            hit = by_title.get(e["title"].strip().lower())
            if hit and _present(hit.get("filepath", "")):
                fp = hit["filepath"]
        if not fp:
            pre = f"{e['idx']:02d} - "
            for f in files:
                if f.startswith(pre) and os.path.join(dest, f) not in used_paths:
                    fp = os.path.join(dest, f)
                    break
        if not fp:
            for pat in (e["title"][:45], e["title"][:25]):
                if not pat.strip():
                    continue
                for f in _glob.glob(os.path.join(_glob.escape(str(dest)),
                                                 _glob.escape(pat) + "*")):
                    if f not in used_paths and _present(f):
                        fp = f
                        break
                if fp:
                    break
        if hit:
            used_urls.add(hit.get("url", ""))
        if fp:
            used_paths.add(fp)
        out.append({"idx": e["idx"], "id": e["id"], "title": e["title"],
                    "url": url, "filepath": fp, "present": bool(fp), "static": True})
    for t in rows:
        if t.get("url", "") in used_urls:
            continue
        fp = t.get("filepath", "")
        if fp in used_paths:
            continue
        if not _present(fp):
            continue
        out.append({"idx": None, "id": "", "title": t.get("title", "?"),
                    "url": t.get("url", ""), "filepath": fp,
                    "present": True, "static": False})
    return out


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
            capture_output=True, text=True, errors="replace", timeout=timeout)
    except FileNotFoundError:
        raise PlaylistError(hint)
    if proc.returncode != 0:
        raise PlaylistError("could not read that playlist - is the URL right?")
    return [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]


def _build_cmd(url, dest, max_items, single):
    if single:
        outtmpl = str(dest / "%(title).80s.%(ext)s")
        scope = ["--no-playlist"]
    else:
        outtmpl = str(dest / "%(playlist_index)02d - %(title).80s.%(ext)s")
        scope = ["--yes-playlist"]
    return (["yt-dlp"] + scope + ["--newline", "--no-colors",
            "--max-downloads", str(1 if single else max_items),
            "-f", "bestaudio/best",
            "--no-post-overwrites", "--continue",
            "-o", outtmpl,
            "--print", "after_move:%(title)s ||| %(filepath)s",
            url])


def ingest(playlist_url, download_dir, store=None, progress=None, max_items=40,
           file_progress=None, stop=None, single=False):
    ok, hint = deps.yt_dlp()
    if not ok:
        raise PlaylistError(hint)
    dest = Path(str(download_dir)).expanduser() / "Playlist"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = _build_cmd(playlist_url, dest, max_items, single)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace")
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
