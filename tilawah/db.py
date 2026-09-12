"""SQLite persistence: catalog cache, history, favorites, positions, playlist.

Why SQLite and not JSON: history/favorites/positions need concurrent,
atomic, queryable updates (e.g. "last 50 plays", "is favorite?") while a
download runs alongside playback. sqlite3 is stdlib, single-file, and honors
XDG via config.data_dir(). Schema version is tracked in `meta`.
"""

import sqlite3
import time
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS reciters (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, letter TEXT DEFAULT '',
  updated_at REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS moshafs (
  id INTEGER PRIMARY KEY, reciter_id INTEGER NOT NULL, name TEXT DEFAULT '',
  server TEXT NOT NULL, surah_total INTEGER DEFAULT 0, surah_list TEXT DEFAULT '',
  rewaya_id INTEGER DEFAULT 0,
  UNIQUE(reciter_id, id)
);
CREATE TABLE IF NOT EXISTS surahs (
  number INTEGER PRIMARY KEY, name TEXT, arabic TEXT, english TEXT,
  ayahs INTEGER, rtype TEXT
);
CREATE TABLE IF NOT EXISTS history (
  rowid INTEGER PRIMARY KEY AUTOINCREMENT, reciter TEXT, moshaf TEXT,
  surah INTEGER, started_at REAL, seconds INTEGER DEFAULT 0, source TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS favorites (
  reciter TEXT, moshaf TEXT, surah INTEGER, added_at REAL,
  PRIMARY KEY (reciter, moshaf, surah)
);
CREATE TABLE IF NOT EXISTS positions (
  reciter TEXT, moshaf TEXT, surah INTEGER, seconds REAL, updated_at REAL,
  PRIMARY KEY (reciter, moshaf, surah)
);
CREATE TABLE IF NOT EXISTS playlist (
  rowid INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT UNIQUE,
  filepath TEXT, added_at REAL
);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cx = sqlite3.connect(str(self.path), check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self.cx.executescript(SCHEMA)
        self.cx.commit()

    def close(self):
        try:
            self.cx.commit()
            self.cx.close()
        except Exception:
            pass

    # -- meta --
    def meta_get(self, key, default=None):
        r = self.cx.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def meta_set(self, key, value):
        self.cx.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, str(value)))
        self.cx.commit()

    # -- catalog cache --
    def save_reciters(self, reciters):
        now = time.time()
        for r in reciters:
            self.cx.execute(
                "INSERT OR REPLACE INTO reciters(id,name,letter,updated_at) VALUES(?,?,?,?)",
                (r["id"], r["name"], r.get("letter", ""), now))
            for m in r.get("moshaf", []):
                self.cx.execute(
                    """INSERT OR REPLACE INTO moshafs
                       (id,reciter_id,name,server,surah_total,surah_list,rewaya_id)
                       VALUES(?,?,?,?,?,?,?)""",
                    (m["id"], r["id"], m.get("name", ""), m.get("server", ""),
                     m.get("surah_total", 0), m.get("surah_list", ""),
                     m.get("rewaya_id", 0)))
        self.meta_set("catalog_updated_at", str(now))
        self.cx.commit()

    def load_reciters(self):
        rows = self.cx.execute("SELECT * FROM reciters ORDER BY name").fetchall()
        out = []
        for r in rows:
            ms = self.cx.execute("SELECT * FROM moshafs WHERE reciter_id=?", (r["id"],)).fetchall()
            out.append({"id": r["id"], "name": r["name"], "letter": r["letter"],
                        "moshaf": [dict(m) for m in ms]})
        return out

    def save_suwar(self, suwar):
        for s in suwar:
            self.cx.execute(
                """INSERT OR REPLACE INTO surahs(number,name,arabic,english,ayahs,rtype)
                   VALUES(?,?,?,?,?,?)""",
                (s.get("id"), s.get("name"), s.get("name"), s.get("name"),
                 0, "Makki" if s.get("makkia") else "Madani"))
        self.cx.commit()

    # -- history / favorites / positions --
    def add_history(self, reciter, moshaf, surah, seconds=0, source="stream"):
        self.cx.execute(
            "INSERT INTO history(reciter,moshaf,surah,started_at,seconds,source) VALUES(?,?,?,?,?,?)",
            (reciter, moshaf, surah, time.time(), seconds, source))
        self.cx.commit()

    def get_history(self, limit=50):
        return [dict(r) for r in self.cx.execute(
            "SELECT * FROM history ORDER BY started_at DESC LIMIT ?", (limit,))]

    def toggle_favorite(self, reciter, moshaf, surah):
        cur = self.cx.execute(
            "SELECT 1 FROM favorites WHERE reciter=? AND moshaf=? AND surah=?",
            (reciter, moshaf, surah)).fetchone()
        if cur:
            self.cx.execute("DELETE FROM favorites WHERE reciter=? AND moshaf=? AND surah=?",
                            (reciter, moshaf, surah))
            self.cx.commit()
            return False
        self.cx.execute("INSERT INTO favorites VALUES(?,?,?,?)",
                        (reciter, moshaf, surah, time.time()))
        self.cx.commit()
        return True

    def is_favorite(self, reciter, moshaf, surah):
        return self.cx.execute(
            "SELECT 1 FROM favorites WHERE reciter=? AND moshaf=? AND surah=?",
            (reciter, moshaf, surah)).fetchone() is not None

    def get_favorites(self):
        return [dict(r) for r in self.cx.execute("SELECT * FROM favorites ORDER BY added_at DESC")]

    def save_position(self, reciter, moshaf, surah, seconds):
        self.cx.execute("INSERT OR REPLACE INTO positions VALUES(?,?,?,?,?)",
                        (reciter, moshaf, surah, seconds, time.time()))
        self.cx.commit()

    def get_position(self, reciter, moshaf, surah):
        r = self.cx.execute("SELECT seconds FROM positions WHERE reciter=? AND moshaf=? AND surah=?",
                            (reciter, moshaf, surah)).fetchone()
        return r["seconds"] if r else 0

    def last_position(self):
        r = self.cx.execute("SELECT * FROM positions ORDER BY updated_at DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    # -- personal playlist --
    def upsert_track(self, title, url, filepath=""):
        self.cx.execute(
            "INSERT OR IGNORE INTO playlist(title,url,filepath,added_at) VALUES(?,?,?,?)",
            (title, url, filepath, time.time()))
        if filepath:
            self.cx.execute("UPDATE playlist SET filepath=?, title=? WHERE url=?",
                            (filepath, title, url))
            # same file under an older key (e.g. retitled video): keep newest
            self.cx.execute("DELETE FROM playlist WHERE filepath=? AND url<>?",
                            (filepath, url))
        self.cx.commit()

    def get_playlist(self):
        return [dict(r) for r in self.cx.execute("SELECT * FROM playlist ORDER BY rowid")]
