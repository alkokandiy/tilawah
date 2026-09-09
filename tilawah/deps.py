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
