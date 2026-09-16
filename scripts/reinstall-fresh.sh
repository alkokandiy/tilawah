#!/usr/bin/env bash
# Fresh reinstall of Tilawah WITH the shelf-fetch fix (v1.8.7+).
#
# What it does:
#   1. Removes the old installed tilawah package (needs your sudo password)
#   2. Installs audio/download deps: mpv, yt-dlp, ffmpeg + a JS runtime
#      (node/deno — YouTube challenges need one; the app now also falls
#      back to the android player client so bot-checks don't kill downloads)
#   3. Refreshes yt-dlp to the newest build (old builds get bot-blocked)
#   4. Builds + installs tilawah from THIS source tree (includes the fix)
#   5. Runs `tilawah doctor` so you can verify before downloading
#
# Usage:
#   bash scripts/reinstall-fresh.sh
#
# After it finishes, re-download your shelf yourself with ONE of:
#   tilawah setup            # pre-downloads the whole shelf (takes a while once)
#   tilawah                  # open TUI, press Y to fetch the shelf, Enter on [ ] tracks
#   tilawah shelf            # check saved [x] vs missing [ ] tracks
#
# Notes:
#   - Your shelf files live in ~/Tilawah/Playlist/ (wiped clean before reinstall).
#   - If YouTube rate-limits you (HTTP 429), wait 5-10 min and retry ONE track.
#   - Persistent "Sign in to confirm you're not a bot" = IP flagged; try a
#     different network or pass cookies per `yt-dlp --help | grep -A3 cookies`.
set -euo pipefail

echo "== 1/5 removing old tilawah (if present) =="
if dpkg -l | grep -q '^ii.*tilawah'; then
    sudo apt-get remove -y tilawah
else
    echo "(not installed via apt — skipping remove)"
fi

echo ""
echo "== 2/5 installing deps (mpv, yt-dlp, ffmpeg, js runtime) =="
sudo apt-get update -qq
# deno may not exist on every distro repo — try it, tolerate failure, fall back to nodejs.
sudo apt-get install -y -qq mpv yt-dlp ffmpeg nodejs || sudo apt-get install -y -qq mpv yt-dlp ffmpeg
if ! command -v deno >/dev/null 2>&1; then
    sudo apt-get install -y -qq deno 2>/dev/null || echo "(deno not in apt repos — node covers the JS runtime)"
fi

echo ""
echo "== 3/5 refreshing yt-dlp (YouTube blocks stale builds) =="
sudo yt-dlp --update 2>/dev/null || yt-dlp --update 2>/dev/null || echo "(yt-dlp update skipped — continuing with apt version)"

echo ""
echo "== 4/5 building + installing tilawah from this source =="
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
sh "$ROOT/packaging/build-deb.sh"
DEB="$(ls -t "$ROOT"/tilawah_*_all.deb | head -n 1)"
echo "installing $DEB ..."
sudo apt-get install -y "$DEB"

echo ""
echo "== 5/5 verifying =="
tilawah doctor || true

echo ""
echo "done. Re-download your shelf yourself with:"
echo "  tilawah setup     # full shelf, once"
echo "  tilawah shelf     # verify [x] saved tracks"
echo "  tilawah           # TUI, Y fetches shelf, Enter plays/fetches"
