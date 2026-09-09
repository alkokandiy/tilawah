#!/bin/sh
# Publish Tilawah as a trivial APT repo you can host anywhere static
# (GitHub Pages, Nginx, S3). Produces apt-repo/ with the .deb + indexes.
#
#   sh packaging/publish-apt.sh
#   # upload apt-repo/ to https://YOUR-HOST/tilawah-apt/
#   # clients run:
#   echo "deb [trusted=yes] https://YOUR-HOST/tilawah-apt/ ./" \
#     | sudo tee /etc/apt/sources.list.d/tilawah.list
#   sudo apt update && sudo apt install tilawah
#
# For a SIGNED repo (no [trusted=yes] needed), set TILAWAH_GPG_KEY to your
# key id and have passphrase-less signing or gpg-agent ready:
#   TILAWAH_GPG_KEY=ABCDEF12 sh packaging/publish-apt.sh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
sh "$ROOT/packaging/build-deb.sh" >/dev/null
REPO="$ROOT/apt-repo"
mkdir -p "$REPO"
cp "$ROOT"/tilawah_*.deb "$REPO/"
rm -f "$REPO"/Packages "$REPO"/Packages.gz "$REPO"/Release "$REPO"/InRelease
(cd "$REPO" && dpkg-scanpackages --multiversion . /dev/null > Packages)
gzip -9kf "$REPO/Packages"
cat > "$REPO/apt-release.conf" <<'EOF'
APT::FTPArchive::Release::Origin "Tilawah";
APT::FTPArchive::Release::Label "Tilawah";
APT::FTPArchive::Release::Suite "stable";
APT::FTPArchive::Release::Codename "tilawah";
APT::FTPArchive::Release::Architectures "all";
APT::FTPArchive::Release::Components "./";
APT::FTPArchive::Release::Description "Tilawah terminal Qur'an player";
EOF
(cd "$REPO" && apt-ftparchive -c apt-release.conf release . > Release)
rm -f "$REPO/apt-release.conf"
if [ -n "${TILAWAH_GPG_KEY:-}" ]; then
  gpg --default-key "$TILAWAH_GPG_KEY" --clearsign -o "$REPO/InRelease" "$REPO/Release"
  gpg --default-key "$TILAWAH_GPG_KEY" -abs -o "$REPO/Release.gpg" "$REPO/Release"
  echo "signed: InRelease + Release.gpg"
else
  echo "unsigned repo (clients use [trusted=yes]; set TILAWAH_GPG_KEY to sign)"
fi
ls -la "$REPO"
