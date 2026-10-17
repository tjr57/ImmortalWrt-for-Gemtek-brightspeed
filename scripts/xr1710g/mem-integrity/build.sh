#!/bin/sh
# Bounded offline build and self-qualification for xr-mem-integrity.
#
# The host build proves the portable detection/classification logic. The
# qemu-aarch64 static run proves the aarch64-only paired-ldp access path,
# which the host build cannot exercise. Nothing here touches a device.
#
# Usage: build.sh [output-dir]
# Exit status is non-zero if any required step fails.
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
TC="$ROOT/staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl"
OUT="${1:-/tmp/xr-mem-integrity-qa}"
QEMU="${QEMU_AARCH64:-qemu-aarch64-static}"
CFLAGS="-O2 -Wall -Wextra -Werror -std=gnu11"
rc_all=0

export STAGING_DIR="$TC"
mkdir -p "$OUT" || exit 1

step() { printf '== %s ==\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; rc_all=1; }

step "host build"
gcc $CFLAGS -o "$OUT/host" "$HERE/xr-mem-integrity.c" || fail host-build

step "host selftest"
"$OUT/host" --selftest --out "$OUT/selftest-host.json" && echo "host selftest PASS" \
	|| fail host-selftest

step "host short run"
"$OUT/host" --size 8388608 --seconds 30 \
	--patterns zero,ones,walk-one,addr,prng \
	--out "$OUT/shortrun-host.json"
shortrc=$?
[ "$shortrc" -eq 0 ] && echo "host short run PASS" || fail "host-shortrun-rc=$shortrc"

step "pagemap path (requires root)"
if [ "$(id -u)" -eq 0 ]; then
	"$OUT/host" --size 1048576 --seconds 20 --patterns zero \
		--out "$OUT/shortrun-host-root.json"
	pgrc=$?
	[ "$pgrc" -eq 0 ] && echo "root short run PASS" || fail "root-shortrun-rc=$pgrc"
else
	echo "SKIP not root: physical-address reporting stays unqualified in this run"
fi

step "arm build"
"$TC/bin/aarch64-openwrt-linux-musl-gcc" $CFLAGS -static \
	-o "$OUT/arm-unstripped" "$HERE/xr-mem-integrity.c" || fail arm-build
cp "$OUT/arm-unstripped" "$OUT/xr-mem-integrity-arm" || fail arm-copy
"$TC/bin/aarch64-openwrt-linux-musl-strip" "$OUT/xr-mem-integrity-arm" \
	|| fail arm-strip

step "arm selftest under qemu (covers the ldp path)"
if command -v "$QEMU" >/dev/null 2>&1; then
	"$QEMU" "$OUT/xr-mem-integrity-arm" --selftest \
		--out "$OUT/selftest-arm.json" && echo "arm selftest PASS" \
		|| fail arm-selftest
else
	echo "FAIL $QEMU not available: the aarch64 ldp path would stay unqualified"
	rc_all=1
fi

step "digests"
sha256sum "$HERE/xr-mem-integrity.c" "$OUT/arm-unstripped" \
	"$OUT/xr-mem-integrity-arm" | tee "$OUT/digests.txt"
file "$OUT/xr-mem-integrity-arm" | tee "$OUT/file.txt"

printf 'OVERALL_RC=%d\n' "$rc_all"
exit "$rc_all"
