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

## Round 5 — "really broken" report (2026-09-11)

24. **Verdict first**: reproduced on a fresh profile with real mpv - playback
    works, `k` raises volume, `j` lowers it. The device symptoms (inverted
    keys + dead play) match the pre-1.0.4 build exactly, so the prime suspect
    is an un-upgraded box. Fix: version is now printed on the splash screen
    AND the header (`Tilawah v1.0.5`), so any report can be tied to a build.
25. **Real release-process bug found on the way**: v1.0.4 was tagged without
    bumping code/changelog (app reported 1.0.3). Repaired with retroactive
    changelog entries; CI now fails any tag whose version disagrees with
    `tilawah.__version__` and the changelog head.
26. **First-run honesty**: empty-cache fetch now announces itself on stdout
    (previously a black screen on slow connections); empty catalog gets its
    own message and loading screen; the background catalog refresh retries
    every 60s instead of once, so offline-first launches heal themselves.

## Round 6 — ascii-maxxing (2026-09-10)

27. **Pulse is real data, not decoration**: `nrg.py` scans each saved file
    with ffmpeg ebur128 (background thread, JSON cache keyed by
    path+size+mtime) and the fullscreen/Now visuals follow the recitation's
    energy around the playhead. Three sampling bugs died on the way: (a)
    max-pool resampling let one peak pin every bucket - mean-pooling keeps
    verse/pause structure; (b) fixed linear LUFS map saturated on loud
    YouTube masters (97.6% of samples pinned) - percentile stretch on raw
    LUFS adapts to any mastering; (c) ebur128's 0.5s gating warmup faked
    dynamics - warmup frames dropped.
28. **Splash + frames**: hand-drawn 5x6 block font (big TILAWAH, ASCII-only
    cells), double-line U+2550 borders (single-cell, cursor-safe, unlike
    ambiguous-width glyphs). Every bordered write stays sliced to width per
    the round-2 ghost post-mortem.

## Round 9 — Rich frontend (2026-09-10)

33. **`tilawah/ui_rich.py`**: Rich Live dashboard on the same backend
    (Player/Store/api/nrg shared, zero duplication): parchment/gold/emerald
    palette, Kufic-style splash with fade, dashboard card (gold reciter,
    emerald surah, braille spinner + curve-driven block visualizer, custom
    progress bar), two-pane library (pointer, Makki/Madani icons), RTL-aware
    shelf table, up-next queue card with marquee. Optional dependency
    (`python3-rich`, graceful one-line hint); core stays stdlib-only.
34. **Two real bugs caught live**: raw termios kills ONLCR and smears every
    frame (fixed: raw input, cooked output); search re-entry appended to the
    stale filter in both frontends (fixed: cleared on entry).

## Round 7 — download-before-play + shelf that ships (2026-09-10)

29. **Play gates on fetch**: `Player.on_track_request` hook (also covers
    auto-advance) + TUI fetch overlay with %, MB, ETA and cancel. Cancel
    aborts mid-file via a progress-callback exception; the partial file
    stays and resumes next time. `play_mode = download` default,
    `"stream"` opts out (config or `play --stream`).
30. **Shelf ships with the tool**: the playlist URL is a built-in default
    (overridable), `setup` needs no args now, and fresh devices get a
    one-key `Y` fetch with live count/percent (two-phase: enumerate, then
    download; stoppable). Bundling 344MB into the .deb was rejected:
    slow installs, repo bloat, re-download risk on every update.

## Round 8 — the silent switch (2026-09-10)

31. **Root cause of "shelf won't play"**: starting a fresh queue called
    `Player.play()`, which deliberately no-ops while audio runs - so the
    backend kept the old track while every UI label showed the new one.
    Fresh queues now go through `play_index` (pause/resume keeps `play()`).
    Proven with a recording-backend test, not just eyeballing.
32. **Silence is a bug**: tracks dying seconds in now raise an early-death
    hook ("stopped 2s in - file may be broken, D re-saves it") instead of
    quietly stopping. `tilawah doctor` gained a real audio-chain smoke test
    (synthesized tone through mpv) and a shelf integrity count, so "no
    sound / missing files" reports answer themselves.

## Round 10 — Rich frontend removed (2026-09-10)

35. **Kept the opening + borders, deleted the rest**: the Kufic splash and
    motif divider were ported into the curses TUI (font moved to `art.py`);
    `ui_rich.py`, the `rich` subcommand, its tests and all packaging/docs
    traces are gone. One TUI to maintain, core back to pure stdlib.

## Round 11 — universal platform (2026-09-10)

36. **Two lines, everywhere**: APT source + install on Debian-likes,
    `install.sh` one-liner from Pages, per-OS commands (dnf/pacman/brew/pip)
    in the README. `dpkg-deb --root-owner-group` for proper package perms.
37. **Hints follow the platform**: dependency messages name the right package
    manager by reading `/etc/os-release` (apt/dnf/pacman/zypper/apk), brew
    on macOS, pip/site links on Windows. Verified by platform-simulation
    tests, not by owning five machines.
38. **Windows/macOS honesty**: curses import stub keeps CLI/tests alive where
    curses is absent (TUI refuses with the windows-curses fix); XDG dirs map
    to APPDATA/LOCALAPPDATA on Windows. CI now runs the suite on
    ubuntu + macos + windows. Windows TUI and macOS runs are best-effort and
    untested on real hardware - stated, not implied.
## Round 13 — About tab (2026-09-10)
42. **Hadith refs verified, not recalled**: Bukhari 5050 and Tirmidhi 2910
    wordings/numbers checked against sunnah.com before shipping.
43. **Channels are data**: uploader names fetched per video id from YouTube
    (31 unique); videos that left the playlist still credit correctly.

## Round 12 — shelf that ships (2026-09-10)

40. **Shelf is a catalog, not a folder listing**: hardcoded 36 video ids
    (stable even when YouTube reorders; 4 already left the playlist yet keep
    working locally). Status resolves DB key -> title -> NN file -> glob;
    local files always win. Enter on missing fetches it (overlay), plays on
    landing, and backfills the rest while you listen.
41. **Key-format lesson**: DB keys carry `#title`, lookups used bare URLs -
    nothing ever matched until indexed by the pre-`#` part. Stale same-file
    keys are now merged on write.

39. **No silent gaps left**: every optional dep either works, warns once with
    the fix (ffmpeg visuals tip), or degrades loudly (dummy backend prints
    NO SOUND). `tilawah doctor` remains the single source of truth.

## Round 14 — systematic reliability pass (2026-09-10)

Seven defects found by pattern sweep + edge probing, each reproduced first:
1. (High) mid-download network errors escaped as raw tracebacks -
   read loop now raises DownloadError.
2. (High) sub-32KB error pages kept on disk poisoned the next Range
   resume (HTML prefix + MP3 tail passed the size check) - junk deleted.
3. (Medium) TUI traceback with no usable terminal (pipes/cron) - clean
   one-liner + exit code 1, player still closed.
4. (Medium) CLI IndexError on reciters with empty moshaf/surah lists -
   `_pick_moshaf` helper + clean messages in play/download.
5. (Medium) yt-dlp non-UTF8 stdout bytes crashed ingest - errors="replace"
   on both Popen and list_entries paths.
6. (Low) mpv IPC socket collided across Players in one process, and lived
   in hardcoded /tmp - unique suffix + tempfile.gettempdir().
7. (Low) Arabic output crashed strict-locale terminals - stdio reconfigured
   to backslashreplace at startup.
Reviewed, no change: api MIN_GAP thread race (politeness only), ffplay
mid-session binary removal (absurdly unlikely, paths guarded), _watch
teardown spin (daemons die with process, no C modules in that path).

## Round 15 — pause-trap + label truth (2026-09-10)

44. **Auto-play now announces itself** ("playing X"): users mashed Space on
    silence and paused what had just started, then needed Space again -
    matching both reported bugs without any engine fault (switching verified
    clean via headless-mpv + App-level probes).
45. **Space during fetch reports progress** instead of vanishing silently.
46. **Source labels describe what plays**: cached file + stream URL used to
    print "stream" while mpv played the file. `_resolve` now labels by the
    backend's actual pick.
