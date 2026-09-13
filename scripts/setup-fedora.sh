#!/usr/bin/env bash
# Install Tilawah on Fedora/RHEL/CentOS.
#
# Usage:
#   bash scripts/setup-fedora.sh
set -euo pipefail

echo "installing audio deps via dnf..."
sudo dnf install -y mpv yt-dlp ffmpeg

echo "installing tilawah from pip..."
pip3 install --user git+https://github.com/alkokandiy/tilawah.git

echo ""
echo "done. type: tilawah"
echo "(if tilawah is not found, add ~/.local/bin to PATH)"
