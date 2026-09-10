# DECISIONS.md — engineering calls made where the spec was ambiguous

Spec was truncated after "Default keymap (ship this, allow rebinding later)",
so the keymap below is mine; everything else follows the brief literally.

1. **Language/runtime: Python 3.10+, stdlib-only core.** No click/tqdm/textual
   dependency — `apt install mpv` + `pip install .` is enough. `curses`,
   `sqlite3`, `urllib`, `tomllib` cover TUI/storage/HTTP/config. Verified API
   shapes live (2026-09-09) before writing the client; sample code that did
   the verification is essentially `tests/test_tilawah.py::ApiShapeTest`.

2. **SQLite, not JSON** (`~/.local/share/tilawah/tilawah.db`, respects XDG).
   History/favorites/positions/playlist need atomic concurrent updates while
   downloads run beside playback; sqlite3 is stdlib and single-file.

3. **Audio URL = `{server}{NNN}.mp3`** (zero-padded 3 digits). Verified with
   HEAD requests: `server6…/akdr/001.mp3` and `server9…/akrm/114.mp3` both
   return HTTP 200 `audio/mpeg` with `Accept-Ranges: bytes` (=> resume works).

4. **Playback backends: mpv (IPC) → ffplay → dummy.** mpv gives full
   seek/volume via `--input-ipc-server` JSON IPC. ffplay fallback restarts
   with `-ss` for seeks (documented limitation). Dummy backend simulates the
   clock so queue/shuffle/repeat/sleep-timer stay usable with no audio stack
   (servers, CI, pre-`apt install mpv`). Missing binaries print a one-line
   `sudo apt install …` hint, never a traceback (`tilawah/doctor.py`
   convention implemented in `deps.py`; `tilawah doctor`).

5. **Reciter photos: the API serves none** (no photo fields in v3 responses,
   no portraits on /eng/ listing pages — only logo/banner images). So
   `photo_to_ansi()` renders a provided image when given, but per-reciter art
   is a deterministic geometric medallion (Pillow-free), cached per-photo as
   `.ans` under XDG cache when Pillow is present. Stated openly here and in
   README, not silently stubbed.

6. **Keymap** (shipped, rebinding later via config table — post-v1):
   Space play/pause, s stop, n/p next/prev, 0 restart, ←/→ or h/l seek ∓10s,
   ↑/↓ volume, z shuffle, e repeat, Tab panels, / filter, f/F favorite/list,
   H history, d download selected, D playlist, t/T sleep set/cancel,
   g theme, v fullscreen, o move-box, ? help, q quit.

7. **TUI = curses, single binary, no daemon.** Movable floating now-playing
   box (`o` + arrows), fullscreen motif view (`v`), splash screen, ambient
   8-point-star/rub-el-hizb animation at configurable fps,
   `reduced_motion=true` (or `--calm`) drops to a static frame at ~2fps for
   slow terminals/SSH. `--mini` corner-overlay is a stretch goal: NOT in v1
   (says so in README too).

8. **Downloader politeness:** 1 connection, resume via Range, skip cached
   files >32KB, ~0.25–0.4s gaps, Tilawah User-Agent, catalog cached in SQLite.

9. **YouTube shelf:** `yt-dlp` subprocess, audio-only, no re-encode (ffmpeg
   not required), `%(playlist_index)02d - %(title)s` into `~/Tilawah/Playlist`,
   tracks registered in SQLite. Missing yt-dlp → one-line hint.

10. **Distribution:** `pip install .` (console script `tilawah`), `make deb`
    (dpkg-buildpackage, depends: python3, recommends: mpv/yt-dlp/ffmpeg),
    README documents hosting a trivial APT repo with `reprepro`.

## Round 2 (2026-09-09, user feedback)

11. **Top-picks menu (21, not 242).** Curated list incl. Yasser Al-Dosari and
    Mohammed Al-Lohaidan (= Muhammad Al-Luhaidan in API transliteration —
    verified live, there is no "Muhammad Luhaidan" entry). Full catalog one
    keypress away (C / --all). Murattal narration auto-preferred, `w` cycles.
12. **Ghost-text hunt:** a phantom "...ration" fragment haunted the reciter
    list. Root cause: the one unbounded write (66-char header at col 50 on a
    100-col screen) overflowed the screen edge in early paints; ncurses
    differential updates then preserved the wrapped overflow as a ghost.
    Fixed by slicing EVERY write to the visible width; UI text is ASCII-only
    now (markers `>`, `-`, `*`), which also hardens low-color/SSH terminals.
    Plus `locale.setlocale` fallback chain (C.UTF-8) at TUI start.
13. **Smoother streaming:** mpv gets deep cache (80MB/90s readahead),
    reconnect flags, gapless audio; engine prefetches (HEAD) the next track
    and probes durations in background (ffprobe, else HEAD-size estimate);
    EOF grace period stops false track-skips at load.
14. **Player best practices:** mute (m), volume bar, elapsed/remaining toggle
    (R), buffering indicator, kbps readout, resume toast, sleep presets
    (1/2/3 = 15/30/60), background downloads with progress + cancel (x),
    quiet background catalog refresh after launch, filename + source
    ("108.mp3 - stream/saved file") on every track.
15. **Shelf:** `tilawah setup <URL>` saves the playlist URL and pre-downloads
    all 40 tracks (verified: 40/40, 717MB). yt-dlp turned out to be
    preinstalled at /usr/bin/yt-dlp, so no converter websites were needed.
16. **Shrink:** `tilawah shrink-shelf --bitrate 96k [--min-mb N]` re-encodes
    shelf audio with libopus, verifying duration before replacing (a failed
    encode never touches the original; temp file lives beside the source
    because /tmp and /home can be different filesystems). Audit showed pure
    Opus, no cover art — no lossless win exists, so 96k perceptual
    transparency was the honest offer. Result: 454MB -> 344MB, 0 bad files.

## Round 3 — release polish (2026-09-09)

17. **Audit fixes:** mpv zombie on quit (new `Player.close()`, wired into all
    exits); mpv IPC never raises (dead backend degrades, TUI can't crash);
    real `--resume` (rebuilds queue at last position, dead code removed);
    `default_moshaf` config now wired into `play`; `if __name__` moved to end
    of cli.py; ASCII-only everywhere including doctor/shelf output; Store gains
    `close()`; ytpl/downloader dead code removed.
18. **Distribution without root:** `packaging/build-deb.sh` crafts a real
    `.deb` with `dpkg-deb` only (no debhelper): `/usr/bin/tilawah` wrapper +
    package under `/usr/share/tilawah` (stdlib-only, so no venv/pip needed on
    target) + man page + docs. Verified by extracting and running the payload,
    and by REAL mpv playback tests (local file: pos/seek/duration OK; network
    stream playing in <2s with true duration).
19. **`sudo apt install tilawah`:** `packaging/publish-apt.sh` builds
    `apt-repo/` (deb + Packages.gz + Release, GPG-signs when TILAWAH_GPG_KEY
    is set). Host it on any static server/GitHub Pages; clients add one
    sources line. CI (`.github/workflows/release.yml`) runs tests on every
    `v*` tag and attaches sdist/wheel/.deb to the GitHub release.

## Round 4 — controls & save center (on-device bug reports)

20. **Volume was inverted** (Down/j raised it): movement now takes signed
    up/down and Up/k/w is louder everywhere, Down/j/s quieter. Arrows, hjkl
    and WASD mirror each other; letter-actions keep their meaning only where
    the footer shows it (`d` saves in Reciters, `s` stops in Now) - `w`/`a`
    were scoped to panels where narration-switch/save apply so they never
    swallow movement.
21. **Numbered panels (1-4) + Esc-to-Now**: Tab-only navigation confused new
    users; header shows `1 Now Playing  2 Reciters  3 My Shelf  4 Queue`.
22. **Save center (D)**: one dialog for this surah / whole reciter / Juz 30
    (78-114) / all top picks (two-step confirm), each option showing
    saved/total counts; saving is idempotent (cached files skipped, "already
    saved" when nothing to do); live per-file progress in dialog + status.
23. **Narration scoring**: two moshafs can both be labelled Murattal, so
    preference is now Hafs + completeness, not first-match (Mishary correctly
    defaults to the 114-surah Hafs, not the 6-surah Dorai).
