#!/usr/bin/env bash
# Build the LionOS macOS .pkg installer from a macOS launcher binary.
#
# A minimal flat package via `pkgbuild`: installs the `lionos` launcher into
# /usr/local/bin (user-accessible, no admin for the binary itself; provisioning
# QEMU/toolchain later is handled by `lionos setup`). The package is tiny — the
# launcher, not the OS.
#
# Usage:  build.sh <path-to-lionos-binary> <version> <out-dir>
# Output: <out-dir>/lionos-<version>.pkg

set -euo pipefail

BIN="${1:?path to lionos binary}"
VERSION="${2:?version, e.g. 1.1.0}"
OUT="${3:?output dir}"

# pkgbuild requires a directory layout rooted at the install location.
ROOT="$(mktemp -d)"
mkdir -p "$ROOT/usr/local/bin"
install -m 0755 "$BIN" "$ROOT/usr/local/bin/lionos"

mkdir -p "$OUT"
pkgbuild \
  --root "$ROOT" \
  --identifier "io.lionos.launcher" \
  --version "$VERSION" \
  --install-location / \
  "$OUT/lionos-${VERSION}.pkg" >/dev/null
rm -rf "$ROOT"
echo "OK   $(ls -la "$OUT/lionos-${VERSION}.pkg" | awk '{print $5, $9}')"
