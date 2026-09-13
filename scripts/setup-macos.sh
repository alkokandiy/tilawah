#!/usr/bin/env bash
# Install Tilawah on macOS via Homebrew + pip.
# Pre-requisite: Homebrew (https://brew.sh).
#
# Usage:
#   bash scripts/setup-macos.sh
set -euo pipefail

if ! command -v brew >/dev/null; then
  echo "homebrew not found. install it first: https://brew.sh" >&2
  exit 1
fi

echo "installing audio deps via brew..."
brew install mpv yt-dlp ffmpeg

echo "installing tilawah from pip..."
pip3 install --user git+https://github.com/alkokandiy/tilawah.git

echo ""
echo "done. type: tilawah"
echo "(if tilawah is not found, add ~/.local/bin to PATH)"
