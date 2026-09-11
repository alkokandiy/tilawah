"""`tilawah` command line. One binary, no daemon:

  tilawah                        launch the TUI
  tilawah play -r NAME -s N      play a surah (stream or cached file)
  tilawah download -r NAME [-s N | --all]   download audio
  tilawah get-playlist URL       ingest personal Top-40 YouTube playlist
  tilawah shelf                  list personal playlist shelf
  tilawah reciters [--refresh]   list/browse reciters (cached offline)
  tilawah surahs [query]         list/search the 114 surahs
  tilawah favs                   list favorites
  tilawah history                recent plays
  tilawah resume                 resume last position
  tilawah theme NAME             switch theme (night/dawn/minimal)
  tilawah doctor                 dependency + connectivity check
"""

import argparse
import os
import sys
import time

from . import __version__, api, config, deps, downloader
from .db import Store
from .player import Player, auto_backend
from .surahs import SURAHS, search as search_surahs
from . import themes


def ctx():
    cfg = config.load()
    config.ensure_dirs()
    store = Store(config.db_path())
    return cfg, store


def _graceful(player):
    """SIGTERM/SIGINT (timeout, systemd, Ctrl-C) always stop audio first."""
    import signal as _sig

    def _handler(*_a):
        try:
            player.close()
        except Exception:
            pass
        raise SystemExit(143)

    for _s in (_sig.SIGTERM, _sig.SIGINT):
        try:
            _sig.signal(_s, _handler)
        except Exception:
            pass


def get_catalog(store, refresh=False):
    cached = store.load_reciters()
    if cached and not refresh:
        return cached, False
    if not cached:
        # Fresh device: this blocks before the TUI can draw, so say so.
        print("first run: fetching the reciter list from mp3quran.net ...")
    try:
        reciters = api.fetch_reciters()
        store.save_reciters(reciters)
        try:
            store.save_suwar(api.fetch_suwar())
        except Exception:
            pass
        return reciters, True
    except Exception as e:
        if cached:
            print(f"warning: offline ({e}) — using cached catalog.", file=sys.stderr)
            return cached, False
        print(f"error: cannot reach mp3quran.net and no cache yet: {e}", file=sys.stderr)
        return [], False


def cmd_tui(args):
    import curses
    cfg, store = ctx()
    if args.calm:
        cfg["reduced_motion"] = True
    if args.offline:
        cfg["offline"] = True
    if args.theme in themes.names():
        cfg["theme"] = args.theme
    reciters, _ = get_catalog(store, refresh=args.refresh)
    msg = ""
    if not reciters:
        msg = "offline with empty cache — downloads & streaming need connection once"
    player = Player(store=store, backend=auto_backend(args.backend), offline=cfg.get("offline"),
                    cache_dir=config.cache_dir())
    player.volume = int(cfg.get("volume", 80))
    _graceful(player)
    if args.resume:
        _resume_last(store, player, offline=cfg.get("offline"),
                     download_dir=cfg.get("download_dir", "~/Tilawah"))
        if player.current() is not None:
            msg = f"resumed: {player.describe()}"
    from .tui import App
    app = App(store, cfg, player, reciters, config.cache_dir(), status_msg=msg)
    import locale
    for loc in ("", "C.UTF-8", "en_US.UTF-8"):
        try:
            locale.setlocale(locale.LC_ALL, loc)
            break
        except locale.Error:
            continue
    try:
        curses.wrapper(app.run)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            app.close()
        except Exception:
            pass
        player.close()
    cfg["volume"] = player.volume
    try:
        config.save(cfg)
    except Exception:
        pass
    return 0


def _resume_last(store, player, offline=False, download_dir="~/Tilawah"):
    """Rebuild a queue around the last saved position and start it."""
    try:
        last = store.last_position()
    except Exception:
        return
    if not last:
        return
    try:
        from . import api as _api
        reciters = store.load_reciters()
        r = _api.find_reciter(reciters, last.get("reciter", ""))
        if not r or not r.get("moshaf"):
            return
        idx = _api.preferred_moshaf_index(r)
        m = r["moshaf"][idx]
        nums = _api.available_surahs(m)
        surah = last.get("surah") or 0
        if surah not in nums:
            return
        tracks = []
        for n in nums[nums.index(surah):]:
            fp = str(downloader._local_name(download_dir, r["name"], n))
            tracks.append({"reciter": r["name"], "moshaf": m.get("name", ""),
                           "surah": n, "url": _api.audio_url(m["server"], n),
                           "filepath": fp if os.path.exists(fp) else "",
                           "prefer_local": bool(offline)})
        player.offline = offline
        player.set_queue(tracks)
        player.play()
    except Exception:
        pass


def cmd_play(args):
    cfg, store = ctx()
    if args.offline:
        cfg["offline"] = True
    reciters, _ = get_catalog(store)
    if not reciters:
        return 1
    r = api.find_reciter(reciters, args.reciter or cfg.get("default_reciter", ""))
    if not r:
        print(f"reciter not found: {args.reciter!r} — try `tilawah reciters | head`")
        return 1
    m = r["moshaf"][min(args.moshaf if args.moshaf is not None else int(cfg.get("default_moshaf", 0)), len(r["moshaf"]) - 1)]
    nums = api.available_surahs(m)
    start = args.surah if args.surah in nums else nums[0]
    mode = "stream" if args.stream else ("download" if args.download
                                         else ("stream" if str(cfg.get("play_mode", "download")).lower() == "stream" else "download"))
    if mode == "download" and not cfg.get("offline"):
        dest = downloader._local_name(cfg["download_dir"], r["name"], start)
        if not downloader.already_cached(dest):
            print(f"fetching surah {start:03d} first (cached forever after)...")

            def cb(d, t):
                pct = f"{100 * d // t}%" if t else f"{d // 1024}KB"
                print(f"\r  {downloader.bar(d, t)} {pct}", end="", flush=True)

            try:
                downloader.download_surah(m["server"], r["name"], start,
                                          cfg["download_dir"], progress=cb)
                print("  saved")
            except downloader.DownloadError as e:
                print(f"\n  fetch failed ({e}) - streaming instead")
    tracks = []
    for n in nums[nums.index(start):]:
        fp = str(downloader._local_name(cfg["download_dir"], r["name"], n))
        tracks.append({"reciter": r["name"], "moshaf": m.get("name", ""), "surah": n,
                       "url": api.audio_url(m["server"], n),
                       "filepath": fp if os.path.exists(fp) else "",
                       "prefer_local": bool(cfg.get("offline")) or mode == "download"})
    player = Player(store=store, backend=auto_backend(args.backend), offline=cfg.get("offline"),
                    cache_dir=config.cache_dir())
    player.volume = int(cfg.get("volume", 80))
    _graceful(player)
    if args.shuffle:
        player.toggle_shuffle()
    if args.repeat in ("one", "all"):
        player.repeat = args.repeat
    player.set_queue(tracks)
    err = player.play()
    if err:
        print(err)
        player.close()
        return 1
    print(f"playing {r['name']} from surah {start:03d} [{player.backend.name}] — Ctrl-C to stop")
    if args.sleep:
        player.start_sleep(args.sleep)
        print(f"sleep timer: {args.sleep} min")
    try:
        while player.playing:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        player.close()
    return 0


def cmd_download(args):
    cfg, store = ctx()
    reciters, _ = get_catalog(store)
    if not reciters:
        return 1
    if args.reciter:
        r = api.find_reciter(reciters, args.reciter)
        if not r:
            print(f"reciter not found: {args.reciter!r}")
            return 1
        targets = [r]
    else:
        targets = reciters if args.all_reciters else None
        if targets is None:
            print("give --reciter NAME, or --all-reciters (large!).")
            return 1
    total_files = 0
    for r in targets:
        m = r["moshaf"][min(args.moshaf, len(r["moshaf"]) - 1)]
        only = tuple(args.surahs) if args.surahs else ()
        if args.surah and not only:
            only = (args.surah,)
        nums = [s for s in api.available_surahs(m) if (not only or s in set(only))]
        print(f"{r['name']} [{m.get('name','')}]: {len(nums)} file(s)")
        for i, s in enumerate(nums):
            dest = downloader._local_name(cfg["download_dir"], r["name"], s)
            if downloader.already_cached(dest):
                print(f"  [{i+1}/{len(nums)}] {s:03d} cached — skip")
                continue
            def cb(d, t, i=i, s=s, n=len(nums)):
                pct = f"{100*d//t}%" if t else f"{d//1024}KB"
                print(f"\r  [{i+1}/{n}] {s:03d} {downloader.bar(d,t)} {pct}", end="", flush=True)
            try:
                downloader.download_surah(m["server"], r["name"], s, cfg["download_dir"], progress=cb)
                print(f"  ✓ {s:03d}")
                total_files += 1
            except downloader.DownloadError as e:
                print(f"\n  ✗ {s:03d}: {e}")
    print(f"done — {total_files} new file(s) in {cfg['download_dir']}")
    return 0


def cmd_get_playlist(args):
    cfg, store = ctx()
    url = args.url or cfg.get("youtube_playlist_url", "")
    if not url:
        print("no URL given and none in config — usage: tilawah get-playlist <YouTube-playlist-URL>")
        return 1
    from . import ytpl
    try:
        tracks = ytpl.ingest(url, cfg["download_dir"], store=store,
                             max_items=args.max,
                             progress=lambda n, t: print(f"  [{n}] {t}"))
    except ytpl.PlaylistError as e:
        print(e)
        return 1
    print(f"done — {len(tracks)} track(s) on your shelf (`tilawah shelf`, TUI panel Shelf)")
    return 0


def cmd_add_link(args):
    """Paste one link -> audio extracted -> shelf folder."""
    cfg, store = ctx()
    from . import ytpl
    try:
        tracks = ytpl.ingest(args.url, cfg["download_dir"], store=store,
                             max_items=1, single=True,
                             progress=lambda n, t: print(f"  saved: {t}"))
    except ytpl.PlaylistError as e:
        print(e)
        return 1
    if not tracks:
        print("nothing fetched - check the link")
        return 1
    print(f"on your shelf now (`tilawah shelf`, TUI panel 3)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tilawah", description="terminal-native Qur'an audio player")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("tui", help="launch the TUI (default)")
    a.add_argument("--refresh", action="store_true")
    a.add_argument("--offline", action="store_true")
    a.add_argument("--calm", action="store_true", help="reduced motion")
    a.add_argument("--theme", default="")
    a.add_argument("--backend", default=None, choices=["mpv", "ffplay", "dummy"])
    a.add_argument("--resume", action="store_true")
    a.set_defaults(fn=cmd_tui)

    p = sub.add_parser("play", help="play without the TUI")
    p.add_argument("-r", "--reciter", default="")
    p.add_argument("-s", "--surah", type=int, default=0)
    p.add_argument("--moshaf", type=int, default=None)
    p.add_argument("--shuffle", action="store_true")
    p.add_argument("--repeat", default="off", choices=["off", "one", "all"])
    p.add_argument("--sleep", type=int, default=0)
    p.add_argument("--offline", action="store_true")
    p.add_argument("--stream", action="store_true", help="play instantly, no fetch first")
    p.add_argument("--download", action="store_true", help="fetch before play (default)")
    p.add_argument("--backend", default=None, choices=["mpv", "ffplay", "dummy"])
    p.set_defaults(fn=cmd_play)

    d = sub.add_parser("download", help="download surah(s) for offline use")
    d.add_argument("-r", "--reciter", default="")
    d.add_argument("-s", "--surah", type=int, default=0)
    d.add_argument("--surahs", type=int, nargs="*", default=[])
    d.add_argument("--moshaf", type=int, default=0)
    d.add_argument("--all-reciters", action="store_true")
    d.set_defaults(fn=cmd_download)

    g = sub.add_parser("get-playlist", help="download personal YouTube playlist shelf")
    g.add_argument("url", nargs="?")
    g.add_argument("--max", type=int, default=40)
    g.set_defaults(fn=cmd_get_playlist)

    al = sub.add_parser("add-link", help="fetch one link's audio into the shelf")
    al.add_argument("url")
    al.set_defaults(fn=cmd_add_link)

    st = sub.add_parser("setup", help="first-run setup: save YouTube URL + pre-download shelf")
    st.add_argument("url", nargs="?", help="YouTube playlist URL (saved to config)")
    st.add_argument("--max", type=int, default=40)
    st.add_argument("--reciter", default="", help="also pre-download a reciter (default Top-20 pick)")
    st.set_defaults(fn=cmd_setup)

    sh = sub.add_parser("shrink-shelf", help="re-encode shelf audio to save space (duration-verified)")
    sh.add_argument("--bitrate", default="96k", help="target audio bitrate, e.g. 64k, 96k")
    sh.add_argument("--min-mb", type=float, default=0, help="only shrink files bigger than this (MB)")
    sh.set_defaults(fn=cmd_shrink_shelf)

    r = sub.add_parser("reciters", help="list reciters (cached, works offline)")
    r.add_argument("--refresh", action="store_true")
    r.add_argument("--all", action="store_true", help="show all 242 (default: Top 20)")
    r.add_argument("query", nargs="?")
    r.set_defaults(fn=cmd_reciters)

    s = sub.add_parser("surahs", help="list/search the 114 surahs")
    s.add_argument("query", nargs="?")
    s.set_defaults(fn=cmd_surahs)

    f = sub.add_parser("favs", help="list favorites")
    f.set_defaults(fn=cmd_favs)
    hh = sub.add_parser("history", help="recent plays")
    hh.add_argument("--limit", type=int, default=20)
    hh.set_defaults(fn=cmd_history)
    shf = sub.add_parser("shelf", help="list personal playlist shelf")
    shf.set_defaults(fn=cmd_shelf)
    rs = sub.add_parser("resume", help="show last position (TUI resumes automatically)")
    rs.set_defaults(fn=cmd_resume)
    t = sub.add_parser("theme", help="get/set theme")
    t.add_argument("name", nargs="?")
    t.set_defaults(fn=cmd_theme)
    doc = sub.add_parser("doctor", help="dependency + connectivity check")
    doc.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        args = ap.parse_args(["tui"] + (argv or []))
        if not hasattr(args, "fn"):
            args.fn = cmd_tui
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0


def cmd_reciters(args):
    _, store = ctx()
    reciters, fresh = get_catalog(store, refresh=args.refresh)
    if not args.all:
        top, _ = api.curate(reciters)
        reciters = top or reciters
    if args.query:
        q = args.query.lower()
        reciters = [r for r in reciters if q in r["name"].lower()]
    for r in reciters[:250]:
        n = sum(1 for m in r.get("moshaf", []))
        print(f"{r['id']:4d}  {r['name']}  [{n} narration(s)]")
    scope = "all" if args.all else f"Top {len(reciters)} (use --all for everything)"
    print(f"— {len(reciters)} reciter(s), {scope}{' (fresh)' if fresh else ' (cache)'}")
    return 0


def cmd_surahs(args):
    rows = search_surahs(args.query or "")
    for s in rows:
        print(f"{s['number']:3d}  {s['translit']:16s} {s['arabic']:10s} {s['english']}  ({s['ayahs']} ayahs, {s['type']})")
    return 0


def cmd_favs(args):
    _, store = ctx()
    favs = store.get_favorites()
    if not favs:
        print("(no favorites — press f while playing in the TUI)")
    for x in favs:
        print(f"{x['reciter']} — surah {x['surah']:03d}")
    return 0


def cmd_history(args):
    _, store = ctx()
    for x in store.get_history(args.limit):
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(x["started_at"]))
        print(f"{ts}  {x['reciter']} — {x['surah']:03d}  ({x['source']})")
    return 0


def cmd_shelf(args):
    _, store = ctx()
    tracks = store.get_playlist()
    if not tracks:
        print("(empty shelf — run: tilawah get-playlist <YouTube-playlist-URL>)")
    for i, t in enumerate(tracks, 1):
        mark = "x" if t["filepath"] else " "
        print(f"{i:2d}. [{mark}] {t['title']}")
    return 0


def cmd_resume(args):
    _, store = ctx()
    last = store.last_position()
    if not last:
        print("(no saved position yet)")
        return 0
    print(f"{last['reciter']} — surah {last['surah']:03d} @ "
          f"{int(last['seconds']//60):02d}:{int(last['seconds']%60):02d}")
    return 0


def cmd_setup(args):
    """First-run: remember the YouTube URL and pre-download the shelf."""
    from . import ytpl
    cfg = config.load()
    config.ensure_dirs()
    if args.url:
        cfg["youtube_playlist_url"] = args.url
        config.save(cfg)
        print(f"saved playlist URL to {config.config_path()}")
    url = (cfg.get("youtube_playlist_url", "") or "").strip() or ytpl.DEFAULT_PLAYLIST_URL
    if not url:
        print("usage: tilawah setup <YouTube-playlist-URL>  (then it pre-downloads the shelf)")
        return 1
    print("saving your shelf tracks - this takes a while once, then it's yours offline...")
    args.url = url
    rc = cmd_get_playlist(args)
    if rc == 0 and args.reciter:
        args.surah, args.surahs, args.all_reciters, args.moshaf = 0, [], False, 0
        return cmd_download(args)
    return rc


def cmd_shrink_shelf(args):
    """Re-encode shelf files to a smaller bitrate. Each output's duration is
    verified against its original before replacing — a failed encode never
    touches your file."""
    import os
    import subprocess
    ok, hint = deps.ffmpeg()
    if not ok:
        print(hint)
        return 1
    _, store = ctx()
    tracks = [t for t in store.get_playlist() if t["filepath"] and os.path.exists(t["filepath"])]
    small = [t for t in tracks
             if os.path.getsize(t["filepath"]) < args.min_mb * 1024 * 1024]
    tracks = [t for t in tracks if t not in small]
    if not tracks:
        print("nothing to shrink.")
        return 0
    print(f"shrinking {len(tracks)} file(s) to {args.bitrate}"
          + (f" (skipping {len(small)} under {args.min_mb}MB)" if small else "") + " …")
    saved = 0
    for i, t in enumerate(tracks, 1):
        src = t["filepath"]
        before = os.path.getsize(src)
        tmp = os.path.join(os.path.dirname(src), ".tilawah-shrink.tmp.webm")
        try:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", src, "-map", "0:a", "-c:a", "libopus", "-b:a", args.bitrate,
                 "-vbr", "on", tmp],
                timeout=1800)
            if r.returncode != 0 or not os.path.exists(tmp):
                print(f"  [{i}/{len(tracks)}] SKIP (encode failed): {os.path.basename(src)[:50]}")
                continue
            d0, d1 = _duration(src), _duration(tmp)
            if not d0 or abs(d0 - d1) > 2.0:
                print(f"  [{i}/{len(tracks)}] SKIP (duration mismatch): {os.path.basename(src)[:50]}")
                continue
            after = os.path.getsize(tmp)
            if after >= before:
                print(f"  [{i}/{len(tracks)}] SKIP (already smaller): {os.path.basename(src)[:50]}")
                continue
            os.replace(tmp, src)
            saved += before - after
            print(f"  [{i}/{len(tracks)}] {before//1024//1024}M -> {after//1024//1024}M  "
                  f"{os.path.basename(src)[:45]}")
        except subprocess.TimeoutExpired:
            print(f"  [{i}/{len(tracks)}] SKIP (timeout): {os.path.basename(src)[:50]}")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    print(f"done — saved {saved//1024//1024}MB.")
    return 0


def _duration(path):
    import subprocess
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path],
                           capture_output=True, text=True, timeout=60)
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0


def cmd_theme(args):
    cfg = config.load()
    if not args.name:
        print(f"current: {cfg.get('theme')}  (available: {', '.join(themes.names())})")
        return 0
    if args.name not in themes.names():
        print(f"unknown theme {args.name!r} — choose: {', '.join(themes.names())}")
        return 1
    cfg["theme"] = args.name
    config.save(cfg)
    print(f"theme: {args.name}")
    return 0


def cmd_doctor(args):
    print(f"tilawah {__version__}")
    for name, (ok, hint) in deps.status().items():
        print(f"  [{'ok' if ok else 'MISSING'}] {name}" + ("" if ok else f" - {hint}"))
    ok, msg = deps.audio_check()
    print(f"  [{'ok' if ok else 'FAIL'}] sound: {msg}")
    try:
        api.fetch_suwar()
        print("  [ok] mp3quran.net reachable")
    except Exception as e:
        print(f"  [MISSING] mp3quran.net unreachable ({e}) - offline mode will use cache")
    cfg, store = ctx()
    print(f"  config: {config.config_path()}  downloads: {cfg.get('download_dir')}")
    tracks = store.get_playlist()
    if tracks:
        import os
        missing = [t for t in tracks
                   if not (t.get("filepath") and os.path.exists(t["filepath"]))]
        line = f"  shelf: {len(tracks)} registered, {len(tracks) - len(missing)} files present"
        if missing:
            line += f" - {len(missing)} MISSING, re-fetch with: tilawah setup"
        print(line)
    else:
        print("  shelf: empty (press Y in the TUI or run: tilawah setup)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
