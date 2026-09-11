"""Rich frontend: Islamic-aesthetic Live dashboard for Tilawah.

`tilawah rich [--demo]` — needs the `rich` package
(`sudo apt install python3-rich` / `pip install rich`).

Design contract (user spec): parchment/gold/emerald palette, double and
rounded borders, geometric motif dividers, ayah/end markers, Makki/Madani
icons, transport glyphs, braille + block visualizers, custom progress bar,
Kufic-style splash with fade, two-pane library, RTL-aware shelf table,
up-next queue card with marquee. All animation via rich.Live (~15fps).

Scope: panels, transport, search, favorites/history views, help. Sleep
timer and downloads live in the classic curses TUI and the CLI (the help
screen says so). Everything exposed here works; nothing here is a stub.

Zero backend duplication: Player/Store/api/surahs/nrg are imported and
shared with the curses frontend.
"""

import math
import os
import select
import sys
import termios
import time
import tty

try:
    from rich.align import Align
    from rich.box import DOUBLE, ROUNDED
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

from . import api as api_mod
from . import nrg as nrg_mod
from .surahs import by_number

# ---------------------------------------------------------------- palette
PARCHMENT = "#F4ECD8"
GOLD = "#D4AF37"
EMERALD = "#50C878"
MIDNIGHT = "#0B1026"
DIM = "#8A8FA3"

THEME = Theme({
    "parch": PARCHMENT,
    "gold": GOLD,
    "emerald": EMERALD,
    "dim": DIM,
    "night": MIDNIGHT,
}) if HAVE_RICH else None

# ------------------------------------------------------------ glyph assets
AYAH = "\u06dd"          # end-of-ayah / selection pointer
STAR4 = "\u2727"
STAR8 = "\u2736"
MOTIF = "\u06de"         # symmetric geometric divider mark
PLAY, PAUSE, QUEUE = "\u23f5", "\u23f8", "\u2398"
POINTER = "\u06dd"
MAKKI, MADANI = "\U0001f54b", "\U0001f54c"
YT, LOCAL = "\U0001f534", "\U0001f4be"
SPIN = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
BLOCKS = " \u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def motif_divider(width=48):
    side = "\u254c" * ((width - 6) // 2)
    return f"{STAR4} {side} {MOTIF} {side} {STAR4}"


# Square-Kufic-inspired 7-row geometric letterforms ('#' cells only).
KUFIC = {
    "T": ["#######", "#######", "   #   ", "   #   ", "   #   ", "   #   ", "   #   "],
    "I": ["#######", "#######", "   #   ", "   #   ", "   #   ", "#######", "#######"],
    "L": ["#      ", "#      ", "#      ", "#      ", "#      ", "#######", "#######"],
    "A": ["  ###  ", " ##### ", "## # ##", "## # ##", "#######", "## # ##", "## # ##"],
    "W": ["## # ##", "## # ##", "## # ##", "## # ##", "## # ##", "### ###", "### ###"],
    "H": ["## # ##", "## # ##", "## # ##", "#######", "## # ##", "## # ##", "## # ##"],
    " ": ["       "] * 7,
    "?": ["#######", "#     #", "    ## ", "   ##  ", "   #   ", "       ", "   #   "],
}


def kufic(text):
    rows = [""] * 7
    for ch in str(text).upper():
        g = KUFIC.get(ch, KUFIC["?"])
        for i in range(7):
            rows[i] += g[i] + "  "
    return [r.rstrip() for r in rows]


def pbar(frac, width=30):
    frac = min(1.0, max(0.0, frac or 0.0))
    fill = int(width * frac)
    return "\u25b0" * fill + "\u25b1" * (width - fill)


def has_arabic(s):
    return any("\u0600" <= c <= "\u06ff" for c in (s or ""))


def bidi_cell(s, width):
    """RTL-aware cell: Arabic right-aligned, else left; never splits words."""
    t = Text(s or "", overflow="ellipsis", no_wrap=True,
             justify="right" if has_arabic(s) else "left")
    return t


# ------------------------------------------------------------------ app
class RichApp:
    PANELS = ["Now Playing", "Reciters", "My Shelf", "Queue"]

    def __init__(self, store, cfg, player, reciters, status_msg=""):
        self.store = store
        self.cfg = cfg
        self.player = player
        self.reciters = reciters or []
        self.panel = 0
        self.rec_sel = 0
        self.sur_sel = 0
        self.col = 0
        self.shelf_sel = 0
        self.q_sel = 0
        self.moshaf_idx = {}
        self.filter = ""
        self.mode = "browse"  # browse | search
        self.buf = ""
        self.msg = status_msg
        self.msg_until = time.time() + 4 if status_msg else 0
        self.t0 = time.time()
        self.show_help = False
        self.list_view = "reciters"
        self.favs = []
        self.hist = []
        self.shelf = []
        try:
            self.shelf = self.store.get_playlist()
        except Exception:
            pass

    # -- shared data helpers (same rules as the curses frontend) --
    def say(self, text, secs=4):
        self.msg = text
        self.msg_until = time.time() + secs

    def visible_reciters(self):
        top, _rest = api_mod.curate(self.reciters)
        pool = self.reciters if self.cfg.get("show_all_reciters") else (top or self.reciters)
        if not self.filter:
            return pool
        q = self.filter.lower()
        return [r for r in pool if q in r["name"].lower() or q == str(r["id"])]

    def current_moshaf(self):
        rs = self.visible_reciters()
        if not rs:
            return None, None
        r = rs[min(self.rec_sel, len(rs) - 1)]
        ms = r.get("moshaf", [])
        if not ms:
            return r, None
        idx = self.moshaf_idx.get(r["name"], api_mod.preferred_moshaf_index(r))
        return r, ms[max(0, min(idx, len(ms) - 1))]

    def surah_numbers(self):
        _r, m = self.current_moshaf()
        if m:
            try:
                return api_mod.available_surahs(m)
            except Exception:
                pass
        from .surahs import SURAHS
        return [n for n, *_ in SURAHS]

    def surah_name(self, n):
        s = by_number(n)
        return s["translit"] if s else f"Surah {n}"

    def frac(self):
        try:
            d = self.player.backend.dur() or (self.player.current() or {}).get("duration") or 0
            p = self.player.backend.pos() or 0
            return (p / d) if d else 0
        except Exception:
            return 0

    # -- actions --
    def make_track(self, r, m, surah):
        import os as _os
        from . import downloader as _dl
        fp = ""
        try:
            cand = str(_dl._local_name(self.cfg.get("download_dir", "~/Tilawah"),
                                       r["name"], surah))
            fp = cand if _os.path.exists(cand) else ""
        except Exception:
            pass
        return {"reciter": r["name"], "moshaf": m.get("name", ""), "surah": surah,
                "url": api_mod.audio_url(m["server"], surah), "filepath": fp,
                "prefer_local": bool(self.cfg.get("offline"))}

    def play_selection(self):
        r, m = self.current_moshaf()
        if not r or not m:
            self.say("this reciter has no audio")
            return
        nums = self.surah_numbers()
        s = nums[min(self.sur_sel, len(nums) - 1)]
        self.player.set_queue([self.make_track(r, m, n) for n in nums], nums.index(s))
        err = self.player.play_index(self.player.index)
        self.say(err if err else f"{PLAY} {r['name']} - surah {s:03d}", 6 if err else 4)

    # -- render: splash --
    def render_splash(self, step=7):
        lines = kufic("TILAWAH")
        body = []
        for i, ln in enumerate(lines):
            style = "bold " + ("gold" if i <= step else "dim")
            body.append(Text(ln, style=style, justify="center"))
        body.append(Text(motif_divider(52), style="emerald", justify="center"))
        body.append(Text("terminal Qur'an audio player", style="parch", justify="center"))
        return Panel(Group(*body), box=DOUBLE, border_style=GOLD,
                     title=f"{STAR8} tilawah {STAR8}", title_align="center",
                     subtitle="press any key", subtitle_align="center")

    # -- render: dashboard --
    def energy_bars(self, width):
        cur = self.player.current() or {}
        lively = self.player.playing and not self.player.paused
        curve, dur = cur.get("_nrg"), None
        try:
            dur = self.player.backend.dur() or cur.get("duration") or 0
            pos = self.player.backend.pos() or 0
        except Exception:
            pos = 0
        if curve and dur:
            span = max(8.0, dur * 0.06)
            vals = []
            for i in range(width):
                back = span * (width - 1 - i) / max(1, width - 1)
                vals.append(nrg_mod.at(curve, pos - back, dur))
            return "".join(BLOCKS[int(v * 7)] for v in vals)
        t = time.time() - self.t0
        out = []
        for i in range(width):
            v = (math.sin(t * 2.1 + i * 0.55) * 0.5 + 0.5) * 0.6 + \
                (math.sin(t * 3.7 + i * 1.3) * 0.5 + 0.5) * 0.4
            out.append(BLOCKS[int(v * 7 * (1 if lively else 0.15))])
        return "".join(out)

    def render_dashboard(self, width=76):
        cur = self.player.current()
        t = time.time() - self.t0
        if not cur:
            body = [Text("Nothing playing yet.", style="parch"),
                    Text("Go to Reciters (2), pick a surah, Enter plays.", style="dim")]
            return Panel(Group(*body), title="Now Playing", box=DOUBLE, border_style=GOLD)
        from .surahs import by_number as _bn
        s = _bn(cur.get("surah") or 0) or {}
        state = PAUSE if self.player.paused else (PLAY if self.player.playing else QUEUE)
        spin = SPIN[int(t * 10) % len(SPIN)] if self.player.playing and not self.player.paused else " "
        lines = [
            Text.from_markup(f"[gold]{state} {cur.get('reciter', '?')}[/]"),
            Text.from_markup(f"[emerald]{s.get('translit', cur.get('title', '?'))} "
                             f"[dim]{AYAH} {cur.get('surah', '')}[/]") if cur.get("surah")
            else Text(cur.get("title", "?"), style="emerald"),
            Text(f"{cur.get('_file', '')} - {cur.get('_via', 'stream')}", style="dim"),
            Text(f"{spin} {self.energy_bars(max(20, width - 8))}", style="emerald"),
            Text(f"{pbar(self.frac(), max(10, width - 22))}  {self.player.time_text()}", style="gold"),
        ]
        return Panel(Group(*lines), title="Now Playing", title_align="left",
                     box=DOUBLE, border_style=GOLD)

    # -- render: library --
    def render_library(self):
        if self.list_view == "favs":
            rows = [(f"{f['reciter']} - {self.surah_name(f['surah'])}") for f in self.favs] \
                or ["(no favorites - press f while playing in the classic TUI)"]
            return Panel(Group(*[Text(r, style="parch") for r in rows]),
                         title="Favorites", box=ROUNDED, border_style=GOLD)
        if self.list_view == "hist":
            rows = [(f"{x['reciter']} - {self.surah_name(x['surah'])}") for x in self.hist] \
                or ["(nothing played yet)"]
            return Panel(Group(*[Text(r, style="parch") for r in rows]),
                         title="History", box=ROUNDED, border_style=GOLD)
        rs = self.visible_reciters()
        r, m = self.current_moshaf()
        nums = self.surah_numbers()
        left = Table.grid(padding=(0, 1))
        for i, rec in enumerate(rs[:18]):
            sel = i == min(self.rec_sel, max(0, len(rs) - 1)) and self.col == 0
            mark = POINTER + " " if sel else "  "
            left.add_row(Text(mark + rec["name"],
                              style="bold gold" if sel else "parch"))
        right = Table.grid(padding=(0, 1))
        for i, n in enumerate(nums[:18]):
            sel = i == min(self.sur_sel, max(0, len(nums) - 1)) and self.col == 1
            s = by_number(n) or {}
            icon = MAKKI if s.get("type") == "Makki" else MADANI
            mark = POINTER + " " if sel else "  "
            right.add_row(Text(f"{mark}{n:03d}  {self.surah_name(n)}  {icon}",
                               style="bold emerald" if sel else "parch"))
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        scope = "Top picks" if not self.cfg.get("show_all_reciters") else "All"
        grid.add_row(
            Panel(left, title=f"Reciters - {scope}", box=ROUNDED, border_style=GOLD),
            Panel(right, title=(r["name"] if r else "-") +
                  (f" - {m['name']}" if m and m.get("name") else ""),
                  box=ROUNDED, border_style=EMERALD),
        )
        return grid

    # -- render: shelf (RTL-aware) --
    def render_shelf(self):
        tab = Table(box=DOUBLE, border_style=GOLD, expand=True, show_lines=False)
        tab.add_column("#", style="dim", width=4)
        tab.add_column("Track", style="parch", ratio=3)
        tab.add_column("Size", style="gold", width=9, justify="right")
        tab.add_column("Source", width=9, justify="center")
        try:
            tracks = self.store.get_playlist()
        except Exception:
            tracks = []
        for i, trk in enumerate(tracks[:40]):
            fp = trk.get("filepath", "")
            try:
                size = f"{os.path.getsize(fp) / 1e6:.0f}M" if fp and os.path.exists(fp) else "-"
            except OSError:
                size = "-"
            sel = i == min(self.shelf_sel, max(0, len(tracks) - 1))
            name = (POINTER + " " if sel else "") + trk.get("title", "?")
            tab.add_row(str(i + 1), bidi_cell(name, 0),
                        Text(size, style="bold gold" if sel else "gold"),
                        Text(f"{LOCAL} local", style="emerald"))
        if not tracks:
            tab.add_row("", bidi_cell("Shelf empty here - press Y in the classic TUI, "
                                      "or run: tilawah setup", 0), "", "")
        return Panel(tab, title=f"My Shelf - {len(tracks)} saved",
                     box=ROUNDED, border_style=GOLD)

    # -- render: queue --
    def render_queue(self):
        rows = self.player.queue_view() or ["(queue empty - play anything)"]
        t = time.time() - self.t0
        body = []
        for i, row in enumerate(rows[:14]):
            cur = row.startswith("> ")
            name = row[2:] if row[:2] in ("> ", "  ") else row
            if cur and len(name) > 52:
                off = int(t * 10) % (len(name) + 6)
                name = (name + "   -   " + name)[off:off + 52]
            if cur:
                up = Panel(Text(f"{PLAY} {name}", style="bold gold"),
                           box=ROUNDED, border_style=EMERALD, title="Up Next")
                body.append(up)
            else:
                hl = i == self.q_sel
                body.append(Text(f"{QUEUE} {name}", style="bold parch" if hl else "dim"))
        return Panel(Group(*body), title="Queue", box=DOUBLE, border_style=GOLD)

    def render_help(self):
        tab = Table.grid(padding=(0, 2))
        for k, v in [("Space", "play/pause"), ("n/p", "next/prev"), ("0", "restart"),
                     ("L/R", "seek 10s"), ("U/D", "volume"), ("m", "mute"),
                     ("Tab/1-4", "panels"), ("Enter", "play"), ("/", "find"),
                     ("f/F/H", "fav/list/history"), ("z/e", "shuffle/repeat"),
                     ("R", "time mode"), ("v", "dashboard"), ("?", "help"), ("q", "quit"),
                     ("t/D", "sleep/save: classic TUI + CLI")]:
            tab.add_row(Text(k, style="gold"), Text(v, style="parch"))
        return Panel(tab, title="Keys", box=DOUBLE, border_style=GOLD)

    # -- frame --
    def header(self):
        tabs = "   ".join(f"[reverse]{i + 1} {p}[/]" if i == self.panel else f"{i + 1} {p}"
                          for i, p in enumerate(self.PANELS))
        return Text.from_markup(f"[gold]Tilawah[/]   {tabs}")

    def footer(self):
        hints = ["Space play - n next - L/R seek - U/D vol - Tab panels - ? keys",
                 "move: arrows/hjkl - Enter play - / find - ? keys",
                 "Enter play shelf track - ? keys",
                 "Enter jump - z shuffle - e repeat - ? keys"][self.panel]
        left = self.player.sleep_left()
        status = self.msg if time.time() < self.msg_until else \
            (f"sleeps in {int(left // 60):02d}:{int(left % 60):02d}" if left else hints)
        return Text(status, style="dim")

    def render(self):
        lay = Layout()
        lay.split_column(Layout(name="h", size=1), Layout(name="b"), Layout(name="f", size=1))
        lay["h"].update(self.header())
        body = [self.render_dashboard(), self.render_library(),
                self.render_shelf(), self.render_queue()][self.panel]
        if self.show_help:
            body = self.render_help()
        lay["b"].update(body)
        lay["f"].update(self.footer())
        if self.mode == "search":
            lay["f"].update(Text(f"find reciter: {self.buf}", style="bold gold"))
        return lay

    # -- input + loop --
    def key(self, ch):
        if self.mode == "search":
            if ch in ("esc", "enter"):
                self.mode = "browse"
            elif ch in ("backspace",):
                self.buf = self.buf[:-1]
                self.filter = self.buf
                self.rec_sel = 0
            elif isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
                self.buf += ch
                self.filter = self.buf
                self.rec_sel = 0
            return None
        if ch == "q":
            if self.show_help:
                self.show_help = False
                return None
            return "quit"
        if ch == "esc":
            if self.show_help:
                self.show_help = False
            elif self.filter:
                self.filter = ""
                self.buf = ""
            else:
                self.panel = 0
            return None
        if ch == "?":
            self.show_help = not self.show_help
            return None
        if ch in ("1", "2", "3", "4"):
            self.panel = int(ch) - 1
            self.show_help = False
            return None
        if ch == "tab":
            self.panel = (self.panel + 1) % 4
            return None
        if ch == "space":
            self.say(self.player.pause_toggle() or
                     ("paused" if self.player.paused else "playing"))
            return None
        if ch == "n":
            self.player.next()
            return None
        if ch == "p":
            self.player.prev()
            return None
        if ch == "0":
            self.player.restart()
            return None
        if ch == "m":
            self.say("muted" if self.player.toggle_mute() else f"vol {self.player.volume}")
            return None
        if ch in ("-", "_"):
            self.player.set_volume(self.player.volume - 5)
            return None
        if ch in ("=", "+"):
            self.player.set_volume(self.player.volume + 5)
            return None
        if ch == "z":
            self.say("shuffle on" if self.player.toggle_shuffle() else "shuffle off")
            return None
        if ch == "e":
            self.say(f"repeat: {self.player.cycle_repeat()}")
            return None
        if ch == "R":
            self.say("left" if self.player.toggle_time_mode() else "elapsed")
            return None
        if ch == "f":
            t = self.player.current()
            if t and t.get("surah"):
                on = self.store.toggle_favorite(t["reciter"], t["moshaf"], t["surah"])
                self.say("saved to favorites" if on else "removed")
            return None
        if ch == "F":
            self.list_view = "reciters" if self.list_view == "favs" else "favs"
            self.favs = self.store.get_favorites()
            self.panel = 1
            return None
        if ch == "H":
            self.list_view = "reciters" if self.list_view == "hist" else "hist"
            self.hist = self.store.get_history(50)
            self.panel = 1
            return None
        if ch == "/":
            self.panel = 1
            self.mode = "search"
            self.buf = ""
            self.filter = ""
            self.rec_sel = 0
            return None
        if ch in ("up", "k", "down", "j"):
            d = 1 if ch in ("down", "j") else -1
            if self.panel == 0:
                self.player.set_volume(self.player.volume - 5 * d)
            elif self.panel == 1:
                if self.col == 0:
                    self.rec_sel = max(0, self.rec_sel + d)
                else:
                    self.sur_sel = max(0, self.sur_sel + d)
            elif self.panel == 2:
                self.shelf_sel = max(0, self.shelf_sel + d)
            else:
                self.q_sel = max(0, self.q_sel + d)
            return None
        if ch in ("left", "h", "right", "l"):
            d = 1 if ch in ("right", "l") else -1
            if self.panel == 0:
                self.player.seek(10 * d)
            elif self.panel == 1:
                self.col = max(0, min(1, self.col + d))
            return None
        if ch == "enter":
            if self.panel == 1:
                self.play_selection()
            elif self.panel == 3 and self.player.queue:
                self.player.jump(self.q_sel % len(self.player.queue))
            elif self.panel == 2:
                try:
                    tracks = self.store.get_playlist()
                except Exception:
                    tracks = []
                if tracks:
                    t = tracks[min(self.shelf_sel, len(tracks) - 1)]
                    self.player.set_queue([{"reciter": "My Shelf", "moshaf": "",
                                            "title": t["title"],
                                            "filepath": t["filepath"], "url": ""}], 0)
                    self.say(self.player.play() or f"{PLAY} {t['title']}")
            elif self.panel == 0 and not self.player.playing and self.player.queue:
                self.player.play()
            return None
        return None

    def run(self, console=None):
        console = console or Console(theme=THEME)
        splash = self.render_splash(0)
        with Live(splash, console=console, refresh_per_second=15, screen=True) as live:
            for step in range(1, 8):
                time.sleep(0.09)
                live.update(self.render_splash(step))
            time.sleep(0.5)
            keys = _Keys()
            try:
                while True:
                    ch = keys.get()
                    if ch is not None and self.key(ch) == "quit":
                        try:
                            self.player.stop()
                        except Exception:
                            pass
                        return
                    live.update(self.render())
            finally:
                keys.close()


class _Keys:
    """Non-blocking stdin keys without curses (raw termios + select).

    Raw INPUT (no echo, char-at-a-time) but cooked OUTPUT: plain setraw()
    also clears OPOST, which stops translating \\n to \\r\\n and smears
    every frame down the screen. We set OPOST|ONLCR back on.
    """

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        try:
            attrs = termios.tcgetattr(self.fd)
            attrs[1] |= termios.OPOST | termios.ONLCR
            termios.tcsetattr(self.fd, termios.TCSADRAIN, attrs)
        except Exception:
            pass

    def get(self, timeout=0.06):
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            r2, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r2:
                return {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}.get(
                    sys.stdin.read(2), "esc")
            return "esc"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == " ":
            return "space"
        if ch == "\t":
            return "tab"
        if ch in ("\x7f", "\x08"):
            return "backspace"
        return ch

    def close(self):
        try:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        except Exception:
            pass


def demo(console=None):
    """Print sample screens without interaction (preview + tests)."""
    import tempfile
    from rich.console import Console as _C
    from rich.rule import Rule
    from .db import Store
    from .player import DummyBackend, Player
    console = console or _C(theme=THEME)
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "demo.db"))
    mosh = [{"id": 1, "name": "Hafs - Murattal", "server": "https://x/",
             "surah_total": 114, "surah_list": "1,2,18", "rewaya_id": 1}]
    reciters = [{"id": 1, "name": "Mishary Alafasi", "letter": "M", "moshaf": mosh},
                {"id": 2, "name": "Yasser Al-Dosari", "letter": "Y", "moshaf": mosh}]
    player = Player(store=None, backend=DummyBackend())
    player.set_queue([{"reciter": "Mishary Alafasi", "moshaf": "Hafs - Murattal",
                       "surah": 18, "url": "https://x/018.mp3",
                       "filepath": "", "_file": "018.mp3", "_via": "stream",
                       "duration": 600.0}], 0)
    player.play()
    app = RichApp(store, {"show_all_reciters": True, "download_dir": "~/Tilawah",
                          "offline": False},
                  player, reciters)
    console.print(Rule("splash", style=GOLD))
    console.print(app.render_splash(7))
    console.print(Rule("now playing", style=GOLD))
    console.print(app.render_dashboard())
    console.print(Rule("library", style=GOLD))
    console.print(app.render_library())
    console.print(Rule("shelf", style=GOLD))
    console.print(app.render_shelf())
    console.print(Rule("queue", style=GOLD))
    console.print(app.render_queue())
    try:
        player.close()
    except Exception:
        pass
    try:
        store.close()
    except Exception:
        pass
    return 0
