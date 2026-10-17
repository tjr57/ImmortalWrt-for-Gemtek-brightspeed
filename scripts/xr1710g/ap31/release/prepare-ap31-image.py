"""Integrate verified defensive guards and diagnostic dependencies once."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl, hashlib, json, re, shutil, subprocess

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
k = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out = w / 'development/ap31'
candidate = out / 'ppe-context'
version = '20261011-ap31-d331711d'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert not (out / 'image-preparation.json').exists(), 'One-shot preparation already started/completed'
progress = json.loads((candidate / 'progress.json').read_text())
assert progress['candidateSHA256'] == sha(candidate / 'airoha_ppe.c')
for p in ['ppe-context/qa.json', 'ppe-context/kernel-object-build.json', 'publisher/vm-result.json', 'publisher/tc-tiny-build.json']:
    assert json.loads((out / p).read_text())['passed'], p
kernel_files = ['drivers/net/ethernet/airoha/airoha_ppe.c', 'drivers/net/ethernet/airoha/airoha_eth.h', 'net/bridge/br_fdb.c', 'include/linux/if_bridge.h']
for p in kernel_files:
    assert sha(k / p) == sha(candidate / ('before-' + Path(p).name)), p
patch = r / 'target/linux/airoha/patches-6.18/99999g-XR-exact-PPE-bridge-publication.patch'
assert not patch.exists()
configs = [r / '.config', r / 'xr1710g-ap.config']
dependencies = ['tc-tiny', 'kmod-sched-core', 'kmod-sched-flower', 'kmod-sched-act-vlan']
record = {'at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'version': version,
          'baseline': '20261010-ap30-d331711d', 'jobs': 12, 'status': 'started',
          'patchSHA256': sha(candidate / patch.name), 'configBeforeSHA256': {p.name: sha(p) for p in configs},
          'dependencies': dependencies, 'NpuPpeDefaultsChanged': False, 'automaticPublisherIncluded': False,
          'sourceCandidate': 'development/ap31/ppe-context/progress.json', 'deviceFlashed': False}
(out / 'image-preparation.json').write_text(json.dumps(record, indent=2) + '\n')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    shutil.copy2(candidate / patch.name, patch)
    for p in configs:
        s = p.read_text()
        assert '20261010-ap30-d331711d' in s
        for suffix in ['NUMBER', 'CODE']:
            s, count = re.subn(r'^CONFIG_VERSION_' + suffix + r'="[^"]+"$', 'CONFIG_VERSION_' + suffix + '="' + version + '"', s, flags=re.M)
            assert count == 1
        for package in dependencies:
            key = 'CONFIG_PACKAGE_' + package
            s = re.sub(r'^(?:' + re.escape(key) + r'=.*|# ' + re.escape(key) + r' is not set)\n?', '', s, flags=re.M)
            s += key + '=y\n'
        p.write_text(s)
    with (out / 'prepare-image.log').open('w') as log:
        for target in ('defconfig', 'target/linux/prepare'):
            p = subprocess.run(['make', target, '-j12'], cwd=r, stdout=log, stderr=subprocess.STDOUT)
            assert p.returncode == 0, 'See prepare-image.log'
    for p in kernel_files:
        assert sha(k / p) == sha(candidate / Path(p).name), ('prepared source differs', p)
record['status'] = 'prepared'
record['configAfterSHA256'] = {p.name: sha(p) for p in configs}
record['exactCandidateSourcesApplied'] = True
(out / 'image-preparation.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
