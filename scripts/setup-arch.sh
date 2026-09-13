#!/usr/bin/env bash
# Install Tilawah on Arch/Manjaro.
#
# Usage:
#   bash scripts/setup-arch.sh
set -euo pipefail

echo "installing audio deps via pacman..."
sudo pacman -S --noconfirm mpv yt-dlp ffmpeg

echo "installing tilawah from pip..."
pip3 install --user git+https://github.com/alkokandiy/tilawah.git

echo ""
echo "done. type: tilawah"
echo "(if tilawah is not found, add ~/.local/bin to PATH)"
