#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Reusable AP artifact gate: no make/hardware/network, and no stale find -quit."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import subprocess
from verify_ap4_artifacts import ELF64, FDT, extract_function

# Diff exports cover all tracked files, including staged additions. Reject
# untracked source in these scopes: Git otherwise silently omits new packages,
# patches and build helpers. Unrelated local outputs (for example uc.out) stay
# outside this source-only guard.
SOURCE_PATCH_SCOPES = (
    'scripts', 'package', 'target', 'patches', 'config', 'include', 'tools',
    'toolchain', 'Makefile', 'Config.in', 'rules.mk', 'feeds.conf.default',
    'xr1710g-ap.config', 'xr1710g-ap.feeds.conf',
)

def assert_source_tracking(root):
    missing = subprocess.check_output(
        ['git', 'ls-files', '--others', '--exclude-standard', '-z', '--',
         *SOURCE_PATCH_SCOPES], cwd=root)
    paths = [path.decode('utf-8', 'surrogateescape') for path in missing.split(b'\0') if path]
    if paths:
        raise ValueError('Untracked source would be omitted from ap-source.patch; '
                         'review and git add these paths before building/exporting: '
                         + ', '.join(paths))
    return paths

def source_diff_checked(root):
    assert_source_tracking(root)
    return subprocess.check_output(['git', 'diff', 'HEAD', '--binary'], cwd=root)


def config_value(text, key):
    match = re.search('^' + re.escape(key) + r'="([^"\n]*)"$', text, re.M)
    if not match: raise ValueError('Missing string config: ' + key)
    return match.group(1)

def select_version_artifacts(root, version=None):
    root = Path(root)
    config = (root / '.config').read_text()
    configured = config_value(config, 'CONFIG_VERSION_NUMBER')
    if version is None: version = configured
    if version != configured: raise ValueError('Requested artifact version does not match current .config')
    directory = root / 'bin/targets/airoha/an7581'
    profiles = json.loads((directory / 'profiles.json').read_text())
    if profiles.get('version_code') != config_value(config, 'CONFIG_VERSION_CODE'):
        raise ValueError('profiles.json version_code differs from current .config')
    if profiles.get('version_number') != version:
        raise ValueError('profiles.json belongs to a different/stale version')
    profile = profiles['profiles']['gemtek_xr1710g']
    if profile['supported_devices'] != ['gemtek,xr1710g']:
        raise ValueError('Unexpected alternate profile/layout')
    prefix = profile['image_prefix']
    if Path(prefix).name != prefix or '/' in prefix or '\\' in prefix:
        raise ValueError('Image prefix must be a basename inside the artifact directory')
    if ('-' + version + '-') not in prefix or not prefix.endswith('-gemtek_xr1710g'):
        raise ValueError('Image prefix does not identify the exact version/primary profile')
    result = {'version': version, 'version_code': profiles.get('version_code'), 'prefix': prefix, 'directory': directory, 'profile': profile}
    for kind, suffix in [('sysupgrade', '-squashfs-sysupgrade.itb'), ('recovery', '-initramfs-recovery.itb'), ('manifest', '.manifest')]:
        # Exact profile prefix, exactly one matching artifact: old versions and
        # alternate profiles cannot accidentally satisfy this selection.
        matches = list(directory.glob(prefix + suffix))
        if len(matches) != 1: raise ValueError('Expected one ' + kind + ' artifact for ' + prefix)
        result[kind] = matches[0]
    expected_names = {result['sysupgrade'].name, result['recovery'].name}
    if len(profile['images']) != 2 or {item['name'] for item in profile['images']} != expected_names:
        raise ValueError('Expected exactly the selected sysupgrade and recovery metadata records')
    for image in profile['images']:
        if image['name'] not in {result['sysupgrade'].name, result['recovery'].name}:
            raise ValueError('Unexpected image in selected profile')
        data = (directory / image['name']).read_bytes()
        if len(data) != image['size'] or hashlib.sha256(data).hexdigest() != image['sha256']:
            raise ValueError('Selected image size/hash differs from profiles.json')
    return result

def check_ap_build_artifacts(root, version=None):
    root = Path(root)
    selected = select_version_artifacts(root, version)
    details=(root/'target/linux/generic/kernel-6.18').read_text()
    match=re.search(r'^LINUX_VERSION-6\.18\s*=\s*(\.\d+)\s*$',details,re.M)
    if not match:raise ValueError('Cannot resolve configured kernel')
    kernel_version='6.18'+match[1]
    linux=root/('build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-'+kernel_version)
    mt76 = linux.parent / 'mt76-2026.09.01~be5ce791'
    checks = []; warnings = []
    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
    config = (linux / '.config').read_text()
    check('effective PPE default off and WLAN NPU support compiled', '# CONFIG_NET_AIROHA_PPE_BIND_DEFAULT is not set' in config and 'CONFIG_NET_AIROHA_NPU=y' in config)
    param_object = ELF64(linux / 'drivers/net/ethernet/airoha/airoha_ppe.o')
    param = param_object.symbol_bytes('__param_ppe_bind_enable')
    check('compiled boot policy has default0 and read-only0400', param_object.symbol_bytes('ppe_bind_enable') == b'\0' and len(param) == 40 and int.from_bytes(param[24:26], 'little') == 0o400)
    check('compiled exact boot parameter name', param_object.symbol_bytes('__param_str_ppe_bind_enable').rstrip(b'\0') == b'airoha_eth.ppe_bind_enable')
    fit = FDT(selected['sysupgrade'].read_bytes())
    cfg_node = '/configurations/' + fit.string('/configurations', 'default')
    dtb = fit.payload('/images/' + fit.string(cfg_node, 'fdt'))
    board = FDT(dtb)
    check('packed I2C binding fixed', board.string('/soc/i2c0@1fbf8000', 'compatible') == 'mediatek,mt7621-i2c' and board.string('/soc/i2c0@1fbf8000', 'status') == 'okay')
    check('packed DTB is current generated DTB', dtb == (linux.parent / 'image-an7581-xr1710g.dtb').read_bytes())
    check('packed normal kernel is current saved Image', fit.payload('/images/' + fit.string(cfg_node, 'kernel')) == (linux.parent / 'Image').read_bytes())
    npu_policy = ELF64(mt76 / 'npu.o')
    npu_param = npu_policy.symbol_bytes('__param_npu_enable')
    check('compiled WLAN NPU attach default0 and read-only0400', npu_policy.symbol_bytes('npu_enable') == b'\0' and len(npu_param) == 40 and int.from_bytes(npu_param[24:26], 'little') == 0o400)
    check('compiled WLAN NPU boot parameter name', npu_policy.symbol_bytes('__param_str_npu_enable').rstrip(b'\0') == b'npu_enable')
    packed_mt7996 = (root / ('build_dir/target-aarch64_cortex-a53_musl/root-airoha/lib/modules/'+kernel_version+'/mt7996e.ko')).read_bytes()
    check('shipped TXFREE boundary and layout diagnostics', all(text in packed_mt7996 for text in [b'TXFREE nonlinear skb', b'TXFREE truncated', b'TXFREE short header', b'TXFREE linearize failed']))
    npu = (mt76 / 'npu.c').read_text()
    dequeue = extract_function(npu, 'static struct sk_buff *mt76_npu_dequeue(')
    refill = extract_function(npu, 'int mt76_npu_fill_rx_queue(')
    check('NPU ownership preflight and refill present', dequeue.index('ctrl = READ_ONCE(desc[index].ctrl);') < dequeue.index('dma_rmb();') < dequeue.index('READ_ONCE(desc[index].info)') and 'nframes > q->queued' in dequeue and 'e->dma_len[0]' in dequeue and 'clamp(nframes' not in dequeue and 'Q_WRITE' not in dequeue and 'WRITE_ONCE(desc[q->head].ctrl, 0)' in refill and 'Q_WRITE(q, dma_idx, q->head)' in refill)
    manifest = selected['manifest'].read_text()
    packages = {line.split(' - ')[0] for line in manifest.splitlines()}
    needed = {'xr1710g-ap-defaults', 'xr1710g-ap-configurator', 'kmod-mt76-core', 'kmod-mt7996e', 'kmod-hwmon-nct7802', 'wpad-mesh-mbedtls', 'luci-app-airoha-fancontrol'}
    check('current version manifest contains AP safety packages', needed <= packages)
    preinit = (root / 'build_dir/target-aarch64_cortex-a53_musl/root-airoha/lib/preinit/00_preinit.conf').read_text()
    check('current rootfs preinit address10.3', 'pi_ip="192.168.10.3"' in preinit)
    buildinfo = (selected['directory'] / 'version.buildinfo').read_text().strip()
    if selected['version'] not in buildinfo and str(selected['version_code']) not in buildinfo:
        warnings.append('version.buildinfo is an upstream/stale generic label; do not present it as the AP artifact version. Exact version was validated via .config/profiles.json and unique prefix.')
    result = {'passed': all(item['passed'] for item in checks), 'version': selected['version'], 'version_code': selected['version_code'], 'manifest': str(selected['manifest']), 'sysupgrade': str(selected['sysupgrade']), 'recovery': str(selected['recovery']), 'checks': checks, 'warnings': warnings, 'hardware_verified': False}
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--version')
    parser.add_argument('--print-manifest', action='store_true')
    parser.add_argument('--report')
    source_mode = parser.add_mutually_exclusive_group()
    source_mode.add_argument('--check-source-tracking', action='store_true')
    source_mode.add_argument('--source-patch', help='Write checked Git HEAD binary diff; no artifact check')
    args = parser.parse_args()
    try:
        if args.check_source_tracking:
            assert_source_tracking(args.root)
            result = {'passed': True, 'source_tracking_checked': True, 'scopes': SOURCE_PATCH_SCOPES}
        elif args.source_patch:
            patch = source_diff_checked(args.root)
            Path(args.source_patch).write_bytes(patch)
            result = {'passed': True, 'source_tracking_checked': True, 'patch_bytes': len(patch), 'scopes': SOURCE_PATCH_SCOPES}
        else:
            result = check_ap_build_artifacts(args.root, args.version)
    except Exception as error:
        result = {'passed': False, 'error': str(error)}
    if args.report: Path(args.report).write_text(json.dumps(result, indent=2) + '\n')
    if args.print_manifest and result['passed']:
        print(result['manifest'])
    else:
        print(json.dumps(result, indent=2))
    sys.exit(0 if result['passed'] else 1)

if __name__ == '__main__':
    main()
