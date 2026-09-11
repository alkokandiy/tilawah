#!/bin/sh
# One-line Tilawah install (Debian/Ubuntu/Kali/Mint/...):
#   curl -sSL https://alkokandiy.github.io/tilawah/install.sh | sh
set -eu
if ! command -v python3 >/dev/null; then
  echo "install python3 first, then re-run this script" >&2
  exit 1
fi
URL="$(python3 -c "import json,urllib.request; r=json.load(urllib.request.urlopen('https://api.github.com/repos/alkokandiy/tilawah/releases/latest', timeout=30)); print([a['browser_download_url'] for a in r['assets'] if a['name'].endswith('.deb')][0])")"
echo "fetching $URL"
cd /tmp
curl -sSL -o tilawah-latest.deb "$URL"
sudo apt install ./tilawah-latest.deb
rm -f tilawah-latest.deb
echo "done - type: tilawah"
