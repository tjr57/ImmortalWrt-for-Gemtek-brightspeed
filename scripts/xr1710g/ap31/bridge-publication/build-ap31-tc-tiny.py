"""Private tc-tiny ARM build; no production package/config/stamp changes."""
from pathlib import Path
from datetime import datetime
import fcntl, hashlib, json, os, shutil, subprocess

r = Path('/home/xrdev/projects/xr1710g/openwrt')
w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap31/publisher'
base = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/iproute2-ipfull/iproute2-6.18.0'
tc = r / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
target = r / 'staging_dir/target-aarch64_cortex-a53_musl'
host = r / 'staging_dir/host'
lab = r.parent / 'boot-lab/ap31-tc-tiny' / datetime.now().strftime('%Y%m%d-%H%M%S')
lab.parent.mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
held_paths = [r / '.config', base / 'config.mk', base / 'ip/ip', base / 'bridge/bridge']
held = {str(p): sha(p) for p in held_paths}
env = dict(os.environ, STAGING_DIR=str(target),
           PATH=str(host / 'bin') + ':' + str(tc / 'bin') + ':' + os.environ['PATH'],
           CC=str(tc / 'bin/aarch64-openwrt-linux-musl-gcc'),
           AR=str(tc / 'bin/aarch64-openwrt-linux-musl-ar'),
           PKG_CONFIG=str(host / 'bin/pkg-config'), PKG_CONFIG_SYSROOT_DIR=str(target),
           PKG_CONFIG_LIBDIR=str(target / 'usr/lib/pkgconfig'),
           CFLAGS='-Os -I' + str(target / 'usr/include'),
           LDFLAGS='-L' + str(target / 'usr/lib') + ' -Wl,-rpath-link=' + str(target / 'usr/lib'),
           HAVE_ELF='', HAVE_MNL='', HAVE_CAP='', HAVE_TIRPC='n')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    shutil.copytree(base, lab)
    with (out / 'tc-tiny-build.log').open('w') as log:
        commands = [
            ['make', 'clean'],
            ['./configure', '--include_dir=' + str(tc / 'usr/include'), '--libbpf_force=off', '--color=auto'],
            ['make', '-j12', 'SUBDIRS=lib tc', 'BUILD_VARIANT=tctiny', 'SHARED_LIBS=',
             'TC_CONFIG_XT=n', 'TC_CONFIG_XT_OLD=n', 'TC_CONFIG_XT_OLD_H=n', 'TC_CONFIG_IPSET=n'],
        ]
        for cmd in commands:
            p = subprocess.run(cmd, cwd=lab, env=env, stdout=log, stderr=subprocess.STDOUT)
            assert p.returncode == 0, ('see tc-tiny-build.log', cmd)
    assert all((lab / 'tc' / n).is_file() for n in ['f_flower.o', 'm_mirred.o', 'm_vlan.o', 'q_clsact.o', 'tc'])
    assert held == {str(p): sha(p) for p in held_paths}
binary = out / 'tc-tiny-arm'
shutil.copy2(lab / 'tc/tc', binary)
root = target / 'root-airoha'
prefix = ['qemu-aarch64-static', '-L', str(root), str(binary)]
tests = [(['-V'], 'iproute2-6.18.0'), (['actions', 'add', 'vlan', 'help'], 'vlan'),
         (['actions', 'add', 'mirred', 'help'], 'mirred'), (['filter', 'add', 'flower', 'help'], 'skip_sw')]
logs = []
for args, expected in tests:
    p = subprocess.run(prefix + args, capture_output=True, text=True)
    output = p.stdout + p.stderr
    assert expected in output, (args, p.returncode, output)
    logs.append({'argv': args, 'rc': p.returncode, 'output': output})
(out / 'tc-tiny-arm-help.json').write_text(json.dumps(logs, indent=2) + '\n')
report = {'passed': True, 'jobs': 12, 'binarySHA256': sha(binary), 'size': binary.stat().st_size,
          'actualARMParserHelp': True, 'privateBuildOnly': True, 'productionStateUnchanged': True,
          'selectedVariant': 'tc-tiny', 'requiredPackages': ['tc-tiny', 'kmod-sched-core', 'kmod-sched-flower', 'kmod-sched-act-vlan'],
          'BPFOrXtablesRequired': False, 'fullImageBuiltOrFlashed': False}
(out / 'tc-tiny-build.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
