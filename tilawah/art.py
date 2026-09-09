"""Terminal visuals: Islamic-geometric ambient animation + ASCII/ANSI art.

- `motif_frame(w, h, t)`: frame-based 8-pointed-star (rub el hizb style)
  animation. Two overlaid squares counter-rotate slowly while a ring
  "breathes" in and out; pure math, no dependencies, deterministic.
- `photo_to_ansi(path, width)`: Pillow luminance ramp -> block cells with
  ANSI colors, rendered once and cached under XDG cache as `.ans` text so
  reuse is instant. Without Pillow (or without a photo — the mp3quran API
  serves no reciter photos) falls back to a generated geometric avatar.
- `avatar_ansi(name, width)`: deterministic per-reciter geometric medallion.
- `splash_lines(w)`: launch splash screen art.
"""

import hashlib
import math
import os

RAMP = " .:-=+*#%@"
BARS = "▁▂▃▄▅▆▇█"
STAR = "\u2736"

ANIMS = ["orbit", "star", "waves"]


def frame(anim, w, h, t, frac=0.0):
    """Dispatcher: 'orbit' | 'star' | 'waves'. frac draws a progress ring."""
    if anim == "waves":
        return waves_frame(w, h, t)
    if anim == "orbit":
        return orbit_frame(w, h, t, frac)
    return motif_frame(w, h, t)


def motif_frame(w, h, t):
    """Return `h` strings of width `w` — one animation frame at time `t`.

    Geometry: normalized coords in [-1,1]; r = radius, a = angle. Two squares
    rotated by +/- (t*speed) give the 8-point star; ring = breathing circle;
    intensity -> luminance ramp character.
    """
    cx, cy = 0.0, 0.0
    rot = t * 0.25
    breathe = 0.5 + 0.5 * math.sin(t * 0.8)
    ring_r = 0.45 + 0.18 * breathe
    lines = []
    aspect = 2.0  # terminal cells are ~2x taller than wide
    for y in range(h):
        row = []
        for x in range(w):
            nx = (x / max(1, w - 1) * 2 - 1) * (w / max(1, h)) / aspect
            ny = (y / max(1, h - 1) * 2 - 1)
            r = math.hypot(nx - cx, ny - cy)
            a = math.atan2(ny - cy, nx - cx)
            # two squares: |x|+|y| style distance in rotated frames
            def sqdist(ang):
                ca, sa = math.cos(ang), math.sin(ang)
                rx = (nx - cx) * ca + (ny - cy) * sa
                ry = -(nx - cx) * sa + (ny - cy) * ca
                return max(abs(rx), abs(ry))
            d1 = sqdist(rot)
            d2 = sqdist(-rot + math.pi / 4)
            star_edge = min(abs(d1 - 0.55), abs(d2 - 0.55))
            star = max(0.0, 1.0 - star_edge * 6.0)
            ring = max(0.0, 1.0 - abs(r - ring_r) * 7.0)
            center = max(0.0, 1.0 - r * 2.4) * (0.35 + 0.3 * breathe)
            cross = max(0.0, 1.0 - min(abs(nx - cx), abs(ny - cy)) * 9.0) * 0.25
            v = min(1.0, star * 0.9 + ring * 0.75 + center + cross)
            # soft outer arabesque dots
            dots = (math.sin(nx * 9 + t) * math.sin(ny * 9 - t))
            if r > 0.75 and dots > 0.86:
                v = max(v, 0.55)
            row.append(RAMP[int(v * (len(RAMP) - 1))])
        lines.append("".join(row))
    return lines


def orbit_frame(w, h, t, frac=0.0):
    """Twinkling starfield + rotating 8-point star + optional progress ring.

    `frac` (0..1) draws a bright arc around the motif — used in fullscreen
    as a progress ring around the artwork.
    """
    rot = t * 0.35
    breathe = 0.5 + 0.5 * math.sin(t * 0.9)
    lines = []
    aspect = 2.0
    for y in range(h):
        row = []
        for x in range(w):
            nx = (x / max(1, w - 1) * 2 - 1) * (w / max(1, h)) / aspect
            ny = (y / max(1, h - 1) * 2 - 1)
            r = math.hypot(nx, ny)

            def sqdist(ang):
                ca, sa = math.cos(ang), math.sin(ang)
                return max(abs(nx * ca + ny * sa), abs(-nx * sa + ny * ca))

            edge = min(abs(sqdist(rot) - 0.5), abs(sqdist(-rot + math.pi / 4) - 0.5))
            star = max(0.0, 1.0 - edge * 7.0)
            glow = max(0.0, 0.55 - r) * (0.35 + 0.35 * breathe)
            # twinkling field: deterministic hash shimmer
            tw = math.sin(x * 12.9898 + y * 78.233 + t * (1 + (x * y % 5) * 0.4))
            spark = 0.6 if (tw > 0.985 and r > 0.6) else 0.0
            # corner ornaments
            cx = min(x, w - 1 - x) / max(1, w)
            cy = min(y, h - 1 - y) / max(1, h)
            corner = 0.5 if (cx < 0.03 and cy < 0.09) else 0.0
            v = min(1.0, star * 0.95 + glow + spark + corner)
            # progress ring
            if frac > 0 and abs(r - 0.82) < 0.045:
                ang = (math.atan2(ny, nx) / (2 * math.pi) + 0.25) % 1.0
                v = 1.0 if ang < frac else max(v, 0.3)
            row.append(RAMP[int(v * (len(RAMP) - 1))])
        lines.append("".join(row))
    return lines


def waves_frame(w, h, t):
    """Layered arabesque sine bands drifting horizontally."""
    lines = []
    for y in range(h):
        yn = y / max(1, h - 1) * 2 - 1
        row = []
        for x in range(w):
            xn = x / max(1, w - 1) * 2 - 1
            b1 = math.sin(xn * 5 + t * 1.2 + math.sin(yn * 4 + t * 0.7))
            b2 = math.sin(xn * 9 - t * 0.8 + yn * 6)
            band = max(0.0, 1.0 - abs(yn * 1.6 - b1 * 0.35) * 4.0)
            band2 = max(0.0, 1.0 - abs(yn * 1.6 + 0.7 - b2 * 0.3) * 5.0) * 0.6
            dia = 0.5 if abs(abs(xn) - abs(yn) * 1.4) < 0.02 else 0.0
            v = min(1.0, band * 0.9 + band2 + dia * 0.4)
            row.append(RAMP[int(v * (len(RAMP) - 1))])
        lines.append("".join(row))
    return lines


def bars(width, t, lively=True):
    """Simulated spectrum bars (time-driven; honest fallback where the
    backend exposes no audio levels)."""
    out = []
    for i in range(width):
        v = (math.sin(t * 2.1 + i * 0.55) * 0.5 + 0.5) * 0.6 + \
            (math.sin(t * 3.7 + i * 1.3) * 0.5 + 0.5) * 0.4
        if not lively:
            v *= 0.15
        out.append(BARS[int(v * (len(BARS) - 1))])
    return "".join(out)


def avatar_ansi(name, width=24):
    """Deterministic geometric medallion for a reciter name (no photo needed)."""
    seed = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    h = width // 2
    lines = motif_frame(width, h, (seed % 100) / 10.0)
    initial = (name.strip()[:1] or "?").upper()
    mid = len(lines) // 2
    if lines:
        row = lines[mid]
        c = len(row) // 2
        lines[mid] = row[:c - 1] + f"[{initial}]" + row[c + 2:]
    return lines


def photo_to_ansi(path, width=28, cache_dir=None):
    """Render a photo file to ANSI art lines, cached per-photo.

    Returns (lines, from_cache). Falls back to avatar when Pillow/photo
    is unavailable — never raises for missing deps.
    """
    path = str(path)
    key = hashlib.md5(path.encode()).hexdigest()[:12]
    cache_file = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"art-{key}.ans")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, encoding="utf-8") as fh:
                    return fh.read().splitlines(), True
            except OSError:
                pass
    try:
        from PIL import Image
    except ImportError:
        return avatar_ansi(os.path.basename(path), width), False
    if not os.path.exists(path):
        return avatar_ansi(os.path.basename(path), width), False
    try:
        img = Image.open(path).convert("L")
        aspect = img.height / max(1, img.width)
        h = max(4, int(width * aspect * 0.5))
        img = img.resize((width, h))
        px = img.load()
        lines = []
        for y in range(h):
            row = []
            for x in range(width):
                v = px[x, y] / 255.0
                ch = RAMP[int(v * (len(RAMP) - 1))]
                row.append(f"\x1b[38;5;{232 + int(v * 23)}m{ch}\x1b[0m")
            lines.append("".join(row))
        if cache_file:
            try:
                with open(cache_file, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(lines))
            except OSError:
                pass
        return lines, False
    except Exception:
        return avatar_ansi(os.path.basename(path), width), False


def splash_lines(w=60):
    star = STAR
    inner = max(10, w - 4)
    return [
        "+" + "-" * (w - 2) + "+",
        "|" + f"  {star}  T I L A W A H  {star}".center(w - 2) + "|",
        "|" + "terminal Qur'an audio player".center(w - 2) + "|",
        "|" + ("~" * min(inner, 34)).center(w - 2) + "|",
        "|" + "press any key".center(w - 2) + "|",
        "+" + "-" * (w - 2) + "+",
    ]
