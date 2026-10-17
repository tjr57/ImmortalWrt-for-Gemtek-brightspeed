"""Build AP32 private ARM bridge/PPE translation units, production unchanged."""
from pathlib import Path
from datetime import datetime
import argparse, fcntl, hashlib, json, os, shutil, subprocess

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
k = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
parser = argparse.ArgumentParser()
parser.add_argument('--candidate', choices=['bridge-transaction', 'packet-fence'], default='bridge-transaction')
args = parser.parse_args()
out = w / 'development/ap32' / args.candidate
tc = r / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
prep = json.loads((out / 'prepared.json').read_text())
for path, values in prep['sources'].items():
    assert sha(out / Path(path).name) == values['after'], path
    if (k / path).exists():
        assert sha(k / path) == values['before'], path
held_paths = [r / '.config', k / '.config', k / 'vmlinux', k / 'Module.symvers',
              *[k / p for p in prep['sources'] if (k / p).exists()]]
held = {str(p): sha(p) for p in held_paths}
lab = r.parent / 'boot-lab/ap32-bridge-objects' / datetime.now().strftime('%Y%m%d-%H%M%S')
lab.mkdir(parents=True)
objects = {}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for target in ['airoha_ppe', 'br_fdb', 'br_stp', 'br_fwd_policy']:
        origin = k / ('drivers/net/ethernet/airoha' if target == 'airoha_ppe' else 'net/bridge')
        build = lab / target
        build.mkdir()
        for p in origin.glob('*.h'):
            shutil.copy2(p, build / p.name)
        names = [target + '.c', 'if_bridge.h', 'airoha_eth.h' if target == 'airoha_ppe' else 'br_private.h']
        for n in names:
            shutil.copy2(out / n, build / n)
        includes = '-include $(src)/if_bridge.h'
        if target != 'airoha_ppe':
            # trace/events/bridge.h includes the original br_private.h before
            # br_fdb.c reaches its local include. Load the private candidate first.
            includes += ' -include $(src)/br_private.h'
        (build / 'Makefile').write_text('obj-m += ' + target + '.o\nccflags-y += ' + includes + '\n')
        cmd = ['make', '-C', str(k), 'ARCH=arm64', 'CROSS_COMPILE=' + str(tc / 'bin/aarch64-openwrt-linux-musl-'),
               'M=' + str(build), target + '.o', '-j12', 'V=1']
        p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, STAGING_DIR=str(tc)))
        (out / (target + '-' + lab.name + '-build.log')).write_text(p.stdout + p.stderr)
        assert p.returncode == 0, p.stderr[-5000:]
        shutil.copy2(build / (target + '.o'), out / (target + '.o'))
        objects[target] = sha(out / (target + '.o'))
assert held == {str(p): sha(p) for p in held_paths}
report = {'passed': True, 'jobs': 12, 'objects': objects, 'candidate': prep['sources'],
          'productionStateUnchanged': True, 'heldHashes': held, 'fullImageOrHardwareQualified': False}
(out / 'kernel-object-build.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('heldHashes', 'candidate')}))
