"""Optional-dependency detection with one-line fix messages (never tracebacks).

Hints adapt to the platform instead of assuming apt everywhere:
Debian/Ubuntu/Kali/Mint -> apt, Fedora/RHEL -> dnf, Arch/Manjaro -> pacman,
openSUSE -> zypper, Alpine -> apk, macOS -> brew, Windows -> pip or the
project site. Detection is stdlib-only (no `distro` package needed).
"""

import os
import shutil
import sys


def _linux_manager():
    info = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v.strip('"').lower()
    except OSError:
        pass
    ids = info.get("ID", "") + " " + info.get("ID_LIKE", "")
    if any(x in ids for x in ("arch", "manjaro", "endeavour", "cachyos", "garuda")):
        return "sudo pacman -S"
    if any(x in ids for x in ("fedora", "rhel", "centos", "rocky", "alma", "nobara")):
        return "sudo dnf install"
    if "suse" in ids:
        return "sudo zypper install"
    if "alpine" in ids:
        return "sudo apk add"
    return "sudo apt install"


def install_cmd(pkg, brew=None, pip_pkg=None, site=None):
    """One-line install command for `pkg` on this platform."""
    if sys.platform == "darwin":
        return f"brew install {brew or pkg}"
    if sys.platform == "win32":
        if pip_pkg:
            return f"pip install {pip_pkg}"
        if site:
            return f"get {pkg} from {site}"
        return f"install {pkg} for Windows"
    if sys.platform.startswith("linux"):
        return f"{_linux_manager()} {pkg}"
    if pip_pkg:
        return f"pip install {pip_pkg}"
    return f"install {pkg}"


def check(exe, install_hint):
    found = shutil.which(exe) is not None
    return found, None if found else install_hint


def mpv():
    return check("mpv", "mpv not found - " + install_cmd(
        "mpv", site="https://mpv.io/installation/"))


def yt_dlp():
    return check("yt-dlp", "yt-dlp not found - " + install_cmd(
        "yt-dlp", pip_pkg="yt-dlp"))


def ffmpeg():
    return check("ffmpeg", "ffmpeg not found - " + install_cmd(
        "ffmpeg", site="https://ffmpeg.org/download.html"))


def pillow():
    try:
        import PIL  # noqa: F401
        return True, None
    except ImportError:
        return False, "Pillow not found - pip install Pillow"


def windows_curses():
    """Extra check for Windows, where stdlib curses does not exist."""
    if sys.platform != "win32":
        return True, None
    try:
        import curses  # noqa: F401
        return True, None
    except ImportError:
        try:
            import _curses  # noqa: F401
            return True, None
        except ImportError:
            return False, ("curses missing - on Windows run: "
                           "pip install windows-curses (then use Windows Terminal)")


def status():
    out = {
        "mpv": mpv(),
        "yt-dlp": yt_dlp(),
        "ffmpeg": ffmpeg(),
        "pillow": pillow(),
    }
    if sys.platform == "win32":
        out["windows-curses"] = windows_curses()
    return out


def audio_check(timeout=20):
    """Can this machine actually make sound through mpv? Plays a 1s stdlib
    synthesized tone and reads mpv's verdict. Returns (ok, message)."""
    import math
    import struct
    import subprocess
    import tempfile
    if shutil.which("mpv") is None:
        return False, "mpv missing - " + install_cmd(
            "mpv", site="https://mpv.io/installation/")
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
                           "check volume / sound server")
        return True, "mpv plays sound on this machine"
    except FileNotFoundError:
        return False, "mpv missing - " + install_cmd(
            "mpv", site="https://mpv.io/installation/")
    except Exception as e:
        return False, f"audio check inconclusive ({e})"
