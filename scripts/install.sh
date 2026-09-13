#!/usr/bin/env bash
# Install Tilawah on Debian/Ubuntu via APT (recommended).
# Also works for: Kali, Linux Mint, Pop!_OS, Raspberry Pi OS, Zorin.
#
# Usage:
#   bash scripts/install.sh
set -euo pipefail

echo "setting up Tilawah APT source..."
echo "deb [trusted=yes] https://alkokandiy.github.io/tilawah/ ./" \
  | sudo tee /etc/apt/sources.list.d/tilawah.list > /dev/null

echo "installing tilawah + audio deps..."
sudo apt-get update -qq
sudo apt-get install -y -qq tilawah mpv yt-dlp ffmpeg

echo ""
echo "done. type: tilawah"
