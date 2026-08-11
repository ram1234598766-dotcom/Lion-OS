#!/usr/bin/env bash
# Build the LionOS .deb installer from a Linux launcher binary.
#
# Layout (Debian policy): the `lionos` launcher + the setup manager go into
# /usr/bin; the icon/mime metadata and a desktop entry make it discoverable.
# The install manager itself (lionos setup) provisions QEMU + toolchain and
# builds the disk image, so the package is deliberately small — it carries the
# launcher, not a full OS.
#
# Usage:  build.sh <path-to-lionos-binary> <version> <out-dir>
# Output: <out-dir>/lionos_<version>_amd64.deb

set -euo pipefail

BIN="${1:?path to lionos binary}"
VERSION="${2:?version, e.g. 1.1.0}"
OUT="${3:?output dir}"

ROOT="$(mktemp -d)"
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin"

install -m 0755 "$BIN" "$ROOT/usr/bin/lionos"

cat > "$ROOT/DEBIAN/control" <<EOF
Package: lionos
Version: $VERSION
Section: otherosfs
Priority: optional
Architecture: amd64
Maintainer: Mrityunjay <lionos@users.noreply.github.com>
Description: LionOS launcher + installation manager
 A Rust host-side launcher for the LionOS x86_64 bare-metal kernel.
 'lionos setup' is an interactive installation manager that provisions the
 QEMU + build toolchain (compulsory), lets you pick LionOS components, and
 builds a bootable disk image; 'lionos run' boots it in QEMU.
EOF

mkdir -p "$OUT"
dpkg-deb --build --root-owner-group "$ROOT" "$OUT/lionos_${VERSION}_amd64.deb" >/dev/null
rm -rf "$ROOT"
echo "OK   $(ls -la "$OUT/lionos_${VERSION}_amd64.deb" | awk '{print $5, $9}')"
