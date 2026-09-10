"""Real rhythm data: per-track loudness curves via ffmpeg ebur128.

The TUI visualizer is driven by these curves (energy at the current playback
position), so the bars move with the actual recitation - not a fake sine.
Curves are computed once in a background thread and cached as JSON keyed by
path + size + mtime (re-encoding, e.g. shrink-shelf, invalidates cleanly).
Streams without a local file get no curve; the UI falls back to synthesis.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess

_M_RE = re.compile(r"\bM:\s*(-?\d+(?:\.\d+)?)")


def default_cache():
    base = os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache"))
    d = os.path.join(base, "tilawah", "nrg")
    os.makedirs(d, exist_ok=True)
    return d


def _key(path):
    try:
        st = os.stat(path)
        raw = f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime}".encode()
    except OSError:
        raw = os.path.abspath(path).encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def _moments_to_energy(moments):
    """Raw momentary LUFS, clamped to [-70, 0]. No linear pre-mapping: real
    content lives in a narrow band (-45..-10) that any fixed linear map
    crushes to the rails, so scaling happens in _normalize instead."""
    out = []
    for m in moments:
        try:
            out.append(min(0.0, max(-70.0, float(m))))
        except ValueError:
            out.append(-70.0)
    return out


def _normalize(values):
    """Stretch to the file's own dynamic range (5th/95th percentile), so a
    whisper-quiet murattal and a loud YouTube master both use the full scale
    instead of pinning at 0 or 1."""
    if not values:
        return values
    xs = sorted(values)
    lo = xs[max(0, int(len(xs) * 0.05))]
    hi = xs[min(len(xs) - 1, int(len(xs) * 0.95))]
    if hi - lo < 1e-6:
        med = xs[len(xs) // 2]
        return [(0.5 if med > -50 else 0.0) for _ in values]
    return [min(1.0, max(0.0, (v - lo) / (hi - lo))) for v in values]


def _resample(values, buckets):
    if not values:
        return [0.0] * buckets
    if len(values) == buckets:
        return values
    out = []
    for i in range(buckets):
        a = int(i * len(values) / buckets)
        b = max(a + 1, int((i + 1) * len(values) / buckets))
        # mean energy per bucket: max-pooling would let one peak pin every
        # bucket to 1.0 and erase verse/pause structure.
        seg = values[a:b]
        out.append(sum(seg) / len(seg))
    # light smoothing so bars breathe instead of jitter
    sm = []
    for i, v in enumerate(out):
        win = out[max(0, i - 1):i + 2]
        sm.append(sum(win) / len(win))
    return sm


def energy_curve(path, buckets=160, cache_dir=None, timeout=300):
    """Return {'v': [...], 'dur': seconds} or None. Never raises."""
    if not path or not os.path.exists(path):
        return None
    if shutil.which("ffmpeg") is None:
        return None
    try:
        d = cache_dir or default_cache()
        os.makedirs(d, exist_ok=True)
        cf = os.path.join(d, f"nrg-{_key(path)}.json")
        if os.path.exists(cf):
            with open(cf, encoding="utf-8") as fh:
                data = json.load(fh)
            if (isinstance(data.get("v"), list) and len(data["v"]) == buckets
                    and data.get("algo") == 3):
                return data
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-map", "0:a", "-af", "ebur128", "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout)
        moments = _M_RE.findall(proc.stderr or "")
        moments = moments[5:]  # drop ebur128 ~0.5s gating warmup (fake dynamics)
        if not moments:
            return None
        dur = _duration(path)
        data = {"v": _normalize(_resample(_moments_to_energy(moments), buckets)),
                "dur": dur, "algo": 3}
        try:
            with open(cf, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except Exception:
            pass
        return data
    except Exception:
        return None


def _duration(path):
    if shutil.which("ffprobe") is None:
        return 0.0
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                            "format=duration", "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60)
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0


def at(curve, pos, dur):
    """Energy 0..1 at playback second `pos`."""
    try:
        v = curve["v"]
        if not v or not dur:
            return 0.0
        i = min(len(v) - 1, max(0, int(pos / dur * len(v))))
        return v[i]
    except Exception:
        return 0.0
