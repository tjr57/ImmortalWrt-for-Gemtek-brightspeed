"""Exact AP24 binary binding, isolated KASAN guest, then ARM module build.

No router access or production configuration/image changes.
"""
from pathlib import Path
from datetime import datetime
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

W = Path('/mnt/d/ChatGPT/XR1710G')
R = Path('/home/xrdev/projects/xr1710g/openwrt')
O = W / 'development/ap24/maple-observer'
SRC = O / 'src'
K = R / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
VK = R.parent / 'boot-lab/npu-addresses/linux-6.18.54'
TC = R / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
lab = R.parent / 'boot-lab/maple-observer' / stamp
lab.mkdir(parents=True)
sys.path.insert(0, str(R / 'scripts'))
from verify_ap4_artifacts import FDT, ELF64

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(name, value):
    (O / name).write_text(json.dumps(value, indent=2) + '\n')

fit = next((W / 'builds/20261010-ap24-d331711d-development').glob('*sysupgrade.itb'))
assert sha(fit) == '411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0'
payload = FDT(fit.read_bytes()).payload('/images/kernel-1')
elf = ELF64(K / 'vmlinux')
symbol = elf.symbols['mas_empty_area_rev']
code = elf.symbol_bytes('mas_empty_area_rev')
offset = payload.find(code)
assert len(code) == 0x640 and offset >= 0 and payload.find(code, offset + 1) == -1
assert symbol['value'] - offset == 0xffffffc080000000
assert code[0xd4:0xd8] == bytes.fromhex('647860f8')
header = '/* Generated from the exact frozen AP24 Image; no text writes. */\n'
header += 'static const unsigned char xr_maple_expected[] = {\n'
header += '\n'.join(','.join(f'0x{v:02x}' for v in code[i:i+16]) + ',' for i in range(0, len(code), 16))
header += '\n};\n'
(SRC / 'xr_maple_binding.h').write_text(header)
binding = {'frozenFIT_SHA256': sha(fit), 'vmlinux_SHA256': sha(K/'vmlinux'),
           'symbol': symbol, 'imageOffset': hex(offset),
           'codeSHA256': hashlib.sha256(code).hexdigest(),
           'allFunctionBytesMatchedFrozenImage': True,
           'headerSHA256': sha(SRC/'xr_maple_binding.h')}
write('binding.json', binding)
protected = [R/'.config', K/'.config', K/'Module.symvers', K/'vmlinux', fit,
             VK/'.config', VK/'Module.symvers', VK/'arch/x86/boot/bzImage',
             R/'build_dir/target-aarch64_cortex-a53_musl/root-airoha/lib/modules/6.18.54/mt76.ko']
before = {str(p): sha(p) for p in protected}
source = {p.name: sha(p) for p in SRC.iterdir() if p.is_file()}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    vm_build = lab / 'vm-module'
    shutil.copytree(SRC, vm_build)
    with (O/(stamp+'-vm-build.log')).open('w') as f:
        subprocess.run(['make', '-C', str(VK), 'M='+str(vm_build),
                        'XR_MAPLE_VM=1', '-j12', 'modules'], stdout=f, stderr=subprocess.STDOUT, check=True)
root = lab / 'root'
for name in ('bin', 'dev', 'proc', 'sys', 'tmp'):
    (root/name).mkdir(parents=True, exist_ok=True)
shutil.copy2('/bin/busybox', root/'bin/busybox')
for name in ('sh', 'mount', 'cat', 'grep', 'test', 'insmod', 'rmmod', 'poweroff'):
    (root/'bin'/name).symlink_to('busybox')
shutil.copy2(vm_build/'xr_maple_observer.ko', root/'bin/xr_maple_observer.ko')
(root/'init').write_text('''#!/bin/sh
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t debugfs debugfs /sys/kernel/debug
fail() { echo XR_MAPLE_GUEST_FAIL; poweroff -f; }
insmod /bin/xr_maple_observer.ko || fail
cat /sys/kernel/debug/xr_maple_observer | grep -qx 'schema=1 captured=0' || fail
rmmod xr_maple_observer || fail
test ! -e /sys/kernel/debug/xr_maple_observer || fail
echo XR_MAPLE_GUEST_PASS
poweroff -f
''')
(root/'init').chmod(0o755)
paths = ['.'] + [str(p.relative_to(root)) for p in sorted(root.rglob('*'))]
archive = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=root,
                         input=('\0'.join(paths)+'\0').encode(), capture_output=True, check=True).stdout
initrd = lab/'guest.cpio.gz'
with gzip.open(initrd, 'wb') as f:
    f.write(archive)
log = O/(stamp+'-guest.log')
cmd = ['sudo', '-n', 'timeout', '55', 'qemu-system-x86_64', '-accel', 'tcg', '-cpu', 'qemu64',
       '-smp', '2', '-m', '1024', '-nodefaults', '-display', 'none', '-serial', 'stdio',
       '-monitor', 'none', '-no-reboot', '-run-with', 'user=xrdev',
       '-kernel', str(VK/'arch/x86/boot/bzImage'), '-initrd', str(initrd),
       '-append', 'console=ttyS0 rdinit=/init nokaslr panic=1 panic_on_oops=1 panic_on_warn=1']
with log.open('w') as f:
    p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
text = log.read_text(errors='replace')
bad = re.findall(r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|XR_MAPLE_TEST_FAIL|XR_MAPLE_GUEST_FAIL).*$', text, re.M)
cases = re.findall(r'XR_MAPLE_TEST_PASS (\w+)', text)
passed = p.returncode == 0 and not bad and len(cases) == 14 and 'XR_MAPLE_GUEST_PASS' in text
vm = {'passed': passed, 'cases': cases, 'unexpectedFaults': bad, 'exitCode': p.returncode,
      'sources': source, 'moduleSHA256': sha(vm_build/'xr_maple_observer.ko'),
      'guestKernelSHA256': sha(VK/'arch/x86/boot/bzImage'), 'log': str(log),
      'realNotifierRegistration': True, 'callbackWithSyntheticFrames': True,
      'realNotifierDispatch': False, 'realNofaultStackRead': True,
      'limits': ['Synthetic register frames; x86 register names adapted to ARM roles.',
                 'Callback is invoked directly because notify_die is not exported.',
                 'No actual ARM exception, NPU, DMA or hardware corruption is emulated.'],
      'noHostNetworkOrDisks': True}
write(stamp+'-vm.json', vm)
write('vm-result-latest.json', vm)
assert passed, str(log)
print(json.dumps({'vmPassed': True, 'cases': len(cases)}), flush=True)
arm = lab/'arm-module'
shutil.copytree(SRC, arm)
env = dict(os.environ, STAGING_DIR=str(TC))
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with (O/(stamp+'-arm-build.log')).open('w') as f:
        subprocess.run(['make', '-C', str(K), 'M='+str(arm), 'ARCH=arm64',
                        'CROSS_COMPILE='+str(TC/'bin/aarch64-openwrt-linux-'),
                        '-j12', 'modules'], env=env, stdout=f, stderr=subprocess.STDOUT, check=True)
module = arm/'xr_maple_observer.ko'
def info(p, field):
    return subprocess.check_output(['/sbin/modinfo', '-F', field, str(p)], text=True).strip()
assert info(module, 'vermagic') == info(protected[-1], 'vermagic')
assert not info(module, 'parm')
assert int.from_bytes(module.read_bytes()[18:20], 'little') == 183
assert b'XR_MAPLE_TEST_PASS' not in module.read_bytes()
imports = subprocess.check_output([str(TC/'bin/aarch64-openwrt-linux-nm'), '-u', str(module)], text=True)
assert all(x in imports for x in ('copy_from_kernel_nofault', 'register_die_notifier', 'mas_empty_area_rev'))
assert not any(x in imports for x in ('regmap_write', 'ioremap', 'dma_map', 'kprobe', 'notify_die'))
assert before == {str(p): sha(p) for p in protected}
shutil.copy2(module, O/'xr_maple_observer.ko')
report = {'passed': True, 'at': datetime.now().astimezone().isoformat(),
          'jobs': 12, 'sources': source, 'binding': binding,
          'moduleSHA256': sha(module), 'moduleBytes': module.stat().st_size,
          'vermagic': info(module, 'vermagic'), 'vmCasesPassed': len(cases),
          'productionContractsUnchanged': before, 'noModuleParameters': True,
          'vmAdapterAbsentFromArmBinary': True, 'hardwareLoaded': False,
          'productionImageChanged': False}
write(stamp+'-result.json', report)
write('result-latest.json', report)
(O/'arm-imports.txt').write_text(imports)
print(json.dumps(report), flush=True)
