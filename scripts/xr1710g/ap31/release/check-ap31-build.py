"""Qualify actual AP31 image/ABI/delta; does not deploy it."""
from pathlib import Path
import hashlib, json, os, re, shutil, stat, subprocess, sys, tempfile

r = Path('/home/xrdev/projects/xr1710g/openwrt')
w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap31'
art = Path('/home/xrdev/artifacts/xr1710g')
k = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
version = '20261011-ap31-d331711d'
oldversion = '20261010-ap30-d331711d'
sys.path.insert(0, str(r / 'scripts'))
from artifact_light_checks import select_version_artifacts, check_ap_build_artifacts
from verify_ap4_artifacts import FDT
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
process = json.loads((art / 'build-ap31-process.json').read_text())
assert process['exitCode'] == 0 and process['wirelessKernelABIValidated'] and process['externalWlanRebuildRequired']
for n in ['process', 'module-abi']:
    (out / ('build-' + n + '.json')).write_bytes((art / ('build-ap31-' + n + '.json')).read_bytes())
candidate = out / 'ppe-context'
for p in ['drivers/net/ethernet/airoha/airoha_ppe.c', 'drivers/net/ethernet/airoha/airoha_eth.h', 'net/bridge/br_fdb.c', 'include/linux/if_bridge.h']:
    assert sha(k / p) == sha(candidate / Path(p).name), p
vm = json.loads((out / 'publisher/vm-result.json').read_text())
assert vm['passed']
selected = select_version_artifacts(r, version)
image = selected['sysupgrade']
old = next((w / ('builds/' + oldversion + '-development')).glob('*-squashfs-sysupgrade.itb'))
assert sha(old) == '904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0'
assert all(x['imageSHA256'] != sha(image) for x in json.loads((w / 'development/rejected-firmware.json').read_text())['rejected'])

def payloads(fit, kind):
    return {n: fit.payload(n) for n, p in fit.nodes.items() if n.startswith('/images/') and n.count('/') == 2 and p.get('type', b'').rstrip(b'\0') == kind}

oldfit, newfit = FDT(old.read_bytes()), FDT(image.read_bytes())
assert payloads(oldfit, b'flat_dt') == payloads(newfit, b'flat_dt') and payloads(newfit, b'flat_dt')
assert payloads(oldfit, b'kernel') != payloads(newfit, b'kernel')

def listing(root):
    result = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(parent) / name
            mode = p.lstat().st_mode
            result[str(p.relative_to(root))] = {'mode': mode, 'content': os.readlink(p) if p.is_symlink() else sha(p) if stat.S_ISREG(mode) else None}
    return result

with tempfile.TemporaryDirectory(prefix='ap31-packed-') as tmp:
    roots = []
    for label, fit in [('old', oldfit), ('new', newfit)]:
        p = payloads(fit, b'filesystem'); assert len(p) == 1
        sq = Path(tmp) / (label + '.squashfs'); sq.write_bytes(next(iter(p.values())))
        root = Path(tmp) / label
        subprocess.run([str(r / 'staging_dir/host/bin/unsquashfs4'), '-no-progress', '-d', str(root), str(sq)], check=True, stdout=subprocess.DEVNULL)
        roots.append(root)
    before, after = map(listing, roots)
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    delta = {'changedPaths': changed, 'added': sorted(after.keys() - before.keys()), 'removed': sorted(before.keys() - after.keys()),
             'before': {p: before.get(p) for p in changed}, 'after': {p: after.get(p) for p in changed}}
    (out / 'rootfs-delta.json').write_text(json.dumps(delta, indent=2) + '\n')
    metadata = {'etc/banner', 'etc/openwrt_release', 'etc/openwrt_version', 'usr/lib/os-release', 'lib/apk/db/installed', 'lib/apk/db/scripts.tar.gz', 'etc/apk/world'}
    additions = {'tc-tiny', 'kmod-sched-core', 'kmod-sched-flower', 'kmod-sched-act-vlan'}
    metadata |= {'lib/apk/packages/' + p + '.list' for p in additions}
    metadata.add('lib/apk/packages/tc-tiny.alternatives')
    tools = {'usr/libexec/tc-tiny', 'sbin/tc', 'etc/modules.d/70-sched-core', 'etc/modules.d/sched-flower', 'etc/modules.d/sched-act-vlan'}
    allowed = lambda p: p in metadata | tools or p.startswith('lib/modules/6.18.54/')
    unexpected = [p for p in changed if not allowed(p)]
    assert not unexpected, ('unexpected rootfs changes; inspect delta', unexpected)
    assert not delta['removed'], delta['removed']
    rf = roots[1]
    old_world = set((roots[0] / 'etc/apk/world').read_text().splitlines())
    new_world = set((rf / 'etc/apk/world').read_text().splitlines())
    old_kernel = {p for p in old_world if p.startswith('kernel=')}
    new_kernel = {p for p in new_world if p.startswith('kernel=')}
    assert len(old_kernel) == len(new_kernel) == 1
    assert new_kernel == {'kernel=6.18.54~' + (k / '.vermagic').read_text().strip() + '-r1'}
    old_world -= old_kernel; new_world -= new_kernel
    assert old_world <= new_world and new_world - old_world == additions
    for path in before.keys() & after.keys():
        assert before[path]['mode'] == after[path]['mode'], path
    assert os.readlink(rf / 'sbin/tc') == '/usr/libexec/tc-tiny'
    arm_tc = ['qemu-aarch64-static', '-L', str(rf), str(rf / 'usr/libexec/tc-tiny')]
    for args, expected in [(['-V'], 'iproute2-6.18.0'), (['actions', 'add', 'vlan', 'help'], 'vlan'),
                           (['actions', 'add', 'mirred', 'help'], 'mirred'), (['filter', 'add', 'flower', 'help'], 'skip_sw')]:
        p = subprocess.run(arm_tc + args, capture_output=True, text=True)
        assert expected in p.stdout + p.stderr, (args, p.stdout, p.stderr)
    for n in ['cls_flower', 'act_vlan', 'act_mirred', 'sch_ingress']:
        assert (rf / ('lib/modules/6.18.54/' + n + '.ko')).is_file(), n
    staged = r / 'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'
    packed_modules = {str(p.relative_to(rf)): sha(p) for p in (rf / 'lib/modules/6.18.54').glob('*.ko')}
    cross = str(r / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-')
    for p in packed_modules:
        stripped = Path(tmp) / ('verify-' + Path(p).name)
        shutil.copy2(staged / p, stripped)
        subprocess.run(['sh', str(r / 'scripts/strip-kmod.sh'), str(stripped)],
                       env=dict(os.environ, CROSS=cross, NO_RENAME='1'), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert packed_modules[p] == sha(stripped), ('packed module differs after canonical strip', p)
    baseline = json.loads((w / 'development/ap30/packed-files-qa.json').read_text())['matchedFiles']
    matched = {p: sha(rf / p) for p in baseline}
    for p in baseline:
        if not p.startswith('lib/modules/'):
            assert matched[p] == baseline[p], p
    matched.update(packed_modules)
    for p in tools:
        if (rf / p).is_file() and not (rf / p).is_symlink():
            matched[p] = sha(rf / p)
    # Existing init scripts, defaults, password setup, Mesh/SSH startup and
    # all firmware blobs are byte-identical by the full-rootfs delta gate.
    assert sha(rf / 'bin/busybox') == json.loads((w / 'development/ap27/ping-rxbuf/live-queue-qa.json').read_text())['binarySHA256']
    for p in ['etc/banner', 'etc/openwrt_release', 'etc/openwrt_version', 'usr/lib/os-release']:
        assert (roots[0] / p).read_bytes().replace(oldversion.encode(), version.encode()) == (rf / p).read_bytes()
    packed = {'passed': True, 'version': version, 'imageSHA256': sha(image), 'imageSize': image.stat().st_size,
              'matchedFiles': matched, 'packedModules': len(packed_modules),
              'checks': ['Actual configured ARM kernel and WLAN module ABI gate passed',
                         'Exact tested PPE/bridge source integrated; DT identical to AP30',
                         'Full rootfs delta limited to kernel modules, TC tools/autoload and metadata',
                         'Management/Mesh/defaults/firmware/BusyBox unchanged',
                         'PPE/NPU remain default off; automatic rule executor absent']}
    (out / 'packed-files-qa.json').write_text(json.dumps(packed, indent=2) + '\n')
host = check_ap_build_artifacts(r, version); assert host['passed']
(out / 'artifact-qa.json').write_text(json.dumps(host, indent=2) + '\n')
p = subprocess.run(['python3', str(r / 'scripts/test-xr1710g-ap-defaults.py')], capture_output=True, text=True, check=True)
defaults = json.loads(p.stdout); assert defaults['passed'] and len(defaults['checks']) == 14
(out / 'defaults-qa.json').write_text(json.dumps(defaults, indent=2) + '\n')
(out / 'boot-lab').mkdir(exist_ok=True)
gate = {'preflashChecksPassed': True, 'imageSHA256': sha(image), 'homeModeAuthorized': True,
        'actualARMBuildABIAndImageChecks': True, 'newKernelVMRun': True,
        'vmEvidence': 'development/ap31/publisher/vm-result.json', 'fullARMHardwareBootProven': False,
        'scope': 'Actual bridge API/port predicate and TC/VLAN actions in isolated Linux VM; AP ARM objects and linked image/ABI; hardware boot still requires AP2 first.'}
(out / 'boot-lab/result.json').write_text(json.dumps(gate, indent=2) + '\n')
print(json.dumps({'passed': True, 'imageSHA256': sha(image), 'size': image.stat().st_size, 'matchedFiles': len(matched)}))
