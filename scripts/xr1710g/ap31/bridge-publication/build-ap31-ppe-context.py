"""Private ARM kernel object builds, including the real bridge implementation."""
from pathlib import Path
from datetime import datetime
import fcntl, hashlib, json, os, shutil, subprocess

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
k = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out = w / 'development/ap31/ppe-context'
tc = r / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
qa = json.loads((out / 'qa.json').read_text())
assert qa['passed'] and qa['candidateSHA256'] == sha(out / 'airoha_ppe.c')
paths = ['drivers/net/ethernet/airoha/airoha_ppe.c', 'drivers/net/ethernet/airoha/airoha_eth.h', 'net/bridge/br_fdb.c', 'include/linux/if_bridge.h']
for path in paths:
    assert sha(k / path) == sha(out / ('before-' + Path(path).name)), path
held_paths = [r / '.config', k / '.config', k / 'vmlinux', k / 'Module.symvers', *[k / p for p in paths]]
held = {str(p): sha(p) for p in held_paths}
lab = r.parent / 'boot-lab/ap31-ppe-context' / datetime.now().strftime('%Y%m%d-%H%M%S')
lab.mkdir(parents=True)
objects = {}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for target, origin in [('airoha_ppe', k / 'drivers/net/ethernet/airoha'), ('br_fdb', k / 'net/bridge')]:
        build = lab / target
        build.mkdir()
        for p in origin.glob('*.h'):
            shutil.copy2(p, build / p.name)
        for n in [target + '.c', 'if_bridge.h', *(['airoha_eth.h'] if target == 'airoha_ppe' else [])]:
            shutil.copy2(out / n, build / n)
        (build / 'Makefile').write_text('obj-m += ' + target + '.o\nccflags-y += -include $(src)/if_bridge.h\n')
        cmd = ['make', '-C', str(k), 'ARCH=arm64', 'CROSS_COMPILE=' + str(tc / 'bin/aarch64-openwrt-linux-musl-'), 'M=' + str(build), target + '.o', '-j12', 'V=1']
        p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, STAGING_DIR=str(tc)))
        (out / (target + '-build.log')).write_text(p.stdout + p.stderr)
        assert p.returncode == 0, p.stderr[-4000:]
        shutil.copy2(build / (target + '.o'), out / (target + '.o'))
        objects[target] = sha(out / (target + '.o'))
assert held == {str(p): sha(p) for p in held_paths}
report = {'passed': True, 'jobs': 12, 'sourceSHA256': {Path(p).name: sha(out / Path(p).name) for p in paths},
          'objects': objects, 'privateActualArmKernelObjects': True, 'productionStateUnchanged': True,
          'heldHashes': held, 'fullImageOrHardwareQualified': False}
(out / 'kernel-object-build.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'heldHashes'}))
