"""Playback engine: queue + shuffle/repeat + sleep timer + backend abstraction.

Backends (first available wins, auto-detected):
  1. mpv        - full control via --input-ipc-server JSON IPC (seek/volume/time).
  2. ffplay     - play/pause/stop/next/prev; seek = restart with -ss offset.
  3. dummy      - simulated clock, no audio. Keeps the whole UI/queue/timer
                  usable on machines without audio (servers, CI, first-run
                  before `apt install mpv`).

Sources: every track carries both a stream `url` and an optional local
`filepath`. When offline (or `offline=True` in config) the engine plays the
local file if cached, else reports a clean error instead of hanging.
"""

import json
import os
import random
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.request

from .surahs import by_number

REPEAT_OFF, REPEAT_ONE, REPEAT_ALL = "off", "one", "all"


# ---------------------------------------------------------------- backends
class Backend:
    name = "none"

    def play(self, source, start_at=0, volume=80):
        raise NotImplementedError

    def pause_toggle(self):
        pass

    def stop(self):
        pass

    def seek(self, delta):
        return 0

    def set_volume(self, vol):
        pass

    def pos(self):
        return 0.0

    def dur(self):
        return 0.0

    def poll_ended(self):
        return False

    def buffering(self):
        return False

    def audio_kbps(self):
        return 0

    def close(self):
        pass


class DummyBackend(Backend):
    """Simulated clock: advances in real time so UI/queue/timers are testable
    with no audio hardware and no dependencies."""

    name = "dummy"

    def __init__(self):
        self._pos = 0.0
        self._dur = 300.0
        self._playing = False
        self._ended = False
        self._t = 0.0
        self._vol = 80
        self._lock = threading.Lock()

    def play(self, source, start_at=0, volume=80):
        with self._lock:
            self._pos = float(start_at)
            self._dur = float(source.get("duration") or 300.0)
            self._playing = True
            self._ended = False
            self._t = time.time()
            self._vol = volume

    def _tick(self):
        with self._lock:
            if self._playing and not self._ended:
                now = time.time()
                self._pos += now - self._t
                self._t = now
                if self._pos >= self._dur:
                    self._pos = self._dur
                    self._playing = False
                    self._ended = True

    def pause_toggle(self):
        self._tick()
        with self._lock:
            if self._ended:
                return
            self._playing = not self._playing
            self._t = time.time()

    @property
    def playing(self):
        self._tick()
        with self._lock:
            return self._playing

    def stop(self):
        with self._lock:
            self._playing = False
            self._ended = True

    def seek(self, delta):
        self._tick()
        with self._lock:
            self._pos = min(max(0.0, self._pos + delta), self._dur)
            return self._pos

    def set_volume(self, vol):
        with self._lock:
            self._vol = max(0, min(100, vol))

    def pos(self):
        self._tick()
        with self._lock:
            return self._pos

    def dur(self):
        with self._lock:
            return self._dur

    def poll_ended(self):
        self._tick()
        with self._lock:
            if self._ended:
                self._ended = False
                return True
            return False


class MpvBackend(Backend):
    name = "mpv"

    def __init__(self):
        if shutil.which("mpv") is None:
            raise RuntimeError("mpv not found - install it with: sudo apt install mpv")
        self.sock_path = f"/tmp/tilawah-mpv-{os.getpid()}.sock"
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass
        self.proc = subprocess.Popen(
            ["mpv", "--idle=yes", "--no-video", "--no-terminal",
             # smooth streaming: deep cache, readahead, auto-reconnect
             "--cache=yes", "--demuxer-max-bytes=80M",
             "--demuxer-readahead-secs=90", "--audio-buffer=5",
             "--gapless-audio=yes",
             "--stream-lavf-o=reconnect=1,reconnect_streamed=1,reconnect_delay_max=5",
             f"--input-ipc-server={self.sock_path}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if os.path.exists(self.sock_path):
                break
            time.sleep(0.05)
        self._paused = False

    def _cmd(self, command, timeout=3):
        """Never raise: a dead mpv must degrade to silence, not a traceback."""
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                s.connect(self.sock_path)
                s.sendall((json.dumps({"command": command}) + "\n").encode())
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                try:
                    return json.loads(buf.decode().split("\n")[0])
                except Exception:
                    return {}
            finally:
                s.close()
        except OSError:
            return {}

    def play(self, source, start_at=0, volume=80):
        path = source.get("filepath") or source.get("url")
        self._cmd(["loadfile", path, "replace"])
        if start_at:
            time.sleep(0.4)
            self._cmd(["seek", start_at, "absolute"])
        self._cmd(["set_property", "volume", volume])
        self._paused = False

    def pause_toggle(self):
        self._paused = not self._paused
        self._cmd(["set_property", "pause", self._paused])

    def stop(self):
        self._cmd(["stop"])

    def seek(self, delta):
        self._cmd(["seek", delta, "relative"])
        return self.pos()

    def set_volume(self, vol):
        self._cmd(["set_property", "volume", max(0, min(100, vol))])

    def _prop(self, name):
        r = self._cmd(["get_property", name])
        return r.get("data", 0.0) or 0.0

    def pos(self):
        try:
            return float(self._prop("time-pos"))
        except Exception:
            return 0.0

    def dur(self):
        try:
            return float(self._prop("duration"))
        except Exception:
            return 0.0

    def poll_ended(self):
        r = self._cmd(["get_property", "eof-reached"])
        return bool(r.get("data"))

    def buffering(self):
        try:
            r = self._cmd(["get_property", "paused-for-cache"])
            if r.get("data"):
                return True
            r = self._cmd(["get_property", "cache-buffering-state"])
            return int(r.get("data") or 0) < 100
        except Exception:
            return False

    def audio_kbps(self):
        try:
            return int(float(self._cmd(["get_property", "audio-bitrate"]) or 0) // 1000)
        except Exception:
            return 0

    def close(self):
        try:
            self._cmd(["quit"])
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass


class FfplayBackend(Backend):
    """ffplay fallback: play/pause (SIGSTOP/SIGCONT), stop, seek via -ss
    restart, best-effort volume flag."""

    name = "ffplay"

    def __init__(self):
        if shutil.which("ffplay") is None:
            raise RuntimeError("ffplay not found - install it with: sudo apt install ffmpeg")
        self.proc = None
        self._source = None
        self._offset = 0.0
        self._t0 = 0.0
        self._paused = False
        self._vol = 80

    def play(self, source, start_at=0, volume=80):
        self.stop()
        self._source = source
        self._offset = float(start_at)
        self._vol = volume
        self._spawn()
        self._paused = False

    def _spawn(self):
        path = self._source.get("filepath") or self._source.get("url")
        self.proc = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
             "-ss", str(self._offset), "-volume", str(self._vol), path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._t0 = time.time()

    def pause_toggle(self):
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            if self._paused:
                self.proc.send_signal(signal.SIGCONT)
                self._t0 = time.time()
            else:
                self._offset = self.pos()
                self.proc.send_signal(signal.SIGSTOP)
            self._paused = not self._paused
        except Exception:
            pass

    def stop(self):
        if self.proc:
            try:
                try:
                    self.proc.send_signal(signal.SIGCONT)
                except Exception:
                    pass
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def seek(self, delta):
        was_paused = self._paused
        target = max(0.0, self.pos() + delta)
        self.stop()
        self._offset = target
        if self._source:
            self._spawn()
            self._paused = was_paused
            if was_paused:
                self.pause_toggle()
                self._paused = True
        return target

    def set_volume(self, vol):
        self._vol = max(0, min(100, vol))  # applies on next seek/play (ffplay limit)

    def pos(self):
        if self._paused or not self.proc or self.proc.poll() is not None:
            return self._offset
        return self._offset + (time.time() - self._t0)

    def dur(self):
        return float((self._source or {}).get("duration") or 0.0)

    def poll_ended(self):
        if self.proc and self.proc.poll() is not None and not self._paused:
            if self.pos() > self._offset + 1.0:
                self.proc = None
                return True
        return False


def auto_backend(prefer=None):
    if prefer == "dummy":
        return DummyBackend()
    if prefer == "mpv" or (prefer is None and shutil.which("mpv")):
        try:
            return MpvBackend()
        except Exception:
            pass
    if prefer == "ffplay" or (prefer is None and shutil.which("ffplay")):
        try:
            return FfplayBackend()
        except Exception:
            pass
    if prefer in (None, "dummy"):
        return DummyBackend()
    raise RuntimeError(
        f"audio backend '{prefer}' unavailable - install one with: sudo apt install mpv")


# ---------------------------------------------------------------- engine
class Player:
    """Queue engine owning shuffle/repeat/sleep-timer/resume/history."""

    def __init__(self, store=None, backend=None, offline=False, cache_dir=None):
        self.store = store
        self.backend = backend or auto_backend()
        self.offline = offline
        self.cache_dir = cache_dir
        self.queue = []          # list of track dicts
        self.index = -1
        self.shuffle = False
        self._order = []         # play order of queue indices when shuffling
        self.repeat = REPEAT_OFF
        self.volume = 80
        self.muted = False
        self._vol_before_mute = 80
        self.show_remaining = False
        self.playing = False
        self.paused = False
        self._play_ts = 0.0
        # sleep timer state
        self.sleep_until = None
        self.sleep_fade = 30     # fade seconds
        self._sleep_start_vol = 80
        self._lock = threading.Lock()
        self._watcher = threading.Thread(target=self._watch, daemon=True)
        self._watcher.start()

    # -- queue --
    def set_queue(self, tracks, start=0):
        self.queue = list(tracks)
        self._order = list(range(len(tracks)))
        if self.shuffle:
            random.shuffle(self._order)
        self.index = max(0, min(start, len(tracks) - 1)) if tracks else -1

    def enqueue(self, track):
        self.queue.append(track)
        self._order.append(len(self.queue) - 1)

    def current(self):
        if 0 <= self.index < len(self.queue):
            return self.queue[self.index]
        return None

    def queue_view(self):
        cur = self._seq_pos()
        names = []
        seq = self._order if self.shuffle else list(range(len(self.queue)))
        for k, qi in enumerate(seq):
            t = self.queue[qi]
            names.append(("> " if k == cur else "  ") + self._label(t))
        return names

    @staticmethod
    def _label(t):
        s = t.get("surah")
        surah = f"Surah {s:03d}" if isinstance(s, int) else str(t.get("title", "?"))
        return f"{t.get('reciter', '?')} - {surah}"

    def _seq_pos(self):
        if self.index < 0:
            return -1
        seq = self._order if self.shuffle else list(range(len(self.queue)))
        try:
            return seq.index(self.index)
        except ValueError:
            return -1

    def toggle_shuffle(self):
        cur = self.current()
        self.shuffle = not self.shuffle
        self._order = list(range(len(self.queue)))
        if self.shuffle:
            random.shuffle(self._order)
        if cur is not None and cur in self.queue:
            self.index = self.queue.index(cur)
        return self.shuffle

    def cycle_repeat(self):
        nxt = {REPEAT_OFF: REPEAT_ONE, REPEAT_ONE: REPEAT_ALL, REPEAT_ALL: REPEAT_OFF}
        self.repeat = nxt[self.repeat]
        return self.repeat

    # -- transport --
    def _resolve(self, track):
        """Pick local file when offline (or preferred), else stream URL.
        Returns (source_dict, via_label). Raises a clean error when neither
        is usable."""
        fp = track.get("filepath")
        have_file = bool(fp and os.path.exists(fp))
        if self.offline:
            if have_file:
                return {"filepath": fp, "duration": track.get("duration")}, "saved file"
            raise RuntimeError(
                f"offline mode: no cached file for {self._label(track)} - "
                f"download it first with `tilawah download`.")
        if have_file and track.get("prefer_local"):
            return {"filepath": fp, "duration": track.get("duration")}, "saved file"
        if track.get("url"):
            return {"url": track["url"], "filepath": fp if have_file else None,
                    "duration": track.get("duration")}, \
                "saved file" if (have_file and track.get("prefer_local")) else "stream"
        if have_file:
            return {"filepath": fp, "duration": track.get("duration")}, "saved file"
        raise RuntimeError(f"no playable source for {self._label(track)}")

    def play_index(self, i):
        if not (0 <= i < len(self.queue)):
            return None
        self.index = i
        t = self.queue[i]
        start_at = 0.0
        if self.store:
            try:
                start_at = self.store.get_position(
                    t.get("reciter", ""), t.get("moshaf", ""), t.get("surah") or 0)
            except Exception:
                start_at = 0.0
        try:
            src, via = self._resolve(t)
        except RuntimeError as e:
            self.playing = False
            return str(e)
        t["_via"] = via
        t["_file"] = (os.path.basename(src.get("filepath")) if src.get("filepath")
                      else src.get("url", "").rstrip("/").split("/")[-1])
        self.backend.play(src, start_at=start_at, volume=0 if self.muted else self.volume)
        self._play_ts = time.time()
        self.playing = True
        self.paused = False
        self._warm_next()
        self._probe_duration(t)
        self._fill_nrg(t, src)
        if self.store:
            try:
                self.store.add_history(t.get("reciter", ""), t.get("moshaf", ""),
                                       t.get("surah") or 0, source="local" if via == "saved file" else "stream")
            except Exception:
                pass
        return None

    def play(self):
        if self.current() is None:
            if self.queue:
                return self.play_index(self._order[0] if self.shuffle else 0)
            return "queue is empty"
        if self.paused:
            self.backend.pause_toggle()
            self.paused = False
            self.playing = True
            return None
        if not self.playing:
            return self.play_index(self.index)
        return None

    def pause_toggle(self):
        if not self.playing:
            return self.play()
        self.backend.pause_toggle()
        self.paused = not self.paused
        return None

    def stop(self):
        self.backend.stop()
        self._save_pos()
        self.playing = False
        self.paused = False
        self.sleep_until = None

    def close(self):
        """Stop playback and kill the backend process (no zombie mpv)."""
        try:
            self.stop()
        except Exception:
            pass
        try:
            self.backend.close()
        except Exception:
            pass

    def _save_pos(self):
        t = self.current()
        if t and self.store:
            try:
                self.store.save_position(t.get("reciter", ""), t.get("moshaf", ""),
                                         t.get("surah") or 0, self.backend.pos())
            except Exception:
                pass

    def next(self, auto=False):
        if not self.queue:
            return
        if self.repeat == REPEAT_ONE and auto:
            self._save_pos()
            self.play_index(self.index)
            return
        seq = self._order if self.shuffle else list(range(len(self.queue)))
        p = self._seq_pos()
        if p < len(seq) - 1:
            self._save_pos()
            self.play_index(seq[p + 1])
        elif self.repeat == REPEAT_ALL and seq:
            self._save_pos()
            self.play_index(seq[0])
        elif auto:
            self._save_pos()
            self.playing = False

    def prev(self):
        if not self.queue:
            return
        try:
            if self.backend.pos() > 5:
                self.backend.seek(-self.backend.pos())
                return
        except Exception:
            pass
        seq = self._order if self.shuffle else list(range(len(self.queue)))
        p = self._seq_pos()
        self._save_pos()
        self.play_index(seq[max(0, p - 1)])

    def restart(self):
        try:
            self.backend.seek(-self.backend.pos())
        except Exception:
            self.play_index(self.index)

    def seek(self, delta):
        try:
            return self.backend.seek(delta)
        except Exception:
            return 0.0

    def set_volume(self, vol):
        self.volume = max(0, min(100, int(vol)))
        try:
            self.backend.set_volume(0 if self.muted else self.volume)
        except Exception:
            pass

    def toggle_mute(self):
        if self.muted:
            self.muted = False
            self.volume = self._vol_before_mute or 80
        else:
            self.muted = True
            self._vol_before_mute = self.volume or 80
        try:
            self.backend.set_volume(0 if self.muted else self.volume)
        except Exception:
            pass
        return self.muted

    def toggle_time_mode(self):
        self.show_remaining = not self.show_remaining
        return self.show_remaining

    def time_text(self):
        """'02:14 / 05:00' or '-02:46 left' when remaining mode is on."""
        try:
            p, d = self.backend.pos(), self.backend.dur()
        except Exception:
            p, d = 0.0, 0.0
        if self.show_remaining and d:
            left = max(0, d - p)
            return f"-{int(left // 60):02d}:{int(left % 60):02d} left"
        total = fmt_dur(d) if d else ("~" + fmt_dur((self.current() or {}).get("duration") or 0)
                                      if (self.current() or {}).get("_approx") else "--:--")
        return f"{fmt_dur(p)} / {total}"

    def describe(self, t=None):
        """Friendly title + file + source, e.g.
        'Mishary Alafasi - Al-Kawthar (108) - 108.mp3 - stream'."""
        t = t or self.current()
        if not t:
            return "nothing playing"
        if t.get("title") and not t.get("surah"):
            name = t["title"]
        else:
            s = by_number(t.get("surah") or 0) or {}
            name = f"{s.get('translit', 'Surah')} ({t.get('surah'):03d})" \
                if isinstance(t.get("surah"), int) else str(t.get("surah"))
        via = t.get("_via") or ("saved file" if t.get("filepath") else "stream")
        fil = t.get("_file") or ""
        return f"{t.get('reciter', '?')} - {name}" + (f"  -  {fil}  -  {via}" if fil else f"  -  {via}")

    def _warm_next(self):
        """Prefetch (HEAD) the next track's URL so gapless switches feel instant."""
        seq = self._order if self.shuffle else list(range(len(self.queue)))
        p = self._seq_pos()
        nxt = None
        if 0 <= p < len(seq) - 1:
            nxt = self.queue[seq[p + 1]]
        elif self.repeat == REPEAT_ALL and seq:
            nxt = self.queue[seq[0]]
        url = (nxt or {}).get("url")
        if url:
            threading.Thread(target=_head, args=(url,), daemon=True).start()

    def _probe_duration(self, track):
        """Fill track['duration'] in the background (ffprobe, else HEAD-size
        estimate flagged approximate) so progress/time works on all backends."""
        if track.get("duration"):
            return
        threading.Thread(target=_probe_worker, args=(track,), daemon=True).start()

    def _fill_nrg(self, track, src):
        """Scan loudness for local files in the background; the TUI pulse
        visualizer follows the real recitation energy."""
        fp = src.get("filepath")
        if not fp or track.get("_nrg"):
            return

        def work():
            try:
                from . import nrg as _nrg
                curve = _nrg.energy_curve(fp, cache_dir=self.cache_dir)
                if curve:
                    track["_nrg"] = curve
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def jump(self, queue_position):
        seq = self._order if self.shuffle else list(range(len(self.queue)))
        if 0 <= queue_position < len(seq):
            self._save_pos()
            self.play_index(seq[queue_position])

    # -- sleep / focus timer --
    def start_sleep(self, minutes, fade=30):
        if minutes is None or float(minutes) <= 0:
            return
        self._sleep_start_vol = self.volume
        self.sleep_until = time.time() + float(minutes) * 60
        self.sleep_fade = max(5, fade)

    def cancel_sleep(self):
        self.sleep_until = None
        if self.volume != self._sleep_start_vol:
            self.set_volume(self._sleep_start_vol)

    def sleep_left(self):
        if not self.sleep_until:
            return 0
        return max(0, self.sleep_until - time.time())

    def _watch(self):
        while True:
            time.sleep(0.5)
            try:
                if self.sleep_until and self.playing:
                    left = self.sleep_until - time.time()
                    if left <= 0:
                        self.backend.stop()
                        self.playing = False
                        self.sleep_until = None
                        self.set_volume(self._sleep_start_vol)
                    elif left < self.sleep_fade:
                        frac = max(0.0, left / self.sleep_fade)
                        self.backend.set_volume(int(self._sleep_start_vol * frac))
                if self.playing and not self.paused and self.backend.poll_ended():
                    if time.time() - self._play_ts > 2.5:  # grace: mpv flags eof right at load
                        self.next(auto=True)
            except KeyboardInterrupt:
                return
            except Exception:
                pass  # transient backend hiccup: keep watching


# ---------------------------------------------------------------- helpers
def fmt_dur(sec):
    sec = max(0, int(sec or 0))
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _head(url, timeout=10):
    """Warm a stream URL (CDN/prefetch). Returns Content-Length or 0."""
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "Tilawah/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return int(fh.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def _probe_worker(track):
    """Fill track['duration']: ffprobe when present, else HEAD-size estimate
    at ~40kbps flagged approximate (mp3quran murattal-style encodes)."""
    url = track.get("url")
    if not url:
        return
    if shutil.which("ffprobe"):
        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", url],
                capture_output=True, text=True, timeout=12)
            dur = float((proc.stdout or "").strip())
            if dur > 0:
                track["duration"] = dur
                track["_approx"] = False
                return
        except Exception:
            pass
    size = _head(url)
    if size > 0:
        track["duration"] = size * 8 / 40000.0
        track["_approx"] = True
