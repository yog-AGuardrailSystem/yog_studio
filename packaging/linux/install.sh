#!/bin/sh
# Install yogc for the current user (no root): copies it to ~/.local/bin.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest="${YOG_PREFIX:-$HOME/.local}/bin"
mkdir -p "$dest"
install -m 755 "$here/yogc" "$dest/yogc"
echo "yogc installed to $dest/yogc"
case ":$PATH:" in
  *":$dest:"*) ;;
  *) echo "Add it to your PATH, e.g.:  echo 'export PATH=\"$dest:\$PATH\"' >> ~/.profile" ;;
esac
"$dest/yogc" check "$here/policy.yog" alice can_delete database_1 || true
