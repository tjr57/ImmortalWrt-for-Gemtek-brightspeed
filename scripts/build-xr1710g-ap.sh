#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

jobs="${XR1710G_BUILD_JOBS:-12}"
artifacts="${XR1710G_ARTIFACTS:-$HOME/artifacts/xr1710g}"
mkdir -p "$artifacts"
case "$jobs" in ''|*[!0-9]*|0) echo 'Invalid build job count' >&2; exit 2 ;; esac

# Stop before downloading or compiling if a new source file would be omitted.
python3 scripts/artifact_light_checks.py --root "$PWD" --check-source-tracking

cp xr1710g-ap.feeds.conf feeds.conf
./scripts/feeds update -a > "$artifacts/feeds-update.log" 2>&1
./scripts/feeds install -a > "$artifacts/feeds-install.log" 2>&1
# This unused audio package currently creates a Kconfig recursion through
# conditional FFmpeg dependencies. It is not part of the AP image.
./scripts/feeds uninstall squeezelite > "$artifacts/feeds-exclusions.log" 2>&1
FEED_PATCHES_STRICT=1 bash scripts/apply-feed-patches.sh | tee "$artifacts/feed-patches.log"
bash scripts/fix-stale-golang-host.sh

cp xr1710g-ap.config .config
VERSION_DIST='ImmortalWrt XR1710G AP' bash scripts/set-build-version.sh .config
make defconfig > "$artifacts/defconfig.log" 2>&1
if grep -Eq 'recursive dependency|^.*error:' "$artifacts/defconfig.log"; then
	cat "$artifacts/defconfig.log" >&2
	exit 1
fi
grep -Fqx 'CONFIG_TARGET_airoha_an7581_DEVICE_gemtek_xr1710g=y' .config
if grep -Eq '^CONFIG_(TARGET_airoha_an7581_DEVICE|TARGET_DEVICE_airoha_an7581_DEVICE)_.*-ubi=y$' .config; then
	echo 'Unexpected alternate NAND layout selected' >&2
	exit 1
fi
bash scripts/check-gemtek-profile-isolation.sh --config .config
cp .config "$artifacts/ap-config.full"
./scripts/diffconfig.sh > "$artifacts/ap-config.diff"
python3 scripts/artifact_light_checks.py --root "$PWD" \
    --source-patch "$artifacts/ap-source.patch" > "$artifacts/source-patch-check.json"
git rev-parse HEAD > "$artifacts/source-base.txt"
cp xr1710g-ap.feeds.conf "$artifacts/feeds.lock.conf"

make download -j"$jobs" > "$artifacts/download.log" 2>&1
make world -j"$jobs" > "$artifacts/build.log" 2>&1

target_dir='bin/targets/airoha/an7581'
bash scripts/check-firmware-artifacts.sh --config .config --directory "$target_dir"
# Reject stale manifests from older AP builds. Both images and profiles.json
# must identify the exact configured version and have matching size/SHA256.
version="$(sed -n 's/^CONFIG_VERSION_NUMBER="\(.*\)"$/\1/p' .config)"
test -n "$version"
artifact_report="$artifacts/$version-artifact-qa.json"
python3 scripts/artifact_light_checks.py --root "$PWD" --version "$version" \
    --report "$artifact_report"
manifest="$(python3 - "$artifact_report" <<'PY'
import json
import sys
record = json.load(open(sys.argv[1]))
if record.get('passed') is not True:
    raise SystemExit('Artifact safety gate failed')
print(record['manifest'])
PY
)"
kernel_configs=(build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-*/.config)
[[ ${#kernel_configs[@]} -eq 1 && -f "${kernel_configs[0]}" ]]
kernel_config="${kernel_configs[0]}"
test -n "$manifest"
bash scripts/check-gemtek-profile-isolation.sh --config .config --kernel-config "$kernel_config" --manifest "$manifest"
grep -Eq '^xr1710g-ap-defaults[[:space:]]' "$manifest"
echo "AP firmware built and checked in $PWD/$target_dir"
