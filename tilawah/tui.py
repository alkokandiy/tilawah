"""Curses TUI: friendly, keyboard-only, single binary, no daemon.

Panels: Now Playing | Reciters (Top 20) | My Shelf | Queue.
Footer always shows the keys that matter here; `?` shows everything.

  Space play/pause   n/p next/prev    0 restart        m mute   -/= volume
  L/R seek +/-10s (Now) - move lists elsewhere - U/D volume (Now) - move (lists)
  Tab panels   Enter play   / find reciter   C all 242 reciters   w narration
  z shuffle  e repeat  R elapsed/remaining  A animation
  f favorite  F favorites  H history (F/H again to go back)
  d save surah  a save reciter  x cancel saving  D refresh YouTube shelf
  t sleep timer (1/2/3 = 15/30/60 min)  T cancel timer
  g theme  v fullscreen  o move box  ? help  q quit

Reduced motion: `reduced_motion=true` (or --calm) renders one static frame
at ~2fps - for slow terminals and SSH links.
"""

try:
    import curses
except ImportError:  # Windows without windows-curses: stub keeps the CLI,
    # tests and non-TUI commands importable. The TUI itself refuses to run
    # with a clear install hint (see cli.cmd_tui).
    class _CursesFallback:
        error = Exception
        A_NORMAL = 0
        KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = 259, 258, 260, 261
        KEY_BACKSPACE = 263

        def __getattr__(self, _name):
            def _missing(*_a, **_k):
                raise RuntimeError("curses is unavailable on this machine")
            return _missing

    curses = _CursesFallback()
import os
import threading
import time

from . import api as api_mod
from . import art, deps as deps_mod, downloader, themes
from . import __version__ as APP_VERSION
from .surahs import SURAHS, by_number

KEYMAP_DOC = [
    ("Space", "play / pause"), ("n / p", "next / previous track"),
    ("0", "restart track"), ("m", "mute"), ("- / =", "volume"),
    ("Arrows / hjkl / WASD", "move + seek + volume (see footer)"),
    ("1 2 3 4", "jump to Now / Reciters / Shelf / Queue"),
    ("Tab", "next panel"), ("Enter", "play selected"),
    ("Esc", "back to Now Playing"),
    ("/", "find reciter"), ("C", "Top picks <-> all reciters"),
    ("w", "switch narration"), ("z", "shuffle"), ("e", "repeat"),
    ("R", "elapsed <-> remaining"), ("A", "animation style"),
    ("f", "favorite this track"), ("F / H", "favorites / history"),
    ("d", "save this surah"), ("a", "save whole reciter"),
    ("D", "save center: surah/reciter/Juz 30/all"),
    ("Y", "fetch shelf tracks to this device"),
    ("u", "paste a link, fetch its audio to the shelf"),
    ("x", "cancel saving"), ("t / T", "sleep timer set / cancel"),
    ("g", "theme"), ("v", "fullscreen"), ("o", "move player box"),
    ("?", "this help"), ("q", "quit"),
]

HINTS = {
    0: "Space play - n next - L/R seek - U/D vol - m mute - D save - ? keys",
    1: "1-4 panels - move: arrows/hjkl/WASD - Enter play - / find - d save 1 - ? keys",
    2: "Enter play - Y fetch tracks - D save - 1-4 panels - ? keys",
    3: "Enter jump - z shuffle - e repeat - 1-4 panels - ? keys",
}


def progress_bar(frac, width):
    frac = min(1.0, max(0.0, frac or 0.0))
    fill = int(width * frac)
    return "[" + "#" * fill + "-" * (width - fill) + "]"


def vol_bar(vol, width=10):
    fill = int(width * max(0, min(100, vol)) / 100)
    return "[" + "|" * fill + " " * (width - fill) + "]"


class App:
    def __init__(self, store, cfg, player, reciters, cache_dir, status_msg="",
                 refresh=True):
        self.store = store
        self.cfg = cfg
        self.player = player
        self.reciters = reciters or []
        self.cache_dir = str(cache_dir)
        self.theme_name = cfg.get("theme", "night")
        self.anim = cfg.get("anim", "orbit")
        if self.anim not in art.ANIMS:
            self.anim = "orbit"
        self.show_all = bool(cfg.get("show_all_reciters", False))
        self.panel = 0
        self.panels = ["Now Playing", "Reciters", "My Shelf", "Queue"]
        self.fullscreen = False
        self.move_mode = False
        self.box = [2, 2]
        self.rec_sel = 0
        self.sur_sel = 0
        self.col = 0  # 0 reciters, 1 surahs
        self.shelf_sel = 0
        self.q_sel = 0
        self.moshaf_idx = {}  # reciter name -> moshaf index
        self.filter = ""
        self.mode = "browse"  # browse | search | sleep | download | fetch | url
        self.buf = ""
        self.msg = status_msg
        self.msg_until = time.time() + 4 if status_msg else 0
        self.t0 = time.time()
        self.pairs = {}
        self.show_help = False
        self.list_view = "reciters"  # reciters | favs | hist
        self.favs = []
        self.hist = []
        self.shelf = []
        self.dl = None  # background download job dict
        self.dl_opts = []
        self.dl_title = ""
        self.dl_confirm = False
        self._dl_pending = []
        self.fetch = None  # blocking fetch-before-play overlay job
        self._pending = None  # {"queue": True} - what to play when fetch lands
        self.shelf_job = None
        self._bg_thread = None
        self._needs_paint = True
        self.refresh_shelf()
        player.on_track_request = self._gate
        player.on_track_ended_early = self._blip
        if not self.shelf and not status_msg:
            self.say("Shelf empty on this device - press Y to fetch your tracks", 8)
        if refresh:
            self._bg_thread = threading.Thread(target=self._bg_refresh, daemon=True)
            self._bg_thread.start()

    def close(self):
        """Join the background refresh so no thread touches SQLite or the
        network during interpreter teardown (that segfaults on exit)."""
        t = self._bg_thread
        self._bg_thread = None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=10)

    # ---------------------------------------------------------- data
    def refresh_shelf(self):
        try:
            self.shelf = self.store.get_playlist()
        except Exception:
            self.shelf = []

    def _bg_refresh(self):
        """Refresh the catalog quietly after launch so startup is instant.

        Retries every minute until it succeeds (fresh offline devices pick
        the list up by themselves once connected).
        """
        while True:
            try:
                reciters = api_mod.fetch_reciters()
                if reciters:
                    self.store.save_reciters(reciters)
                    try:
                        self.store.save_suwar(api_mod.fetch_suwar())
                    except Exception:
                        pass
                    if not self.reciters:
                        self.say("reciter list loaded - pick one, Enter plays", 6)
                    else:
                        self.say("reciter list updated")
                    self.reciters = reciters
                    return
            except Exception:
                pass
            time.sleep(60)

    def visible_reciters(self):
        top, rest = api_mod.curate(self.reciters)
        pool = self.reciters if self.show_all else (top or self.reciters)
        if not self.filter:
            return pool
        q = self.filter.lower()
        return [r for r in pool if q in r["name"].lower() or q == str(r["id"])]

    def current_moshaf(self, rs=None):
        rs = self.visible_reciters() if rs is None else rs
        if not rs:
            return None, None, 0
        r = rs[min(self.rec_sel, len(rs) - 1)]
        ms = r.get("moshaf", [])
        if not ms:
            return r, None, 0
        idx = self.moshaf_idx.get(r["name"], api_mod.preferred_moshaf_index(r))
        idx = max(0, min(idx, len(ms) - 1))
        return r, ms[idx], idx

    def surah_numbers(self, rs=None):
        r, m, _ = self.current_moshaf(rs)
        if m:
            try:
                return api_mod.available_surahs(m)
            except Exception:
                pass
        return [n for n, *_ in SURAHS]

    def surah_name(self, n):
        s = by_number(n)
        return s["translit"] if s else f"Surah {n}"

    # ---------------------------------------------------------- actions
    def say(self, text, secs=4):
        self.msg = text
        self.msg_until = time.time() + secs

    def make_track(self, reciter_name, moshaf_name, surah, url, local_path="", server=""):
        import os
        fp = local_path
        if not fp:
            try:
                cand = str(downloader._local_name(
                    self.cfg.get("download_dir", "~/Tilawah"), reciter_name, surah))
                fp = cand if os.path.exists(cand) else ""
            except Exception:
                fp = ""
        return {"reciter": reciter_name, "moshaf": moshaf_name, "surah": surah,
                "url": url, "filepath": fp, "_server": server,
                "prefer_local": bool(self.cfg.get("offline"))}

    # -- download-before-play gate --
    def _play_mode(self):
        return "stream" if str(self.cfg.get("play_mode", "download")).lower() == "stream" else "download"

    def _track_file(self, t):
        try:
            s = t.get("surah")
            if not isinstance(s, int) or not t.get("reciter"):
                return ""
            return str(downloader._local_name(
                self.cfg.get("download_dir", "~/Tilawah"), t["reciter"], s))
        except Exception:
            return ""

    def _is_saved(self, t):
        fp = t.get("filepath") or self._track_file(t)
        return bool(fp) and downloader.already_cached(fp)

    def _needs_fetch(self, t):
        return (self._play_mode() == "download" and bool(t.get("url"))
                and isinstance(t.get("surah"), int) and not self._is_saved(t))

    def _gate(self, t):
        """Player hook: True plays now; False holds for the fetch overlay."""
        if not self._needs_fetch(t):
            return True
        self._fetch_one(t)
        return False

    def _blip(self, track, pos):
        label = track.get("title") or f"surah {track.get('surah')}"
        self.say(f"stopped {pos:.0f}s in ({label}) - file may be broken, D re-saves it", 6)

    def _fetch_one(self, t):
        if self.fetch and self.fetch.get("running"):
            self.say("already fetching - x cancels")
            return
        s = t.get("surah")
        job = {"label": f"{t.get('reciter', '?')} - surah {s:03d}",
               "running": True, "cancel": False, "ok": False, "error": "",
               "bytes": 0, "total_bytes": 0, "rate": 0.0,
               "t0": time.time(), "cur": f"{s:03d}.mp3"}
        self.fetch = job
        self._pending = {"queue": True}
        self.mode = "fetch"
        threading.Thread(target=self._fetch_worker, args=(job, t), daemon=True).start()

    def _fetch_worker(self, job, t):
        dd = self.cfg.get("download_dir", "~/Tilawah")
        try:
            server = t.get("_server") or (t["url"].rsplit("/", 1)[0] + "/")
            last = [0, time.time()]

            def cb(d, total):
                if job.get("cancel"):
                    raise downloader.Cancelled("cancelled")
                now = time.time()
                dt = max(0.2, now - last[1])
                inst = (d - last[0]) / dt
                job["rate"] = 0.7 * job["rate"] + 0.3 * inst
                last[0], last[1] = d, now
                job["bytes"] = d
                job["total_bytes"] = total

            downloader.download_surah(server, t["reciter"], t["surah"], dd, progress=cb)
            job["ok"] = True
        except downloader.Cancelled:
            job["cancel"] = True
        except Exception as e:
            job["error"] = str(e) or "network error"
        finally:
            job["running"] = False

    def _poll_fetch(self):
        job = self.fetch
        if not job or job.get("running"):
            return
        self.fetch = None
        pend, self._pending = self._pending, None
        if self.mode == "fetch":
            self.mode = "browse"
        if job.get("cancel"):
            self.say("fetch stopped - file stays cached for next time", 5)
            return
        if not job.get("ok"):
            self.say(f"fetch failed ({job.get('error')}) - press Enter to retry", 6)
            return
        if pend and pend.get("queue"):
            err = self.player.play_index(self.player.index)
            if err and err != "held":
                self.say(err, 6)

    # -- shelf fetch (Y): tracks ship with the tool via built-in playlist --
    def _shelf_fetch(self):
        if self.shelf_job and self.shelf_job.get("running"):
            self.say("shelf fetch already running - x stops it")
            return
        ok, hint = deps_mod.yt_dlp()
        if not ok:
            self.say(hint, 6)
            return
        job = {"running": True, "stop": threading.Event(), "done": 0,
               "total": 0, "pct": 0.0, "title": "", "error": ""}
        self.shelf_job = job
        self.say("fetching your shelf tracks - x stops", 5)
        threading.Thread(target=self._shelf_worker, args=(job,), daemon=True).start()

    def _add_link(self, url):
        """Paste-a-link: fetch one audio into the shelf folder."""
        url = (url or "").strip()
        self.mode = "browse"
        if not url:
            return
        if self.shelf_job and self.shelf_job.get("running"):
            self.say("already fetching - x stops it")
            return
        ok, hint = deps_mod.yt_dlp()
        if not ok:
            self.say(hint, 6)
            return
        job = {"running": True, "stop": threading.Event(), "done": 0,
               "total": 1, "pct": 0.0, "title": url, "error": ""}
        self.shelf_job = job
        self.say("fetching link audio - x stops", 5)
        threading.Thread(target=self._add_link_worker, args=(job, url),
                         daemon=True).start()

    def _add_link_worker(self, job, url):
        from . import ytpl

        def prog(n, title):
            job["done"] = n
            job["title"] = title

        def fprog(pct, _label):
            job["pct"] = pct

        try:
            ytpl.ingest(url, self.cfg.get("download_dir", "~/Tilawah"),
                        store=self.store, max_items=1, single=True,
                        progress=prog, file_progress=fprog, stop=job["stop"])
        except Exception as e:
            job["error"] = str(e) or "network error"
        finally:
            job["running"] = False
            try:
                self.refresh_shelf()
            except Exception:
                pass

    def _shelf_worker(self, job):
        from . import ytpl
        url = (self.cfg.get("youtube_playlist_url") or "").strip() or ytpl.DEFAULT_PLAYLIST_URL
        try:
            try:
                job["total"] = len(ytpl.list_entries(url))
            except Exception:
                pass
            if job["stop"].is_set():
                return

            def prog(n, title):
                job["done"] = n
                job["title"] = title

            def fprog(pct, _label):
                job["pct"] = pct

            ytpl.ingest(url, self.cfg.get("download_dir", "~/Tilawah"),
                        store=self.store, max_items=40,
                        progress=prog, file_progress=fprog, stop=job["stop"])
        except Exception as e:
            job["error"] = str(e) or "network error"
        finally:
            job["running"] = False
            try:
                self.refresh_shelf()
            except Exception:
                pass

    def _poll_shelf(self):
        job = self.shelf_job
        if not job or job.get("running"):
            return
        self.shelf_job = None
        n = len(self.shelf)
        try:
            stopped = job.get("stop").is_set() if job.get("stop") else False
        except Exception:
            stopped = False
        if stopped and job.get("total") and job.get("done", 0) < job["total"]:
            self.say(f"shelf fetch stopped - {n} tracks kept", 6)
        elif job.get("error") and not n:
            self.say(f"shelf fetch had trouble ({job['error']})", 6)
        else:
            self.say(f"shelf ready: {n} tracks live here now", 6)

    def _shelf_size(self):
        total = 0
        for t in self.shelf:
            try:
                fp = t.get("filepath", "")
                if fp and os.path.exists(fp):
                    total += os.path.getsize(fp)
            except OSError:
                pass
        return total

    def _play_tracks(self, tracks, start):
        # Fresh queue: always (re)start via play_index. Player.play() is only
        # for pause/resume - it deliberately no-ops while audio runs, which
        # used to swallow every reciter->shelf switch silently.
        self.player.set_queue(tracks, start=start)
        resumed = 0
        try:
            t = tracks[start]
            resumed = self.store.get_position(t.get("reciter", ""), t.get("moshaf", ""),
                                              t.get("surah") or 0)
        except Exception:
            pass
        err = self.player.play_index(self.player.index)
        if err == "held":
            return  # fetch overlay took over; it plays on completion
        if err:
            self.say(err, 6)
        elif resumed and resumed > 5:
            m, s = int(resumed // 60), int(resumed % 60)
            self.say(f"resumed at {m:02d}:{s:02d}  (0 = restart)")
        else:
            self.say("playing - Space pauses, ? shows keys")
        self._maybe_viz_tip(tracks[start] if 0 <= start < len(tracks) else None)

    def _maybe_viz_tip(self, track):
        """One tip per session: local files deserve ffmpeg's richer visuals."""
        if getattr(self, "_viz_warned", False) or not track:
            return
        fp = track.get("filepath") or ""
        import os as _os
        if not (fp and _os.path.exists(fp)):
            return
        import shutil as _sh
        if _sh.which("ffmpeg") or _sh.which("ffprobe"):
            return
        self._viz_warned = True
        _ok, hint = deps_mod.ffmpeg()
        self.say("richer visuals need ffmpeg - " + (hint or "install ffmpeg"), 6)

    def play_selection(self):
        r, m, _ = self.current_moshaf()
        if not r or not m:
            if not self.visible_reciters():
                self.say("no reciters yet - connect once so the list can load", 6)
            else:
                self.say("this reciter has no audio")
            return
        nums = self.surah_numbers()
        if not nums:
            return
        s = nums[min(self.sur_sel, len(nums) - 1)]
        tracks = [self.make_track(r["name"], m.get("name", ""), n,
                                  api_mod.audio_url(m["server"], n),
                                  server=m["server"]) for n in nums]
        self._play_tracks(tracks, nums.index(s))

    def play_fav_hist(self, entry):
        r = api_mod.find_reciter(self.reciters, entry.get("reciter", ""))
        if not r or not r.get("moshaf"):
            self.say("reciter no longer in catalog")
            return
        idx = api_mod.preferred_moshaf_index(r)
        m = r["moshaf"][idx]
        surah = entry.get("surah") or 0
        nums = api_mod.available_surahs(m)
        if surah not in nums:
            nums = [surah] + nums
        tracks = [self.make_track(r["name"], m.get("name", ""), n,
                                  api_mod.audio_url(m["server"], n),
                                  server=m["server"]) for n in nums]
        self._play_tracks(tracks, nums.index(surah))

    def _cached_count(self, items):
        dd = self.cfg.get("download_dir", "~/Tilawah")
        n = 0
        for (reciter, server, s) in items:
            try:
                if downloader.already_cached(
                        downloader._local_name(dd, reciter, s)):
                    n += 1
            except Exception:
                pass
        return n

    def _dl_enqueue(self, items, label):
        """Queue (reciter, server, surah) items as a background job.

        Files already saved are skipped exactly once - saving is idempotent,
        so re-running never re-fetches ("required one time" by design).
        """
        if self.dl and self.dl.get("running"):
            self.say("already saving - x cancels")
            return
        items = list(items)
        if not items:
            self.say("nothing to save")
            return
        have = self._cached_count(items)
        if have >= len(items):
            self.say("already saved - nothing to fetch")
            return
        job = {"label": label, "done": 0, "total": len(items),
               "have": have, "running": True, "cancel": False,
               "cur": "", "frac": 0.0}
        self.dl = job
        threading.Thread(target=self._dl_worker, args=(job, items),
                         daemon=True).start()
        self.say(f"saving {len(items) - have} new file(s)"
                 + (f" ({have} already saved)" if have else "") + " - x cancels")

    def _dl_worker(self, job, items):
        dd = self.cfg.get("download_dir", "~/Tilawah")
        for (reciter, server, s) in items:
            if job["cancel"]:
                break
            dest = downloader._local_name(dd, reciter, s)
            if downloader.already_cached(dest):
                job["done"] += 1
                continue
            job["cur"] = f"{s:03d}.mp3"
            job["frac"] = 0.0

            def cb(d, t, job=job):
                job["frac"] = (d / t) if t else 0.0

            try:
                downloader.download_surah(server, reciter, s, dd, progress=cb)
            except Exception:
                pass
            job["done"] += 1
            job["frac"] = 0.0
            job["cur"] = ""
        job["running"] = False
        if not job["cancel"]:
            self.say(f"saved {job['label']} - find it offline from now on", 6)

    # -- save center (D) --
    def _dl_context(self):
        """(reciter, moshaf, surah_numbers) for the download dialog."""
        if self.panel == 1 and self.list_view == "reciters":
            r, m, _ = self.current_moshaf()
            if r and m:
                return r, m, self.surah_numbers()
        t = self.player.current()
        if t and t.get("reciter"):
            r = api_mod.find_reciter(self.reciters, t["reciter"])
            if r and r.get("moshaf"):
                idx = self.moshaf_idx.get(r["name"], api_mod.preferred_moshaf_index(r))
                m = r["moshaf"][min(idx, len(r["moshaf"]) - 1)]
                return r, m, api_mod.available_surahs(m)
        return None, None, []

    def _dl_open(self):
        r, m, nums = self._dl_context()
        if not r or not m:
            self.say("pick a reciter first (panel 2)")
            return
        cur_surahs = []
        t = self.player.current()
        if self.panel == 1 and nums:
            cur_surahs = [nums[min(self.sur_sel, len(nums) - 1)]]
        elif t and isinstance(t.get("surah"), int):
            cur_surahs = [t["surah"]]
        j30 = [n for n in nums if n in api_mod.JUZ30]
        top, _ = api_mod.curate(self.reciters)
        all_n = sum(len(api_mod.available_surahs(
            rr["moshaf"][api_mod.preferred_moshaf_index(rr)]))
            for rr in top if rr.get("moshaf"))
        self.dl_opts = [
            ("1", f"this surah ({cur_surahs[0]:03d})" if cur_surahs else "this surah",
             [(r["name"], m["server"], s) for s in cur_surahs]),
            ("2", f"whole {r['name']} ({len(nums)} surahs)",
             [(r["name"], m["server"], s) for s in nums]),
            ("3", f"Juz 30 of {r['name']} ({len(j30)} surahs)",
             [(r["name"], m["server"], s) for s in j30]),
            ("4", f"ALL top picks ({all_n} files - big!)", None),
        ]
        self.dl_title = r["name"]
        self.dl_confirm = False
        self.mode = "download"

    def _dl_all_items(self):
        top, _ = api_mod.curate(self.reciters)
        items = []
        for rr in top:
            if not rr.get("moshaf"):
                continue
            mm = rr["moshaf"][api_mod.preferred_moshaf_index(rr)]
            items += [(rr["name"], mm["server"], s)
                      for s in api_mod.available_surahs(mm)]
        return items

    def _dl_choose(self, key):
        if key == "4":
            if not self.dl_confirm:
                items = self._dl_all_items()
                self.dl_confirm = True
                self._dl_pending = items
                self.say(f"{len(items)} files - press 4 again to start, Esc backs out", 6)
                return
            items = self._dl_pending
            self.mode = "browse"
            self.dl_confirm = False
            self._dl_enqueue(items, "all top picks")
            return
        self.dl_confirm = False
        for k, _label, items in self.dl_opts:
            if k == key and items:
                self.mode = "browse"
                self._dl_enqueue(items, _label)
                return

    # ---------------------------------------------------------- curses setup
    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(80)
        try:
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
        except Exception:
            pass
        self._init_colors()
        self._splash(stdscr)
        calm = bool(self.cfg.get("reduced_motion"))
        fps = 2 if calm else int(self.cfg.get("fps", 12) or 12)
        last = 0.0
        static_done = False
        while True:
            now = time.time()
            ch = stdscr.getch()
            if ch != -1:
                if self._key(ch) == "quit":
                    if self.dl and self.dl.get("running"):
                        self.dl["cancel"] = True
                    try:
                        self.player.stop()
                    except Exception:
                        pass
                    self.cfg["anim"] = self.anim
                    self.cfg["show_all_reciters"] = self.show_all
                    try:
                        from . import config as cfg_mod
                        cfg_mod.save(self.cfg)
                    except Exception:
                        pass
                    return
                self._needs_paint = True
                static_done = False
            if calm:
                if not static_done or self._needs_paint:
                    self._paint(stdscr, static_t=3.0)
                    static_done = True
                    self._needs_paint = False
                time.sleep(0.1)
            elif now - last > 1.0 / max(1, fps) or self._needs_paint:
                self._paint(stdscr)
                last = now
                self._needs_paint = False

    def _init_colors(self):
        try:
            order = ["border", "title", "accent", "text", "dim", "highlight",
                     "progress_fill", "error", "ok"]
            for i, role in enumerate(order, start=1):
                fg = themes.CURSES_COLOR.get(
                    themes.get(self.theme_name).get(role, "white"), 7)
                curses.init_pair(i, fg, -1)
                self.pairs[role] = curses.color_pair(i)
        except Exception:
            pass

    def C(self, role):
        return self.pairs.get(role, curses.A_NORMAL)

    def _frame(self, stdscr, y, x, bw, bh, title=""):
        try:
            stdscr.addstr(y, x, art.dtop(bw)[:bw], self.C("border"))
            if title:
                stdscr.addstr(y, x + 2, f" {title} "[:bw - 4], self.C("title"))
            stdscr.addstr(y + bh - 1, x, art.dbot(bw)[:bw], self.C("border"))
        except curses.error:
            pass

    def _frow(self, stdscr, y, x, bw, txt, attr=None):
        try:
            stdscr.addstr(y, x, art.DB_V + txt.ljust(bw - 2)[:bw - 2] + art.DB_V,
                          attr if attr is not None else self.C("text"))
        except curses.error:
            pass

    def _splash(self, stdscr):
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        lines = art.splash_classic(min(64, w - 2), APP_VERSION)
        y = max(0, h // 2 - len(lines) // 2)
        for ln in lines:
            try:
                stdscr.addstr(y, max(0, (w - len(ln)) // 2), ln[:w - 1], self.C("title"))
            except curses.error:
                pass
            y += 1
        stdscr.refresh()
        # Wait for a keypress - no automatic skip. The user reads the
        # opening for as long as they want.
        stdscr.timeout(-1)
        stdscr.getch()
        stdscr.timeout(80)

    # ---------------------------------------------------------- input
    def _key(self, ch):
        if self.move_mode:
            if ch in (ord("o"), 10, 13, 27):
                self.move_mode = False
            elif ch == curses.KEY_UP:
                self.box[0] = max(0, self.box[0] - 1)
            elif ch == curses.KEY_DOWN:
                self.box[0] += 1
            elif ch == curses.KEY_LEFT:
                self.box[1] = max(0, self.box[1] - 1)
            elif ch == curses.KEY_RIGHT:
                self.box[1] += 1
            return None
        if self.mode == "search":
            if ch in (27, 10, 13):
                self.mode = "browse"
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.filter = self.filter[:-1]
                self.rec_sel = 0
            elif 32 <= ch < 127:
                self.filter += chr(ch)
                self.rec_sel = 0
            return None
        if self.mode == "sleep":
            if ch == 27:
                self.mode = "browse"
            elif ch == ord("1"):
                self._set_sleep(15)
            elif ch == ord("2"):
                self._set_sleep(30)
            elif ch == ord("3"):
                self._set_sleep(60)
            elif ch in (10, 13):
                try:
                    self._set_sleep(int(self.buf or self.cfg.get("sleep_timer_minutes", 30)))
                except ValueError:
                    self.say("type minutes as a number")
                    self.mode = "browse"
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.buf = self.buf[:-1]
            elif 48 <= ch <= 57:
                self.buf += chr(ch)
            return None
        if self.mode == "download":
            if ch == 27:
                self.mode = "browse"
                self.dl_confirm = False
            elif ch in (ord("1"), ord("2"), ord("3"), ord("4")):
                self._dl_choose(chr(ch))
            elif ch == ord("x"):
                if self.dl and self.dl.get("running"):
                    self.dl["cancel"] = True
                    self.say("saving cancelled")
                self.mode = "browse"
            return None
        if self.mode == "fetch":
            if ch in (27, ord("x")):
                if self.fetch and self.fetch.get("running"):
                    self.fetch["cancel"] = True
                self.mode = "browse"
                self.say("fetch cancelled")
            return None
        if self.mode == "url":
            if ch == 27:
                self.mode = "browse"
            elif ch in (10, 13):
                self._add_link(self.buf)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.buf = self.buf[:-1]
            elif 32 <= ch < 127:
                self.buf += chr(ch)
            return None
        # global keys
        if ch == ord("q"):
            if self.show_help or self.mode != "browse" or self.filter:
                self.show_help = False
                self.filter = ""
                return None
            return "quit"
        if ch == 27:
            if self.show_help or self.mode != "browse":
                self.show_help = False
                self.mode = "browse"
            elif self.filter:
                self.filter = ""
            elif self.list_view != "reciters":
                self.list_view = "reciters"
            else:
                self.panel = 0  # Esc always finds the way back to Now Playing
            return None
        if ch == ord("?"):
            self.show_help = not self.show_help
            return None
        if ch == ord("m"):
            self.say("muted" if self.player.toggle_mute() else f"volume {self.player.volume}")
            return None
        if ch in (ord("-"), ord("_")):
            self.player.set_volume(self.player.volume - 5)
            self.say(f"volume {self.player.volume}")
            return None
        if ch in (ord("="), ord("+")):
            self.player.set_volume(self.player.volume + 5)
            self.say(f"volume {self.player.volume}")
            return None
        if ch == ord("R"):
            self.say("showing time left" if self.player.toggle_time_mode() else "showing elapsed")
            return None
        if ch == ord("A"):
            i = art.ANIMS.index(self.anim)
            self.anim = art.ANIMS[(i + 1) % len(art.ANIMS)]
            self.say(f"animation: {self.anim}")
            return None
        if ch == ord("\t") or ch == 9:
            self.panel = (self.panel + 1) % len(self.panels)
            return None
        if ch == ord(" "):
            err = self.player.pause_toggle()
            self.say(err or ("paused" if self.player.paused else "playing"))
            return None
        if ch == ord("s") and (self.panel == 0 or self.fullscreen):
            self.player.stop()
            self.say("stopped")
            return None
        if ch == ord("n"):
            self.player.next()
            return None
        if ch == ord("p"):
            self.player.prev()
            return None
        if ch == ord("0"):
            self.player.restart()
            self.say("restarted")
            return None
        if ch == ord("z"):
            self.say("shuffle on" if self.player.toggle_shuffle() else "shuffle off")
            return None
        if ch == ord("e"):
            self.say(f"repeat: {self.player.cycle_repeat()}")
            return None
        if ch == ord("g"):
            order = themes.names()
            self.theme_name = order[(order.index(self.theme_name) + 1) % len(order)]
            self._init_colors()
            self.say(f"theme: {self.theme_name}")
            return None
        if ch == ord("v"):
            self.fullscreen = not self.fullscreen
            return None
        if ch == ord("o") and not self.fullscreen and self.panel == 0:
            self.move_mode = True
            self.say("move: arrows reposition, Enter done")
            return None
        if ch == ord("t"):
            self.mode = "sleep"
            self.buf = ""
            return None
        if ch == ord("T"):
            self.player.cancel_sleep()
            self.say("sleep timer off")
            return None
        if ch == ord("f"):
            t = self.player.current()
            if t and t.get("surah"):
                on = self.store.toggle_favorite(t["reciter"], t["moshaf"], t["surah"])
                self.say("* saved to favorites" if on else "removed from favorites")
            else:
                self.say("play something first, then press f")
            return None
        if ch == ord("F"):
            if self.list_view == "favs":
                self.list_view = "reciters"
            else:
                self.list_view = "favs"
                self.favs = self.store.get_favorites()
                self.panel = 1
            return None
        if ch == ord("H"):
            if self.list_view == "hist":
                self.list_view = "reciters"
            else:
                self.list_view = "hist"
                self.hist = self.store.get_history(50)
                self.panel = 1
            return None
        if ch == ord("/"):
            self.panel = 1
            self.list_view = "reciters"
            self.mode = "search"
            self.filter = ""
            self.rec_sel = 0
            return None
        if ch == ord("C"):
            self.show_all = not self.show_all
            self.rec_sel = 0
            self.say("all reciters" if self.show_all else "Top 20 reciters")
            return None
        if ch == ord("w") and self.panel == 1:
            r, m, idx = self.current_moshaf()
            if r and len(r.get("moshaf", [])) > 1:
                self.moshaf_idx[r["name"]] = (idx + 1) % len(r["moshaf"])
                self.sur_sel = 0
                self.say(r["moshaf"][self.moshaf_idx[r["name"]]].get("name", ""))
            else:
                self.say("only one narration for this reciter")
            return None
        if ch == ord("d") and self.panel == 1 and self.list_view == "reciters":
            r, m, _ = self.current_moshaf()
            if r and m:
                nums = self.surah_numbers()
                s = nums[min(self.sur_sel, len(nums) - 1)]
                self._dl_enqueue([(r["name"], m["server"], s)],
                                 f"{r['name']} surah {s:03d}")
            else:
                self.say("this reciter has no audio")
            return None
        if ch == ord("a") and self.panel in (0, 1):
            r, m, nums = self._dl_context()
            if r and m:
                self._dl_enqueue([(r["name"], m["server"], s) for s in nums],
                                 f"whole {r['name']}")
            else:
                self.say("pick a reciter first (panel 2)")
            return None
        if ch == ord("x"):
            if self.fetch and self.fetch.get("running"):
                self.fetch["cancel"] = True
                self.mode = "browse"
                self.say("fetch cancelled")
            elif self.shelf_job and self.shelf_job.get("running"):
                try:
                    self.shelf_job["stop"].set()
                except Exception:
                    pass
                self.say("shelf fetch stopping...")
            elif self.dl and self.dl.get("running"):
                self.dl["cancel"] = True
                self.say("saving cancelled")
            return None
        if ch == ord("D"):
            self._dl_open()
            return None
        if ch == ord("Y"):
            self._shelf_fetch()
            return None
        if ch == ord("u"):
            self.mode = "url"
            self.buf = ""
            return None
        if ch in (ord("1"), ord("2"), ord("3"), ord("4")):
            self.panel = ch - ord("1")
            self.show_help = False
            return None
        # movement: arrows, vim hjkl and WASD mirror each other.
        # Up/k/w = up (or louder), Down/j/s = down (or quieter) in lists;
        # 'd' saves in Reciters (handled above), 's' stops in Now/fullscreen.
        if ch in (curses.KEY_LEFT, ord("h"), ord("a")):
            return self._move_h(-1)
        if ch in (curses.KEY_RIGHT, ord("l"), ord("d")):
            return self._move_h(+1)
        if ch in (curses.KEY_UP, ord("k"), ord("w")):
            return self._move_v(-1)
        if ch in (curses.KEY_DOWN, ord("j"), ord("s")):
            return self._move_v(+1)
        if ch in (10, 13):
            return self._enter()
        return None

    def _set_sleep(self, mins):
        self.player.start_sleep(mins)
        self.say(f"sleep in {mins} min - fades out gently (T cancels)")
        self.mode = "browse"

    def _move_h(self, dx):
        """Horizontal: seek in Now/fullscreen, switch list column in Reciters."""
        if self.fullscreen or self.panel == 0:
            self.player.seek(10 * dx)
        elif self.panel == 1 and self.list_view == "reciters":
            self.col = max(0, min(1, self.col + dx))
        return None

    def _move_v(self, dy):
        """Vertical (+1 = down, -1 = up): volume in Now/fullscreen, cursor in lists.

        Up (k/w/Up) is louder, Down (j/s/Down) is quieter - the old build had
        this backwards.
        """
        if self.fullscreen or self.panel == 0:
            self.player.set_volume(self.player.volume - 5 * dy)
            self.say(f"volume {self.player.volume}")
        elif self.panel == 1:
            if self.list_view == "reciters":
                if self.col == 0:
                    self.rec_sel = max(0, self.rec_sel + dy)
                    self.sur_sel = 0
                else:
                    self.sur_sel = max(0, self.sur_sel + dy)
            else:
                self.sur_sel = max(0, self.sur_sel + dy)
        elif self.panel == 2:
            self.shelf_sel = max(0, self.shelf_sel + dy)
        elif self.panel == 3:
            self.q_sel = max(0, self.q_sel + dy)
        return None

    def _enter(self):
        if self.panel == 1:
            if self.list_view == "reciters":
                self.play_selection()
            elif self.list_view == "favs" and self.favs:
                self.play_fav_hist(self.favs[min(self.sur_sel, len(self.favs) - 1)])
            elif self.list_view == "hist" and self.hist:
                self.play_fav_hist(self.hist[min(self.sur_sel, len(self.hist) - 1)])
        elif self.panel == 3 and self.player.queue:
            self.player.jump(self.q_sel % len(self.player.queue))
        elif self.panel == 2 and self.shelf:
            t = self.shelf[min(self.shelf_sel, len(self.shelf) - 1)]
            self.player.set_queue([{"reciter": "My Shelf", "moshaf": "",
                                    "title": t["title"], "filepath": t["filepath"],
                                    "url": "", "_via": "saved file",
                                    "_file": t["filepath"].split("/")[-1]}], 0)
            err = self.player.play_index(0)
            self.say(err or f"playing {t['title']}")
        elif self.panel == 0 and not self.player.queue:
            self.panel = 1
            self.say("pick a reciter, Enter plays", 6)
            return None
        elif self.panel == 0 and not self.player.playing and self.player.queue:
            self.player.play()
        return None

    # ---------------------------------------------------------- paint
    def _paint(self, stdscr, static_t=None):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        self._poll_fetch()
        self._poll_shelf()
        t = static_t if static_t is not None else time.time() - self.t0
        if self.fullscreen:
            self._paint_full(stdscr, h, w, t)
        else:
            self._paint_normal(stdscr, h, w, t)
        # footer: hints + status
        try:
            stdscr.addstr(h - 2, 1, HINTS[self.panel][:w - 2], self.C("dim"))
            status = self._status_line()
            stdscr.addstr(h - 1, 1, status[:w - 2],
                          self.C("highlight") if self.msg and time.time() < self.msg_until else self.C("dim"))
        except curses.error:
            pass
        stdscr.refresh()

    def _status_line(self):
        parts = []
        if self.msg and time.time() < self.msg_until:
            parts.append(self.msg)
        if self.dl and self.dl.get("running"):
            d = self.dl
            fpct = int(100 * d.get("frac", 0))
            parts.append(f"saving {d['label']}: {d['done']}/{d['total']}"
                         + (f" - {d['cur']} {fpct}%" if d.get("cur") else "")
                         + " - x cancels")
        if self.fetch and self.fetch.get("running"):
            f = self.fetch
            b, tb = f.get("bytes", 0), f.get("total_bytes", 0)
            pct = int(100 * b / tb) if tb else 0
            parts.append(f"fetching {f.get('cur', '')}: {pct}% - x cancels")
        if self.shelf_job and self.shelf_job.get("running"):
            sj = self.shelf_job
            tot = f"/{sj['total']}" if sj.get("total") else ""
            parts.append(f"shelf: {sj.get('done', 0)}{tot} - {int(sj.get('pct', 0))}% - x stops")
        left = self.player.sleep_left()
        if left > 0:
            m, s = int(left // 60), int(left % 60)
            parts.append(f"sleeps in {m:02d}:{s:02d}")
        if not parts:
            parts.append("Tab panels - ? all keys - q quit")
        return "   ".join(parts)

    def _frac(self):
        try:
            d = self.player.backend.dur() or (self.player.current() or {}).get("duration") or 0
            p = self.player.backend.pos() or 0
            return (p / d) if d else 0
        except Exception:
            return 0

    def _paint_full(self, stdscr, h, w, t):
        cur = self.player.current() or {}
        try:
            stdscr.addstr(0, 1, self.player.describe()[:w - 2], self.C("title"))
        except curses.error:
            pass
        try:
            d = self.player.backend.dur() or cur.get("duration") or 0
            p = self.player.backend.pos() or 0
        except Exception:
            d, p = 0, 0
        lively = self.player.playing and not self.player.paused
        y = 1
        curve = cur.get("_nrg")
        if curve and d:
            # PULSE: real recitation energy around the playhead.
            rows = art.pulse_rows(curve, p if lively else p, d, w - 2,
                                  height=max(2, (h - 9) // 2))
            for ln in rows[:max(0, h - 8)]:
                try:
                    stdscr.addstr(y, 1, ln[:w - 2], self.C("accent"))
                except curses.error:
                    pass
                y += 1
        else:
            mh = max(4, h - 7)
            for ln in art.frame(self.anim, w - 2, mh, t, self._frac()):
                try:
                    stdscr.addstr(y, 1, ln[:w - 2], self.C("accent"))
                except curses.error:
                    pass
                y += 1
            try:
                stdscr.addstr(y, 1, art.bars(w - 2, t, lively)[:w - 2], self.C("accent"))
            except curses.error:
                pass
        try:
            stdscr.addstr(h - 4, 1, f"{self.player.time_text()}   v back - A anim"[:w - 2],
                          self.C("text"))
            stdscr.addstr(h - 3, 1, progress_bar(self._frac(), w - 4)[:w - 2],
                          self.C("progress_fill"))
        except curses.error:
            pass

    def _paint_normal(self, stdscr, h, w, t):
        tabs = "   ".join(f"[{i + 1} {p}]" if i == self.panel else f"{i + 1} {p}"
                          for i, p in enumerate(self.panels))
        try:
            stdscr.addstr(0, 1, f"Tilawah v{APP_VERSION}   {tabs}"[:w - 2], self.C("title"))
            stdscr.addstr(1, 1, "-" * (w - 2), self.C("border"))
        except curses.error:
            pass
        if self.panel == 0:
            self._now_box(stdscr, h, w, t)
        elif self.panel == 1:
            self._library(stdscr, h, w)
        elif self.panel == 2:
            self._shelf(stdscr, h, w)
        elif self.panel == 3:
            self._queue(stdscr, h, w)
        if self.show_help:
            self._help(stdscr, h, w)
        if self.mode == "download":
            self._download_box(stdscr, h, w)
        if self.mode == "fetch":
            self._fetch_box(stdscr, h, w)
        if self.mode == "search":
            self._prompt(stdscr, h, w, "find reciter: ", self.filter)
        elif self.mode == "sleep":
            self._prompt(stdscr, h, w, "sleep? 1=15m 2=30m 3=60m or minutes: ", self.buf)
        elif self.mode == "url":
            self._prompt(stdscr, h, w, "paste link, Enter fetches its audio: ", self.buf)

    def _now_box(self, stdscr, h, w, t):
        cur = self.player.current()
        by, bx = self.box
        bw, bh = min(w - 4, 56), 13
        y = min(max(2, by), max(2, h - bh - 4))
        x = min(max(1, bx), max(1, w - bw - 1))
        self._frame(stdscr, y, x, bw, bh, "Now Playing")
        lines = self._now_lines(bw - 2, t)
        for i in range(bh - 2):
            self._frow(stdscr, y + 1 + i, x, bw,
                       lines[i] if i < len(lines) else "")

    def _audio_note(self):
        """Loud, never silent: dummy backend means no sound can come out."""
        try:
            name = self.player.backend.name
        except Exception:
            name = ""
        if name == "dummy":
            return "NO SOUND here: sudo apt install mpv"
        return ""

    def _now_lines(self, width, t):
        cur = self.player.current()
        if not cur:
            return ["", "Nothing playing yet.",
                    "Tab -> Reciters, Enter on a surah.",
                    "", "Your 40-track shelf lives under My Shelf."]
        fav = self.store.is_favorite(cur.get("reciter", ""), cur.get("moshaf", ""),
                                     cur.get("surah") or 0) if cur.get("surah") else False
        desc = self.player.describe(cur)
        if fav:
            desc = "* " + desc
        try:
            buffering = self.player.backend.buffering()
        except Exception:
            buffering = False
        state = "buffering..." if buffering else (
            "paused" if self.player.paused else ("playing" if self.player.playing else "stopped"))
        vol = "muted" if self.player.muted else f"vol {self.player.volume} {vol_bar(self.player.volume, 8)}"
        pills = []
        if self.player.shuffle:
            pills.append("shuffle")
        pills.append(f"repeat {self.player.repeat}")
        if self.player.sleep_left() > 0:
            pills.append("sleep on")
        kbps = ""
        try:
            k = self.player.backend.audio_kbps()
            kbps = f" - {k}kbps" if k else ""
        except Exception:
            pass
        lively = self.player.playing and not self.player.paused
        viz = [art.bars(max(10, width - 2), t, lively)]
        try:
            dd = self.player.backend.dur() or cur.get("duration") or 0
            pp = self.player.backend.pos() or 0
        except Exception:
            dd, pp = 0, 0
        if cur.get("_nrg") and dd:
            prow = art.pulse_rows(cur["_nrg"], pp, dd, max(10, width - 2), height=2)
            if len(prow) >= 4:
                viz = prow[:4]
        lines = [desc[:width],
                 f"{state}{kbps}   {self.player.time_text()}   {vol}",
                 progress_bar(self._frac(), max(10, width - 2))] + viz + [
                 " ".join(pills)]
        note = self._audio_note()
        if note:
            lines.insert(1, note[:width])
        return lines

    def _library(self, stdscr, h, w):
        if self.list_view == "favs":
            rows = [f"* {f['reciter']} - {self.surah_name(f['surah'])} ({f['surah']:03d})"
                    for f in self.favs] or ["No favorites yet - play something and press f."]
            self._list(stdscr, h, w, "Favorites  (F goes back)", rows, self.sur_sel)
            return
        if self.list_view == "hist":
            rows = []
            for x in self.hist:
                ts = time.strftime("%m-%d %H:%M", time.localtime(x["started_at"]))
                rows.append(f"{ts}   {x['reciter']} - {self.surah_name(x['surah'])}")
            rows = rows or ["Nothing played yet."]
            self._list(stdscr, h, w, "Recently played  (H goes back)", rows, self.sur_sel)
            return
        rs = self.visible_reciters()
        top_n = len(api_mod.curate(self.reciters)[0]) or 20
        r, m, _ = self.current_moshaf(rs)
        nums = self.surah_numbers(rs)
        if not rs:
            self._list(stdscr, h, w, "Reciters - still loading...",
                       ["Connect once and the list appears by itself.",
                        "Streaming and saving need one online fetch,",
                        "then everything works offline."], 0)
            return
        hw = w // 2
        scope = f"Top {top_n}" if not self.show_all else f"all {len(self.reciters)}"
        try:
            left_h = (f"Reciters - {scope} (C toggles)"
                      + (f" - find: {self.filter}" if self.filter else ""))[:hw - 2]
            stdscr.addstr(2, 1, left_h, self.C("accent"))
            right_h = (f"{r['name'] if r else '-'}"
                       + (f" - {m['name']}" if m and m.get("name") else "")
                       + (" - w: narration" if r and len(r.get("moshaf", [])) > 1 else ""))[:w - hw - 2]
            stdscr.addstr(2, hw, right_h, self.C("accent"))
        except curses.error:
            pass
        maxrows = max(1, h - 6)
        r_top = _win_top(self.rec_sel, len(rs), maxrows)
        s_top = _win_top(self.sur_sel, len(nums), maxrows)
        for i in range(min(len(rs) - r_top, maxrows)):
            try:
                sel = (r_top + i == self.rec_sel) and self.col == 0
                mark = "> " if r_top + i == self.rec_sel else "  "
                stdscr.addstr(3 + i, 1, (mark + rs[r_top + i]["name"])[:hw - 2],
                              self.C("highlight") if sel else self.C("text"))
            except curses.error:
                pass
        for i in range(min(len(nums) - s_top, maxrows)):
            try:
                n = nums[s_top + i]
                sel = (s_top + i == self.sur_sel) and self.col == 1
                mark = "> " if s_top + i == self.sur_sel else "  "
                label = f"{mark}{n:03d} - {self.surah_name(n)}"
                stdscr.addstr(3 + i, hw, label[:w - hw - 1],
                              self.C("highlight") if sel else self.C("text"))
            except curses.error:
                pass

    def _shelf(self, stdscr, h, w):
        self.refresh_shelf()
        rows = [t["title"] for t in self.shelf] or \
            ["Your shelf is empty.",
             "Press Y to fetch your tracks, or u to paste one link."]
        self._list(stdscr, h, w,
                   f"My Shelf - {len(self.shelf)} saved ({self._shelf_size() / 1e6:.0f}MB)",
                   rows, self.shelf_sel)

    def _queue(self, stdscr, h, w):
        rows = self.player.queue_view() or ["Queue is empty - play anything to fill it."]
        self._list(stdscr, h, w,
                   f"Up next - repeat {self.player.repeat} - shuffle "
                   f"{'on' if self.player.shuffle else 'off'}", rows, self.q_sel)

    def _list(self, stdscr, h, w, title, rows, sel):
        try:
            stdscr.addstr(2, 1, title[:w - 2], self.C("accent"))
        except curses.error:
            pass
        maxrows = max(1, h - 6)
        top = _win_top(sel, len(rows), maxrows)
        for i in range(min(len(rows) - top, maxrows)):
            try:
                on = top + i == sel
                row = rows[top + i]
                text = row if row.startswith("> ") else ("> " if on else "  ") + row
                stdscr.addstr(3 + i, 1, text[:w - 2],
                              self.C("highlight") if on else self.C("text"))
            except curses.error:
                pass

    def _help(self, stdscr, h, w):
        bw = min(w - 4, 52)
        bh = min(h - 4, len(KEYMAP_DOC) + 4)
        y, x = max(1, (h - bh) // 2), max(0, (w - bw) // 2)
        self._frame(stdscr, y, x, bw, bh, "Keys (?)")
        for i, (k, v) in enumerate(KEYMAP_DOC[:bh - 2]):
            self._frow(stdscr, y + 1 + i, x, bw, f" {k:22s} {v}")

    def _download_box(self, stdscr, h, w):
        rows = [f"Save for offline - {self.dl_title}"]
        for k, label, items in self.dl_opts:
            if items:
                have = self._cached_count(items)
                rows.append(f"  {k}  {label}   ({have}/{len(items)} saved)")
            else:
                rows.append(f"  {k}  {label}")
        if self.dl and self.dl.get("running"):
            d = self.dl
            rows.append("")
            rows.append(f"  working {d['done']}/{d['total']}"
                        + (f" - {d['cur']}" if d.get("cur") else ""))
            rows.append("  " + progress_bar(d["done"] / max(1, d["total"]), 30))
        rows += ["", "  1-4 choose - x cancel - Esc close"]
        bw = min(w - 4, max([len(r) for r in rows]) + 6)
        bh = min(h - 4, len(rows) + 2)
        y, x = max(1, (h - bh) // 2), max(0, (w - bw) // 2)
        self._frame(stdscr, y, x, bw, bh, "Save for offline")
        for i, r in enumerate(rows[:bh - 2]):
            self._frow(stdscr, y + 1 + i, x, bw, f" {r}",
                       self.C("highlight") if i == 0 else self.C("text"))

    def _fetch_box(self, stdscr, h, w):
        job = self.fetch or {}
        b, tb = job.get("bytes", 0), job.get("total_bytes", 0)
        pct = (b / tb) if tb else 0.0
        rate = job.get("rate", 0) or 0
        eta = ""
        if rate > 1024 and tb and b < tb:
            secs = int((tb - b) / rate)
            eta = f"  ~{secs // 60:02d}:{secs % 60:02d} left"
        size = f"{b / 1e6:.1f} MB" + (f" / {tb / 1e6:.1f} MB" if tb else "")
        rows = [f"Fetching first - {job.get('label', '')}",
                f"  {size}   {int(pct * 100)}%{eta}",
                "  " + progress_bar(pct, 30),
                "",
                "  x / Esc cancel"]
        bw = min(w - 4, max([len(r) for r in rows]) + 6)
        bh = min(h - 4, len(rows) + 2)
        y, x = max(1, (h - bh) // 2), max(0, (w - bw) // 2)
        self._frame(stdscr, y, x, bw, bh, "Fetching")
        for i, r in enumerate(rows[:bh - 2]):
            self._frow(stdscr, y + 1 + i, x, bw, f" {r}",
                       self.C("highlight") if i == 0 else self.C("text"))

    def _prompt(self, stdscr, h, w, label, buf):
        try:
            stdscr.addstr(h - 3, 1, (label + buf)[:w - 2], self.C("highlight"))
        except curses.error:
            pass


def _win_top(sel, total, height):
    """Scroll window so the cursor stays visible."""
    if total <= height:
        return 0
    return max(0, min(sel - height // 2, total - height))
