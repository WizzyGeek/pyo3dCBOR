#!/usr/bin/env bash
# Used both on the exact published digest and inside cibuildwheel's container.
set -euo pipefail

policy="${1:-${AUDITWHEEL_POLICY:?Missing image policy}}"
arch="${2:-$(uname -m)}"
case "$policy/$arch" in
  manylinux_2_28/x86_64) target=x86_64-unknown-linux-gnu ;;
  musllinux_1_2/x86_64) target=x86_64-unknown-linux-musl ;;
  *) echo "Unsupported image: $policy/$arch" >&2; exit 1 ;;
esac

test "$(uname -m)" = "$arch"
test "$AUDITWHEEL_ARCH" = "$arch"
test "$AUDITWHEEL_POLICY" = "$policy"
test "$CARGO_BUILD_JOBS" = 2
rustc --version | grep -Eq '^rustc 1\.90\.0([[:space:]]|$)'
cargo --version
rustup target list --installed | grep -Fx "$target"
auditwheel --version
for python in cp39 cp310 cp311 cp312 cp313 cp314; do
  "/opt/python/${python}-${python}/bin/python" --version
done
printf 'Verified Linux image %s/%s at %s\n' "$policy" "$arch" "$(date -u +%FT%TZ)"
