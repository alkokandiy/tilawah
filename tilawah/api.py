"""mp3quran.net API client. Shapes verified live on 2026-09-09:

GET /api/v3/reciters?language=eng -> {"reciters":[{id,name,letter,date,
    moshaf:[{id,name,rewaya_id,server,surah_total,moshaf_type,surah_list}]}]}
GET /api/v3/suwar?language=eng   -> {"suwar":[{id,name,start_page,end_page,makkia,type}]}
Audio file URL = {server}{NNN}.mp3  (NNN = surah zero-padded to 3 digits,
verified with HEAD requests against server6/server9, both HTTP 200
audio/mpeg with Accept-Ranges: bytes).

No reciter photos exist in the API or on /eng/ listing pages, so reciter
artwork is generated locally (see art.py) — documented in README/DECISIONS.

Politeness: 10s HTTP timeout, Tilawah User-Agent, caller-side rate limiting
in downloader.py, catalog responses cached in SQLite + cache dir.
"""

import json
import time
import urllib.request

BASE = "https://www.mp3quran.net/api/v3"
UA = "Tilawah/1.0 (+terminal quran player)"
_last_call = 0.0
MIN_GAP = 0.4  # seconds between API calls


def _get(url, timeout=15):
    global _last_call
    gap = time.time() - _last_call
    if gap < MIN_GAP:
        time.sleep(MIN_GAP - gap)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        data = json.load(fh)
    _last_call = time.time()
    return data


def fetch_reciters(language="eng"):
    return _get(f"{BASE}/reciters?language={language}").get("reciters", [])


def fetch_suwar(language="eng"):
    return _get(f"{BASE}/suwar?language={language}").get("suwar", [])


def audio_url(server, surah_number):
    """Build the direct MP3 URL. Server values end with '/' already."""
    if not server.endswith("/"):
        server += "/"
    return f"{server}{int(surah_number):03d}.mp3"


def available_surahs(moshaf):
    """Parse 'surah_list' CSV ('1,2,3,...,114') into a sorted int list."""
    out = []
    for part in str(moshaf.get("surah_list", "")).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return sorted(out)


def find_reciter(reciters, query):
    q = (query or "").strip().lower()
    if not q:
        return None
    for r in reciters:
        if r["name"].lower() == q:
            return r
    for r in reciters:
        if q in r["name"].lower():
            return r
    # scored fallback: most query words (prefix) matching wins, needs >= half
    # (e.g. "Mishary Rashid Alafasy" still finds API name "Mishary Alafasi")
    qtokens = [t for t in q.replace("-", " ").split() if len(t) > 2]
    best, best_score = None, 0
    for r in reciters:
        name = r["name"].lower().replace("-", " ")
        score = sum(1 for t in qtokens if t[:5] in name)
        if score > best_score:
            best, best_score = r, score
    if best and best_score >= max(1, (len(qtokens) + 1) // 2):
        return best
    return None


def offline_ok():
    """True when the API is unreachable (caller should use local cache)."""
    try:
        _get(f"{BASE}/suwar?language=eng", timeout=8)
        return False
    except Exception:
        return True


# The menu shows these 20 only (exact API spellings, verified 2026-09-09).
# Full 242-reciter catalog stays one keypress away (TUI 'C', `reciters --all`).
CURATED_TOP20 = [
    "Mishary Alafasi",
    "Abdulbasit Abdulsamad",
    "Saad Al-Ghamdi",
    "Saud Al-Shuraim",
    "Abdulrahman Alsudaes",
    "Maher Al Meaqli",
    "Mohammed Siddiq Al-Minshawi",
    "Ahmad Al-Ajmy",
    "Yasser Al-Dosari",
    "Bandar Balilah",
    "Fares Abbad",
    "Nasser Alqatami",
    "Ali Alhuthaifi",
    "Shaik Abu Bakr Al Shatri",
    "Mohammed Al-Lohaidan",  # = Muhammad Al-Luhaidan (API transliteration)
]


def curate(reciters):
    """Order the catalog's Top-20 first; return (top20, rest)."""
    by_name = {r["name"]: r for r in reciters}
    top, seen = [], set()
    for name in CURATED_TOP20:
        if name in by_name:
            top.append(by_name[name])
            seen.add(name)
    rest = [r for r in reciters if r["name"] not in seen]
    return top, rest


def preferred_moshaf_index(reciter):
    """Pick the best narration: Hafs Murattal wins, then fuller lists.

    Needed because some reciters have several moshafs all labelled Murattal
    (e.g. Mishary Alafasi: full Hafs v. 6-surah Dorai) and API order is not
    stable across refreshes.
    """
    ms = reciter.get("moshaf", [])
    if not ms:
        return 0

    def score(m):
        name = str(m.get("name", "")).lower()
        s = 0.0
        if "murattal" in name:
            s += 10
        if "hafs" in name:
            s += 10
        try:
            s += len(available_surahs(m)) / 114.0
        except Exception:
            pass
        return s

    return max(range(len(ms)), key=lambda i: score(ms[i]))


# Juz 30 (Juz Amma): surahs 78 (An-Naba) .. 114 (An-Nas).
JUZ30 = list(range(78, 115))
