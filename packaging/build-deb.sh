#!/bin/sh
# Build a real installable .deb without needing debhelper (works anywhere
# dpkg-deb exists). Output: tilawah_<version>-1_all.deb in the project root.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(python3 -c "import sys; sys.path.insert(0,'$ROOT'); import tilawah; print(tilawah.__version__)")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PKG="$STAGE/tilawah"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/tilawah" \
         "$PKG/usr/share/man/man1" "$PKG/usr/share/doc/tilawah"

cp "$ROOT/packaging/control" "$PKG/DEBIAN/control"
sed -i "s/^Version:.*/Version: $VER-1/" "$PKG/DEBIAN/control"
cp -r "$ROOT/tilawah" "$PKG/usr/share/tilawah/tilawah"
find "$PKG/usr/share/tilawah" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$PKG/usr/bin/tilawah" <<'EOF'
#!/bin/sh
exec python3 -c "import sys; sys.path.insert(0, '/usr/share/tilawah'); from tilawah.cli import main; raise SystemExit(main())" "$@"
EOF
chmod 755 "$PKG/usr/bin/tilawah"

gzip -9c "$ROOT/packaging/tilawah.1" > "$PKG/usr/share/man/man1/tilawah.1.gz"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/tilawah/copyright"
cp "$ROOT/README.md" "$ROOT/DECISIONS.md" "$PKG/usr/share/doc/tilawah/"

OUT="$ROOT/tilawah_${VER}-1_all.deb"
dpkg-deb --root-owner-group --build "$PKG" "$OUT" >/dev/null
echo "built: $OUT"
dpkg-deb -f "$OUT" Package Version Architecture Depends
