"""Tilawah test suite — stdlib unittest, no third-party deps.

Run:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tilawah import api, art, config, downloader, themes
from tilawah.db import Store
from tilawah.player import DummyBackend, Player


class ApiShapeTest(unittest.TestCase):
    def test_audio_url_pattern(self):
        self.assertEqual(api.audio_url("https://server6.mp3quran.net/akdr/", 1),
                         "https://server6.mp3quran.net/akdr/001.mp3")
        self.assertEqual(api.audio_url("https://server9.mp3quran.net/akrm", 114),
                         "https://server9.mp3quran.net/akrm/114.mp3")

    def test_available_surahs(self):
        m = {"surah_list": "1,2,3,5,114"}
        self.assertEqual(api.available_surahs(m), [1, 2, 3, 5, 114])

    def test_curate_top_picks(self):
        recs = [{"id": i, "name": n, "moshaf": [{"id": 1, "name": "M", "server": "https://x/",
                 "surah_total": 1, "surah_list": "1", "rewaya_id": 1}]}
                for i, n in enumerate(["Yasser Al-Dosari", "Mohammed Al-Lohaidan",
                                       "Some Obscure Reader", "Mishary Alafasi"])]
        top, rest = api.curate(recs)
        names = [r["name"] for r in top]
        self.assertIn("Yasser Al-Dosari", names)
        self.assertIn("Mohammed Al-Lohaidan", names)
        self.assertIn("Mishary Alafasi", names)
        self.assertEqual([r["name"] for r in rest], ["Some Obscure Reader"])
        self.assertEqual(api.preferred_moshaf_index(
            {"moshaf": [{"name": "A"}, {"name": "Hafs - Murattal"}]}), 1)
        self.assertEqual(api.preferred_moshaf_index(
            {"moshaf": [{"name": "Rewayat AlDorai - Murattal",
                         "surah_list": "12,14,25,87,97,99"},
                        {"name": "Rewayat Hafs A'n Assem - Murattal",
                         "surah_list": ",".join(str(i) for i in range(1, 115))}]}), 1)

    def test_live_reciters_shape(self):
        try:
            recs = api.fetch_reciters()
        except Exception as e:
            self.skipTest(f"offline: {e}")
        self.assertGreater(len(recs), 100)
        r0 = recs[0]
        for k in ("id", "name", "moshaf"):
            self.assertIn(k, r0)
        m0 = r0["moshaf"][0]
        for k in ("server", "surah_list", "surah_total"):
            self.assertIn(k, m0)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.s = Store(os.path.join(self.d, "t.db"))

    def tearDown(self):
        self.s.close()

    def test_fav_history_position(self):
        self.assertTrue(self.s.toggle_favorite("R", "M", 36))
        self.assertTrue(self.s.is_favorite("R", "M", 36))
        self.assertFalse(self.s.toggle_favorite("R", "M", 36))
        self.s.add_history("R", "M", 36, 12, "stream")
        self.assertEqual(len(self.s.get_history()), 1)
        self.s.save_position("R", "M", 36, 90.5)
        self.assertAlmostEqual(self.s.get_position("R", "M", 36), 90.5)
        self.assertEqual(self.s.last_position()["surah"], 36)
        self.s.upsert_track("T", "U", "/f.mp3")
        self.assertEqual(len(self.s.get_playlist()), 1)

    def test_catalog_roundtrip(self):
        recs = [{"id": 1, "name": "Test Reciter", "letter": "T",
                 "moshaf": [{"id": 1, "name": "M", "server": "https://x/",
                             "surah_total": 2, "surah_list": "1,2", "rewaya_id": 1}]}]
        self.s.save_reciters(recs)
        back = self.s.load_reciters()
        self.assertEqual(back[0]["name"], "Test Reciter")
        self.assertEqual(back[0]["moshaf"][0]["server"], "https://x/")


class PlayerTest(unittest.TestCase):
    def tracks(self):
        return [{"reciter": "R", "moshaf": "M", "surah": n,
                 "url": f"https://x/{n:03d}.mp3", "duration": 100.0} for n in (1, 2, 3)]

    def test_queue_next_prev_repeat(self):
        p = Player(store=None, backend=DummyBackend())
        p.set_queue(self.tracks())
        self.assertIsNone(p.play())
        self.assertTrue(p.playing)
        p.next()
        self.assertEqual(p.current()["surah"], 2)
        p.prev()
        p.backend._pos = 0.0
        p.prev()
        self.assertEqual(p.current()["surah"], 1)
        p.cycle_repeat()
        self.assertEqual(p.repeat, "one")
        p.next(auto=True)  # repeat-one replays
        self.assertEqual(p.current()["surah"], 1)

    def test_shuffle_jump_seek_volume(self):
        p = Player(store=None, backend=DummyBackend())
        p.set_queue(self.tracks())
        p.toggle_shuffle()
        self.assertTrue(p.shuffle)
        p.play()
        p.jump(2)
        self.assertEqual(len(p.queue_view()), 3)
        p.set_volume(50)
        self.assertEqual(p.volume, 50)
        pos = p.seek(10)
        self.assertGreaterEqual(pos, 10)

    def test_sleep_timer_fires(self):
        p = Player(store=None, backend=DummyBackend())
        p.set_queue(self.tracks())
        p.play()
        p.start_sleep(0.01, fade=5)  # ~0.6s
        time.sleep(1.5)
        self.assertFalse(p.playing)

    def test_close_and_sleep_guard(self):
        p = Player(store=None, backend=DummyBackend())
        p.set_queue(self.tracks())
        p.play()
        p.start_sleep(0)  # ignored, keeps playing
        self.assertIsNone(p.sleep_until)
        p.close()  # must not raise, backend silenced
        self.assertFalse(p.playing)

    def test_resolve_labels_source(self):
        import tempfile
        fd, fp = tempfile.mkstemp(suffix=".mp3")
        os.write(fd, b"x" * 64)
        os.close(fd)
        try:
            p = Player(store=None, backend=DummyBackend(), offline=True)
            src, via = p._resolve({"reciter": "R", "moshaf": "M", "surah": 1,
                                   "url": "https://x/001.mp3", "filepath": fp})
            self.assertEqual(via, "saved file")
            self.assertEqual(src["filepath"], fp)
            p2 = Player(store=None, backend=DummyBackend(), offline=True)
            with self.assertRaises(RuntimeError):
                p2._resolve({"reciter": "R", "moshaf": "M", "surah": 1,
                             "url": "https://x/001.mp3"})
        finally:
            os.remove(fp)

    def test_offline_without_cache_errors_cleanly(self):
        p = Player(store=None, backend=DummyBackend(), offline=True)
        p.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                      "url": "https://x/001.mp3"}])
        err = p.play()
        self.assertIn("offline", err)


class VisualTest(unittest.TestCase):
    def test_motif_frames_differ_and_sized(self):
        f1 = art.motif_frame(30, 10, 0.0)
        f2 = art.motif_frame(30, 10, 2.0)
        self.assertEqual(len(f1), 10)
        self.assertTrue(all(len(r) == 30 for r in f1))
        self.assertNotEqual(f1, f2)

    def test_avatar_and_splash(self):
        a = art.avatar_ansi("Mishary Rashid Alafasy", 20)
        self.assertTrue(a)
        self.assertTrue(art.splash_lines(40))

    def test_photo_fallback_never_raises(self):
        lines, cached = art.photo_to_ansi("/nonexistent/photo.jpg", 20,
                                          cache_dir=tempfile.mkdtemp())
        self.assertTrue(lines)
        self.assertFalse(cached)

    def test_themes(self):
        for name in ("night", "dawn", "minimal"):
            self.assertIn("border", themes.get(name))


class MiscTest(unittest.TestCase):
    def test_bar(self):
        self.assertIn("#", downloader.bar(50, 100))
        self.assertIn("?", downloader.bar(1, 0))

    def test_config_roundtrip(self):
        cfg = dict(config.DEFAULTS)
        cfg["theme"] = "dawn"
        d = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = d
        try:
            config.save(cfg)
            self.assertEqual(config.load()["theme"], "dawn")
        finally:
            del os.environ["XDG_CONFIG_HOME"]


class TuiRenderTest(unittest.TestCase):
    def test_all_panels_paint_headless(self):
        from tilawah.tui import App

        class Stub:
            def __init__(self, h=30, w=100):
                self.h, self.w = h, w
            def getmaxyx(self):
                return (self.h, self.w)
            def addstr(self, y, x, s, *a):
                assert 0 <= y < self.h and 0 <= x < self.w
            def erase(self):
                pass
            def refresh(self):
                pass

        d = tempfile.mkdtemp()
        store = Store(os.path.join(d, "t.db"))
        cfg = dict(config.DEFAULTS)
        p = Player(store=None, backend=DummyBackend())
        p.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                      "url": "https://x/001.mp3", "duration": 60}])
        p.play()
        for panel in range(4):
            for fs in (False, True):
                app = App(store, dict(cfg), p, [], d, refresh=False)
                app.panel = panel
                app.fullscreen = fs
                app._paint(Stub())
                app.close()
        store.close()


class ControlTest(unittest.TestCase):
    def _app(self, reciters=()):
        import tempfile
        from tilawah.tui import App
        d = tempfile.mkdtemp()
        store = Store(os.path.join(d, "t.db"))
        cfg = dict(config.DEFAULTS)
        p = Player(store=None, backend=DummyBackend())
        p.volume = 80
        app = App(store, dict(cfg), p, list(reciters), d, refresh=False)
        self.addCleanup(app.close)
        self.addCleanup(store.close)
        app._store_dir = d
        return app

    def test_volume_direction_fixed(self):
        import curses
        app = self._app()
        app.panel = 0
        app._key(curses.KEY_UP)
        self.assertEqual(app.player.volume, 85)
        app._key(ord("k"))
        self.assertEqual(app.player.volume, 90)
        app._key(curses.KEY_DOWN)
        self.assertEqual(app.player.volume, 85)
        app._key(ord("j"))
        self.assertEqual(app.player.volume, 80)
        app.store.close()

    def test_wasd_moves_lists(self):
        import curses
        app = self._app()
        app.panel = 3
        app.player.set_queue([
            {"reciter": "R", "moshaf": "M", "surah": n, "url": f"https://x/{n:03d}.mp3",
             "duration": 60} for n in (1, 2, 3)])
        app._key(ord("s"))
        self.assertEqual(app.q_sel, 1)
        app._key(ord("w"))
        self.assertEqual(app.q_sel, 0)
        app._key(curses.KEY_DOWN)
        self.assertEqual(app.q_sel, 1)
        app.store.close()

    def test_panel_digits_and_esc(self):
        app = self._app()
        app._key(ord("3"))
        self.assertEqual(app.panel, 2)
        app._key(27)
        self.assertEqual(app.panel, 0)
        app.store.close()

    def test_juz30_range(self):
        from tilawah import api
        self.assertEqual(len(api.JUZ30), 37)
        self.assertEqual(api.JUZ30[0], 78)
        self.assertEqual(api.JUZ30[-1], 114)

    def test_gate_holds_and_releases(self):
        p = Player(store=None, backend=DummyBackend())
        p.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                      "url": "https://x/001.mp3", "duration": 60}])
        p.on_track_request = lambda t: False
        self.assertEqual(p.play_index(0), "held")
        self.assertFalse(p.playing)
        p.on_track_request = lambda t: True
        self.assertIsNone(p.play_index(0))
        self.assertTrue(p.playing)
        p.close()

    def test_new_queue_switches_source(self):
        import tempfile
        loads = []

        class Rec(DummyBackend):
            def play(self, source, start_at=0, volume=80):
                loads.append(source.get("filepath") or source.get("url"))
                return super().play(source, start_at, volume)

        fd, fp = tempfile.mkstemp(suffix=".mp3")
        os.write(fd, b"x" * 64)
        os.close(fd)
        try:
            p = Player(store=None, backend=Rec())
            p.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                          "url": "https://x/001.mp3", "duration": 60}], 0)
            p.play()
            p.set_queue([{"reciter": "Shelf", "moshaf": "", "title": "T",
                          "filepath": fp, "url": ""}], 0)
            p.play_index(0)
            self.assertEqual(loads, ["https://x/001.mp3", fp])
            self.assertEqual(p.current().get("title"), "T")
            p.close()
        finally:
            os.remove(fp)

    def test_early_eof_hook(self):
        fired = []
        p = Player(store=None, backend=DummyBackend())
        p.on_track_ended_early = lambda t, pos: fired.append((t, pos))
        # ends at 2.8s: past the 2.5s load-grace, inside the 8s early window
        p.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                      "url": "https://x/001.mp3", "duration": 2.8}])
        p.play()
        time.sleep(5)
        self.assertEqual(len(fired), 1)
        self.assertLess(fired[0][1], 3.0)
        p.close()

    def test_big_font_and_borders(self):
        from tilawah import art
        rows = art.big("TILAWAH")
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(rows))
        self.assertTrue(all(set(r) <= set("# ") for r in rows))
        sp = art.splash_big(56, "1.0.8")
        self.assertTrue(sp[0].startswith("\u2554"))
        self.assertIn("v1.0.8", "\n".join(sp))
        self.assertIn("press any key", "\n".join(sp))

    def test_pulse_rows_shape(self):
        from tilawah import art
        curve = {"v": [i / 40 for i in range(40)], "dur": 100.0}
        rows = art.pulse_rows(curve, 50.0, 100.0, 30, height=3)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(len(r) == 30 for r in rows))
        self.assertEqual(art.pulse_rows(None, 0, 0, 30), [])

    def test_energy_curve_loud_vs_quiet(self):
        import shutil
        import subprocess
        if shutil.which("ffmpeg") is None:
            self.skipTest("no ffmpeg")
        from tilawah import nrg
        d = tempfile.mkdtemp()
        varied = os.path.join(d, "varied.wav")
        flat = os.path.join(d, "flat.wav")
        jobs = ((varied, "sine=frequency=440:duration=4,tremolo=f=1:d=1.0"),
                (flat, "sine=frequency=440:duration=4,volume=0.05"))
        for out, filt in jobs:
            filt_in = filt.split(",", 1)
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                                "-f", "lavfi", "-i", filt_in[0],
                                "-af", filt_in[1], out], timeout=60)
            self.assertEqual(r.returncode, 0)
        cv = nrg.energy_curve(varied, buckets=32, cache_dir=d)
        cf = nrg.energy_curve(flat, buckets=32, cache_dir=d)
        self.assertIsNotNone(cv)
        self.assertIsNotNone(cf)
        self.assertGreater(max(cv["v"]) - min(cv["v"]), 0.5)  # breathes
        self.assertLess(max(cf["v"]) - min(cf["v"]), 0.25)    # flat stays flat
        self.assertTrue(all(0.0 <= v <= 1.0 for v in cv["v"]))

    def test_player_fills_nrg(self):
        import shutil
        import subprocess
        import time as _t
        if shutil.which("ffmpeg") is None:
            self.skipTest("no ffmpeg")
        from tilawah import nrg
        d = tempfile.mkdtemp()
        wav = os.path.join(d, "t.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", wav],
                       timeout=60, check=True)
        p = Player(store=None, backend=DummyBackend(), cache_dir=d)
        p.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                      "filepath": wav, "duration": 60.0}])
        p.play()
        for _ in range(100):
            if p.current().get("_nrg"):
                break
            _t.sleep(0.2)
        self.assertIn("_nrg", p.current())
        p.close()

    def test_save_dialog_options(self):
        app = self._app([{"id": 1, "name": "Test Reciter", "letter": "T",
                          "moshaf": [{"id": 1, "name": "M", "server": "https://x/",
                                      "surah_total": 3, "surah_list": "78,79,114",
                                      "rewaya_id": 1}]}])
        app.panel = 1
        app._dl_open()
        self.assertEqual(app.mode, "download")
        labels = [label for _k, label, _it in app.dl_opts]
        self.assertTrue(any("Juz 30" in lb and "(3 surahs)" in lb for lb in labels))
        self.assertTrue(any(lb.startswith("whole Test Reciter") for lb in labels))
        app.store.close()

    def test_fetch_gate_needs_saved_state(self):
        import tempfile
        app = self._app()
        dd = tempfile.mkdtemp()
        app.cfg["download_dir"] = dd
        app.cfg["play_mode"] = "download"
        t = {"reciter": "Some Reciter", "moshaf": "M", "surah": 7,
             "url": "https://x/007.mp3"}
        self.assertTrue(app._needs_fetch(t))
        os.makedirs(os.path.join(dd, "Some Reciter"), exist_ok=True)
        with open(os.path.join(dd, "Some Reciter", "007.mp3"), "wb") as fh:
            fh.write(b"x" * 40000)
        self.assertTrue(app._is_saved(t))
        self.assertFalse(app._needs_fetch(t))
        app.cfg["play_mode"] = "stream"
        self.assertFalse(app._needs_fetch({"reciter": "R", "moshaf": "M",
                                           "surah": 1, "url": "https://x/001.mp3"}))
        app.store.close()

    def test_poll_fetch_completes_to_play(self):
        import tempfile
        app = self._app()
        dd = tempfile.mkdtemp()
        app.cfg["download_dir"] = dd
        os.makedirs(os.path.join(dd, "R"), exist_ok=True)
        with open(os.path.join(dd, "R", "001.mp3"), "wb") as fh:
            fh.write(b"x" * 40000)
        app.player.set_queue([{"reciter": "R", "moshaf": "M", "surah": 1,
                               "url": "https://x/001.mp3", "duration": 60}])
        app.player.index = 0
        app.fetch = {"running": False, "ok": True, "cancel": False,
                     "label": "R - surah 001"}
        app._pending = {"queue": True}
        app.mode = "fetch"
        app._poll_fetch()
        self.assertIsNone(app.fetch)
        self.assertEqual(app.mode, "browse")
        self.assertTrue(app.player.playing)
        app.player.close()
        app.store.close()

    def test_playlist_helpers(self):
        from tilawah import ytpl
        self.assertTrue(ytpl.DEFAULT_PLAYLIST_URL.startswith("https://"))
        self.assertIn("list=", ytpl.DEFAULT_PLAYLIST_URL)
        self.assertEqual(ytpl._dl_pct("[download]  45.2% of ~12MB"), 45.2)
        self.assertEqual(ytpl._dl_pct("[download] 100%"), 100.0)
        self.assertIsNone(ytpl._dl_pct("[info] hello"))

    def test_single_vs_playlist_cmd(self):
        from pathlib import Path
        from tilawah import ytpl
        one = ytpl._build_cmd("https://youtu.be/abc", Path("/tmp/x"), 40, True)
        many = ytpl._build_cmd("https://youtube.com/playlist?list=PLx", Path("/tmp/x"), 40, False)
        self.assertIn("--no-playlist", one)
        self.assertIn("--yes-playlist", many)
        self.assertIn("1", one[one.index("--max-downloads") + 1])
        self.assertNotIn("playlist_index", one[one.index("-o") + 1])
        self.assertIn("playlist_index", many[many.index("-o") + 1])

    def test_url_prompt_mode(self):
        app = self._app()
        app._key(ord("u"))
        self.assertEqual(app.mode, "url")
        app._key(ord("h"))
        app._key(ord("i"))
        self.assertEqual(app.buf, "hi")
        app._key(27)
        self.assertEqual(app.mode, "browse")
        app._key(ord("u"))
        app._key(10)  # Enter on empty URL just closes, no threads
        self.assertEqual(app.mode, "browse")
        self.assertIsNone(app.shelf_job)
        app.store.close()


try:
    import rich  # noqa: F401
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@unittest.skipUnless(HAS_RICH, "no rich on this machine")
class RichUiTest(unittest.TestCase):
    def _console(self):
        from rich.console import Console
        from tilawah import ui_rich
        return Console(width=100, record=True, theme=ui_rich.THEME)

    def _app(self):
        import tempfile
        from tilawah import ui_rich
        from tilawah.db import Store
        from tilawah.player import DummyBackend, Player
        d = tempfile.mkdtemp()
        store = Store(os.path.join(d, "r.db"))
        mosh = [{"id": 1, "name": "Hafs - Murattal", "server": "https://x/",
                 "surah_total": 114, "surah_list": "1,2,18", "rewaya_id": 1}]
        reciters = [{"id": 1, "name": "Mishary Alafasi", "letter": "M", "moshaf": mosh}]
        p = Player(store=None, backend=DummyBackend())
        p.set_queue([{"reciter": "Mishary Alafasi", "moshaf": "H", "surah": 18,
                      "url": "https://x/018.mp3", "duration": 600.0}], 0)
        p.play()
        return ui_rich.RichApp(store, {"show_all_reciters": True}, p, reciters), store, p

    def test_assets(self):
        from tilawah import ui_rich
        self.assertEqual(ui_rich.HAVE_RICH, True)
        rows = ui_rich.kufic("TILAWAH")
        self.assertEqual(len(rows), 7)
        self.assertIn("#", "".join(rows))
        bar = ui_rich.pbar(0.5, 10)
        self.assertEqual(len(bar), 10)
        self.assertIn("\u25b0", bar)
        self.assertIn("\u25b1", bar)

    def test_dashboard_content(self):
        app, store, p = self._app()
        p.seek(300)
        c = self._console()
        c.print(app.render_dashboard())
        out = c.export_text()
        self.assertIn("Mishary Alafasi", out)
        self.assertIn("Al-Kahf", out)
        self.assertIn("\u25b0", out)
        self.assertIn("\u23f5", out)
        p.close()
        store.close()

    def test_library_content(self):
        app, store, p = self._app()
        c = self._console()
        c.print(app.render_library())
        out = c.export_text()
        self.assertIn("Mishary Alafasi", out)
        self.assertIn("\u06dd", out)
        self.assertIn("\U0001f54b", out)  # Makki icon on Al-Fatihah
        self.assertIn("Al-Kahf", out)
        p.close()
        store.close()

    def test_shelf_and_queue_content(self):
        import tempfile
        app, store, p = self._app()
        fd, fp = tempfile.mkstemp(suffix=".webm")
        os.write(fd, b"x" * 1000)
        os.close(fd)
        store.upsert_track("Test Track", "http://x", fp)
        c = self._console()
        c.print(app.render_shelf())
        out = c.export_text()
        self.assertIn("My Shelf", out)
        self.assertIn("Test Track", out)
        self.assertIn("\U0001f4be", out)
        os.remove(fp)
        c2 = self._console()
        c2.print(app.render_queue())
        out2 = c2.export_text()
        self.assertIn("Up Next", out2)
        self.assertIn("\u23f5", out2)
        p.close()
        store.close()

    def test_rich_keys(self):
        app, store, p = self._app()
        app.key("3")
        self.assertEqual(app.panel, 2)
        app.key("1")
        self.assertEqual(app.panel, 0)
        v0 = p.volume
        app.key("up")
        self.assertEqual(p.volume, v0 + 5)
        app.key("j")
        self.assertEqual(p.volume, v0)
        app.key("?")
        self.assertTrue(app.show_help)
        app.key("?")
        self.assertFalse(app.show_help)
        self.assertEqual(app.key("q"), "quit")
        p.close()
        store.close()

    def test_demo_runs(self):
        from rich.console import Console
        from tilawah import ui_rich
        c = Console(width=100, record=True, theme=ui_rich.THEME)
        self.assertEqual(ui_rich.demo(c), 0)
        out = c.export_text()
        for needle in ("Mishary Alafasi", "Al-Kahf", "My Shelf", "Up Next"):
            self.assertIn(needle, out)


if __name__ == "__main__":
    unittest.main()
