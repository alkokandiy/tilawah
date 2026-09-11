"""Optional-dependency detection with one-line fix messages (never tracebacks)."""

import shutil


def check(exe, install_hint):
    found = shutil.which(exe) is not None
    return found, None if found else install_hint


def mpv():
    return check("mpv", "mpv not found - install it with: sudo apt install mpv")


def yt_dlp():
    return check("yt-dlp", "yt-dlp not found - install it with: sudo apt install yt-dlp")


def ffmpeg():
    return check("ffmpeg", "ffmpeg not found - install it with: sudo apt install ffmpeg")


def pillow():
    try:
        import PIL  # noqa: F401
        return True, None
    except ImportError:
        return False, "Pillow not found - install it with: pip install Pillow"


def status():
    return {
        "mpv": mpv(),
        "yt-dlp": yt_dlp(),
        "ffmpeg": ffmpeg(),
        "pillow": pillow(),
    }


def audio_check(timeout=20):
    """Can this machine actually make sound through mpv? Plays a 1s stdlib
    synthesized tone and reads mpv's verdict. Returns (ok, message)."""
    import math
    import struct
    import subprocess
    import tempfile
    import os
    if shutil.which("mpv") is None:
        return False, "mpv missing - install it with: sudo apt install mpv"
    try:
        fd, path = tempfile.mkstemp(suffix=".wav")
        n = 8000
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVEfmt "
                     + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
                     + b"data" + struct.pack("<I", n * 2))
            for i in range(n):
                fh.write(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 8000))))
        try:
            proc = subprocess.run(
                ["mpv", "--no-video", "--no-terminal", "--end=1", path],
                capture_output=True, text=True, timeout=timeout)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        bad = [l.strip() for l in (proc.stderr or "").splitlines()
               if "audio" in l.lower() and any(
                   k in l.lower() for k in ("could not", "failed", "error", "no audio", "disabled"))]
        if bad:
            return False, ("mpv cannot open sound here (" + bad[0][:110] + ") - "
                           "check volume / install pulseaudio or pipewire")
        return True, "mpv plays sound on this machine"
    except FileNotFoundError:
        return False, "mpv missing - install it with: sudo apt install mpv"
    except Exception as e:
        return False, f"audio check inconclusive ({e})"
