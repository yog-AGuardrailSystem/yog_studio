#!/usr/bin/env bash
# Build the downloadable yogc packages from the vendored engine (engine/c_front) into OUT_DIR:
#   yog-setup-windows-x64.exe   Windows installer (NSIS, per-user, adds yogc to PATH)
#   yog-windows-x64.zip         the same files without an installer
#   yog-linux-x64.tar.gz        static Linux build + install.sh
#   SHA256SUMS.txt, manifest.json
# Needs: gcc, x86_64-w64-mingw32-gcc, makensis, zip, tar, sha256sum. The Dockerfile's `dist` stage installs them;
# locally:  docker run --rm -v "$PWD":/src:ro -v /tmp/out:/out debian:bookworm sh -c \
#   'apt-get update -qq && apt-get install -y -qq gcc gcc-mingw-w64-x86-64 nsis zip >/dev/null && /src/scripts/build_downloads.sh /out'
set -euo pipefail

OUT=${1:?usage: build_downloads.sh OUT_DIR}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
C="$ROOT/engine/c_front"
PKG="$ROOT/packaging"
COMMIT=$(sed -n 's/^commit:[[:space:]]*\([0-9a-f]\{7\}\).*/\1/p' "$C/VERSION")
[ -n "$COMMIT" ] || { echo "no commit in $C/VERSION" >&2; exit 1; }
SRCS="src/lexer/lexer.c src/parser/*.c src/sema/*.c src/ir/*.c src/vm/*.c src/api/yog.c tools/yogc.c"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
WIN="$WORK/yog-windows-x64"
LIN="$WORK/yog-linux-x64"
mkdir -p "$WIN" "$LIN"

crlf() { sed 's/\r$//; s/$/\r/' "$1"; }                   # Windows text files
readme() { sed "s/@COMMIT@/$COMMIT/" "$PKG/common/README.txt"; }

# ---- compile (static, stripped); the sources are only read
( cd "$C" && x86_64-w64-mingw32-gcc -std=c11 -O2 -static -s -I src -I include $SRCS -o "$WIN/yogc.exe" )
( cd "$C" && gcc -std=c11 -O2 -static -s -I src -I include $SRCS -o "$LIN/yogc" )

# ---- sanity: the Linux build decides the sample policy correctly; the Windows build is a PE executable
"$LIN/yogc" check "$PKG/common/policy.yog" alice can_delete database_1 | grep -q '^ALLOW|' \
  || { echo "linux yogc: alice should be ALLOWED" >&2; exit 1; }
set +e; "$LIN/yogc" check "$PKG/common/policy.yog" bob can_delete database_1 >/dev/null; rc=$?; set -e
[ "$rc" = 3 ] || { echo "linux yogc: bob should be DENIED (exit 3), got $rc" >&2; exit 1; }
[ "$(head -c 2 "$WIN/yogc.exe")" = "MZ" ] || { echo "yogc.exe is not a Windows executable" >&2; exit 1; }

# ---- package contents
readme | crlf /dev/stdin > "$WIN/README.txt"
crlf "$C/LICENSE" > "$WIN/LICENSE.txt"
crlf "$PKG/common/policy.yog" > "$WIN/policy.yog"
readme > "$LIN/README.txt"
cp "$C/LICENSE" "$LIN/LICENSE"
cp "$PKG/common/policy.yog" "$LIN/policy.yog"
install -m 755 "$PKG/linux/install.sh" "$LIN/install.sh"
chmod 644 "$WIN"/*.txt "$WIN/policy.yog" "$LIN/README.txt" "$LIN/LICENSE" "$LIN/policy.yog"
chmod 755 "$WIN/yogc.exe" "$LIN/yogc" "$WIN" "$LIN"

# ---- Windows installer + zip, Linux tarball (fixed timestamps/owners so rebuilds of the same commit match)
makensis -V2 -DVERSION="$COMMIT" -DSRC="$WIN" -DOUTFILE="$OUT/yog-setup-windows-x64.exe" "$PKG/windows/yog.nsi"
[ "$(head -c 2 "$OUT/yog-setup-windows-x64.exe")" = "MZ" ] || { echo "installer is not a Windows executable" >&2; exit 1; }
find "$WORK" -exec touch -h -d '2026-01-01 00:00:00' {} +
( cd "$WORK" && rm -f "$OUT/yog-windows-x64.zip" && zip -qrX "$OUT/yog-windows-x64.zip" yog-windows-x64 )
tar -C "$WORK" --owner=0 --group=0 --numeric-owner --sort=name -czf "$OUT/yog-linux-x64.tar.gz" yog-linux-x64

# ---- checksums + manifest
cd "$OUT"
FILES="yog-setup-windows-x64.exe yog-windows-x64.zip yog-linux-x64.tar.gz"
sha256sum $FILES > SHA256SUMS.txt
entry() {   # name platform kind label
  printf '    {"name": "%s", "platform": "%s", "kind": "%s", "label": "%s", "size": %s, "sha256": "%s"}' \
    "$1" "$2" "$3" "$4" "$(stat -c %s "$1")" "$(sha256sum "$1" | cut -d' ' -f1)"
}
{
  printf '{\n  "engine_commit": "%s",\n  "built_at": "%s",\n  "files": [\n' "$COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  entry yog-setup-windows-x64.exe windows installer "Windows installer (64-bit)"; printf ',\n'
  entry yog-windows-x64.zip windows zip "Windows zip, no installer (64-bit)"; printf ',\n'
  entry yog-linux-x64.tar.gz linux tarball "Linux, static (x86-64)"; printf '\n'
  printf '  ]\n}\n'
} > manifest.json
echo "built in $OUT:"; cat SHA256SUMS.txt
