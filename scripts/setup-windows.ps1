# Install Tilawah on Windows (PowerShell).
# Pre-requisite: Python 3.10+ on PATH, pip on PATH.
#
# Usage (in PowerShell):
#   .\scripts\setup-windows.ps1
$ErrorActionPreference = "Stop"

Write-Host "installing audio deps via pip..."
pip install --user yt-dlp windows-curses

Write-Host "installing tilawah from pip..."
pip install --user git+https://github.com/alkokandiy/tilawah.git

Write-Host ""
Write-Host "done."
Write-Host "Still needed (manual):"
Write-Host "  1. mpv   — https://sourceforge.net/projects/mpv-player-windows/files/64bit/"
Write-Host "  2. ffmpeg — https://www.gyan.dev/ffmpeg/builds/"
Write-Host "Add both to your PATH, then run: tilawah tui"
