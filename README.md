# Tilawah — terminal-native Qur'an audio player

Stream or play offline 114 surahs from a Top-15 menu of the most-listened
reciters, keep a personal shelf downloaded from YouTube, set a sleep timer —
all in one terminal binary with an Islamic-geometric ambient visual.
No daemon, no heavy dependencies: Python 3.10+ standard library does the
work; `mpv` / `yt-dlp` / `ffmpeg` plug in when present. Saved tracks get a
real rhythm-reactive pulse visualizer (loudness-scanned per file).

## Install

```bash
# 1) From the project's APT server (easiest: updates included)
echo "deb [trusted=yes] https://alkokandiy.github.io/tilawah/ ./" \
  | sudo tee /etc/apt/sources.list.d/tilawah.list
sudo apt update && sudo apt install tilawah

# 2) Grab the .deb from GitHub Releases and install it
sudo apt install ./tilawah_1.0.0-1_all.deb   # pulls python3, suggests mpv/yt-dlp

# 3) From source
pip install .                                 # gives you the `tilawah` command
sudo apt install mpv yt-dlp ffmpeg            # real audio + YouTube + shrinking
```

`tilawah doctor` checks everything and prints the one-line fix for anything
missing. The app never crashes on a missing dependency — it degrades (e.g.
simulated playback until you install mpv).

## Use

```bash
tilawah                          # launch the TUI
tilawah setup <YouTube-URL>      # first run: remember URL + pre-download the shelf
tilawah play -r "Mishary Alafasi" -s 36
tilawah download -r "Mishary Alafasi" -s 36     # one surah
tilawah download -r NAME --surahs 36 37 38      # several
tilawah download -r NAME --all                  # whole reciter
tilawah reciters [query]  |  tilawah surahs [query]   # library (offline OK)
tilawah favs | tilawah history | tilawah shelf | tilawah resume
tilawah shrink-shelf --bitrate 96k              # save disk (duration-verified)
tilawah theme dawn  |  tilawah doctor
tilawah tui --offline --calm     # offline + low-motion (slow SSH)
```

In the TUI press `?` for all keys. The short version: `1-4` jump between
panels, `Enter` plays, `/` finds a reciter, `Space` pauses, `D` opens the
save center (one surah / whole reciter / Juz 30 / all), `v` fullscreen,
`t` sleep timer, `Esc` always walks back to Now Playing, `q` quits.
Movement is arrows, vim `hjkl` or `WASD` - your choice.

## Config & data (XDG)

- `~/.config/tilawah/config.toml` — default reciter/narration, theme
  (night/dawn/minimal), animation (orbit/star/waves), download dir, playlist
  URL, offline mode, sleep default, volume, reduced motion.
- `~/.local/share/tilawah/tilawah.db` — catalog cache, history, favorites,
  positions, shelf (SQLite).
- `~/Tilawah/` — downloaded audio (changeable).

## For maintainers

```bash
make test          # 19-test stdlib suite (no pytest needed)
sh packaging/build-deb.sh       # tilawah_X.Y.Z-1_all.deb, no root, no debhelper
sh packaging/publish-apt.sh     # apt-repo/ ready to upload to any static host
```

Tag `v1.0.0` → GitHub Actions runs tests, builds sdist/wheel + .deb, and
attaches everything to the release (see `.github/workflows/release.yml`).
For a *signed* APT repo: `TILAWAH_GPG_KEY=ABCDEF12 sh packaging/publish-apt.sh`.

## Honest limitations (v1)

- **Reciter photos:** mp3quran.net serves no portraits, so per-reciter art is
  a generated geometric medallion (or your own photo via Pillow). See
  DECISIONS.md.
- **`--mini` corner-overlay mode is not implemented** (stretch goal).
- **Key rebinding via config file is not implemented** (fixed keymap, `?`).
- **ffplay fallback** seeks by restarting with `-ss` — use mpv for full control.
