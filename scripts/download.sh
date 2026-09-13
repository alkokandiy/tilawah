#!/usr/bin/env bash
# Download the latest Tilawah .deb for this machine.
# Works on Linux (amd64/arm64) only — macOS/Windows use pip instead.
#
# Usage:
#   bash scripts/download.sh           # downloads to /tmp/
#   bash scripts/download.sh ~/Desktop # downloads to ~/Desktop/
set -euo pipefail

REPO="alkokandiy/tilawah"
OUTDIR="${1:-/tmp}"

# --- detect arch ---
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)  DEB_ARCH="amd64" ;;
  aarch64|arm64) DEB_ARCH="arm64" ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

# --- find latest .deb on GitHub Releases ---
API="https://api.github.com/repos/$REPO/releases/latest"
DEB_URL="$(python3 -c "
import json, urllib.request, sys
r = json.load(urllib.request.urlopen('$API', timeout=30))
debs = [a['browser_download_url'] for a in r['assets']
        if a['name'].endswith('.deb') and '_all.deb' in a['name']]
if not debs:
    print('no .deb found on latest release', file=sys.stderr); sys.exit(1)
print(debs[0])
" 2>/dev/null)"

DEB_NAME="${DEB_URL##*/}"
echo "downloading $DEB_NAME"
curl -#SL -o "$OUTDIR/$DEB_NAME" "$DEB_URL"
echo "saved: $OUTDIR/$DEB_NAME"
echo "install: sudo apt install ./$OUTDIR/$DEB_NAME"
