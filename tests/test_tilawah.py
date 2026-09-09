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
                app = App(store, dict(cfg), p, [], d)
                app.panel = panel
                app.fullscreen = fs
                app._paint(Stub())


if __name__ == "__main__":
    unittest.main()
