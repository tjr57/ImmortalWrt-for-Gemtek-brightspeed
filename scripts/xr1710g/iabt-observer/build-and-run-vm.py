"""Real-kernel VM qualification for xr_iabt_observer.

Builds the module against the already-built isolated x86 guest kernel in
boot-lab/npu-addresses (KASAN_GENERIC + LOCKDEP + PROVE_LOCKING +
DEBUG_ATOMIC_SLEEP), asserting that the guest kernel's own artefacts are not
modified by an external-module build. Then boots it under QEMU with a BusyBox
initrd and exercises: refusal paths, the in-module checks, a real kint run, a
real scan run over every task, and clean unload while armed.

No device is touched. No existing qualification kernel is modified.
"""
import fcntl
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
SRC = Path('/home/xrdev/projects/xr1710g/openwrt/scripts/xr1710g/iabt-observer')
BASE = Path('/home/xrdev/projects/xr1710g/boot-lab/npu-addresses/linux-6.18.54')
LAB = Path('/home/xrdev/projects/xr1710g/boot-lab/iabt-observer-review')
EVIDENCE = Path('/mnt/d/ChatGPT/XR1710G/development/ap47/npu-iabt-observer-review-20261013')
LOCK = Path('/home/xrdev/artifacts/xr1710g/build.lock')
HELD = ['.config', 'Module.symvers', 'arch/x86/boot/bzImage']
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')
QEMU_TIMEOUT = 420


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


INIT = r'''#!/bin/sh
export PATH=/bin:/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t debugfs debugfs /sys/kernel/debug
echo 0 > /proc/sys/kernel/kptr_restrict
M=/lib/modules/xr_iabt_observer.ko
D=/sys/kernel/debug/xr_iabt_observer
fail() { echo "XR_IABT_FAIL: $*"; sync; poweroff -f; }

ST=$(awk '$3=="_stext"{print $1}' /proc/kallsyms)
ET=$(awk '$3=="_etext"{print $1}' /proc/kallsyms)
[ -n "$ST" ] && [ -n "$ET" ] || fail no_kallsyms_text_range
# The kernel parses ulong parameters with base 0, so a bare hex digit string is
# read as decimal and overflows. The 0x prefix is mandatory.
ST=0x$ST
ET=0x$ET
echo "XR_IABT_TEXT_RANGE $ST $ET"

echo XR_IABT_STEP refusals
# --- refusal paths: the module must not arm without verified preconditions ---
reject() {
  if insmod $M "$@" 2>/dev/null; then
    rmmod xr_iabt_observer 2>/dev/null
    echo "XR_IABT_UNEXPECTED_ACCEPT $1"
    fail "unexpected_accept"
  fi
  echo "XR_IABT_EXPECT_REJECT_OK $1"
}
reject scan_enable=1 scan_prefix=napi/
reject scan_enable=1 text_start=$ST text_end=$ET
reject kint_mib=999 deadline_s=30
reject deadline_s=0

echo XR_IABT_STEP vm_tests
# --- in-module checks, then a clean unload while everything is armed ---
insmod $M text_start=$ST text_end=$ET vm_tests=1 diecap_enable=1 die_log_enable=1 \
  deadline_s=120 || fail insmod_vm_tests
[ -f $D/status ] || fail no_debugfs
echo XR_IABT_STATUS_BEGIN; cat $D/status; echo XR_IABT_STATUS_END
echo XR_IABT_SCAN_BEGIN; cat $D/scan; echo XR_IABT_SCAN_END
echo XR_IABT_DIE_BEGIN; cat $D/die; echo XR_IABT_DIE_END
echo XR_IABT_KINT_BEGIN; cat $D/kint; echo XR_IABT_KINT_END
echo XR_IABT_STEP rmmod_after_tests
rmmod xr_iabt_observer || fail rmmod_after_vm_tests
echo XR_IABT_UNLOAD_AFTER_TESTS_OK

echo XR_IABT_STEP kint_run
# --- a real kernel-side pattern run ---
insmod $M text_start=$ST text_end=$ET kint_mib=1 kint_seconds=5 \
  deadline_s=60 || fail insmod_kint
sleep 8
echo XR_IABT_KINT_RUN_BEGIN; cat $D/kint; echo XR_IABT_KINT_RUN_END
echo XR_IABT_STEP rmmod_kint
rmmod xr_iabt_observer || fail rmmod_kint

echo XR_IABT_STEP concurrent_readers_and_deadline
insmod $M text_start=$ST text_end=$ET diecap_enable=1 kint_mib=1 \
  kint_seconds=3 deadline_s=4 || fail insmod_concurrent
# Forking processes must not lead to unsafe cross-task stack accesses.
i=0
while [ "$i" -lt 80 ]; do
  (cat $D/scan >/dev/null; cat $D/die >/dev/null; cat $D/kint >/dev/null) &
  i=$((i+1))
  if [ $((i%8)) -eq 0 ]; then wait; fi
done
wait
sleep 5
echo XR_IABT_STATUS_RUN_BEGIN; cat $D/status; echo XR_IABT_STATUS_RUN_END
grep -q 'armed=0.*expired=1' $D/status || fail deadline_status
rmmod xr_iabt_observer || fail rmmod_after_deadline
echo XR_IABT_DEADLINE_UNLOAD_OK
# Cover removal while notifier and worker are live, before the deadline.
insmod $M text_start=$ST text_end=$ET diecap_enable=1 kint_mib=1 \
  kint_seconds=30 deadline_s=60 || fail insmod_live
rmmod xr_iabt_observer || fail rmmod_live
echo XR_IABT_UNLOAD_WHILE_ARMED_OK

echo XR_IABT_VM_ALL_OK
sync
poweroff -f
'''


def build_module():
    mod = LAB / 'module'
    if mod.exists():
        shutil.rmtree(mod)
    mod.mkdir(parents=True)
    for name in ('xr_iabt_observer.c', 'xr_iabt_vm_tests.h', 'Makefile'):
        shutil.copy2(SRC / name, mod / name)
    log = EVIDENCE / ('vm-module-build-' + STAMP + '.log')
    with log.open('w') as fh:
        proc = subprocess.run(
            ['make', '-C', str(BASE), 'M=' + str(mod), 'XR_IABT_VM=1',
             'modules', '-j12'],
            stdout=fh, stderr=subprocess.STDOUT)
    ko = mod / 'xr_iabt_observer.ko'
    if proc.returncode or not ko.exists():
        raise RuntimeError('guest module build failed; see %s' % log)
    text = log.read_text(errors='replace')
    warnings = [line for line in text.splitlines()
                if re.search(r'warning:|error:', line)]
    return ko, log, warnings


def build_initrd(ko):
    root = LAB / ('guest-' + STAMP)
    root.mkdir(parents=True)
    for d in ('bin', 'sbin', 'dev', 'proc', 'sys', 'tmp', 'lib/modules'):
        (root / d).mkdir(parents=True, exist_ok=True)
    shutil.copy2('/bin/busybox', root / 'bin/busybox')
    for n in ('sh', 'mount', 'cat', 'sleep', 'echo', 'awk', 'grep', 'insmod',
              'rmmod', 'lsmod', 'poweroff', 'sync', 'dmesg'):
        (root / 'bin' / n).symlink_to('busybox')
    shutil.copy2(ko, root / 'lib/modules/xr_iabt_observer.ko')
    (root / 'init').write_text(INIT)
    (root / 'init').chmod(0o755)
    paths = ['.'] + [str(p.relative_to(root)) for p in sorted(root.rglob('*'))]
    proc = subprocess.run(
        ['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=root,
        input=('\0'.join(paths) + '\0').encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    initrd = LAB / ('guest-' + STAMP + '.cpio.gz')
    with gzip.open(initrd, 'wb') as fh:
        fh.write(proc.stdout)
    return initrd


def run_vm(initrd):
    accel = 'kvm' if Path('/dev/kvm').exists() else 'tcg'
    # Serial goes straight to a file. With -serial stdio and a redirected
    # stdout, libc block-buffers the console and a timeout kill loses every
    # line, which makes a slow guest indistinguishable from a dead one.
    console = EVIDENCE / ('vm-console-' + STAMP + '.log')
    cmd = ['timeout', str(QEMU_TIMEOUT), 'qemu-system-x86_64', '-accel', accel,
           '-cpu', 'host' if accel == 'kvm' else 'qemu64',
           '-smp', '2', '-m', '2048', '-nodefaults', '-nic', 'none',
           '-display', 'none', '-serial', 'file:' + str(console),
           '-monitor', 'none',
           '-no-reboot', '-kernel', str(BASE / 'arch/x86/boot/bzImage'),
           '-initrd', str(initrd),
           '-append', 'console=ttyS0 rdinit=/init panic=1 panic_on_oops=1 '
                      'panic_on_warn=1']
    log = EVIDENCE / ('vm-' + STAMP + '.log')
    with log.open('w') as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode, console


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    LAB.mkdir(parents=True, exist_ok=True)
    report = {'at': datetime.now(TZ).isoformat(),
              'accelerator': 'kvm' if Path('/dev/kvm').exists() else 'tcg',
              'deviceTouched': False, 'existingKernelModified': False}

    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = {name: sha(BASE / name) for name in HELD}
        report['guestKernelBefore'] = before
        try:
            ko, build_log, warnings = build_module()
        except RuntimeError as exc:
            report['fatal'] = str(exc)
            report['passed'] = False
            (EVIDENCE / ('vm-result-' + STAMP + '.json')).write_text(
                json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            return 1
        after = {name: sha(BASE / name) for name in HELD}
        report['guestKernelAfter'] = after
        report['guestKernelUnchanged'] = before == after
        report['moduleSHA256'] = sha(ko)
        report['sourceSHA256'] = {n: sha(SRC / n) for n in
                                  ('xr_iabt_observer.c', 'xr_iabt_vm_tests.h')}
        report['buildLog'] = str(build_log)
        report['buildWarnings'] = warnings

        initrd = build_initrd(ko)
        report['initrd'] = str(initrd)
        rc, log = run_vm(initrd)
        text = log.read_text(errors='replace')

    faults = re.findall(
        r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|possible circular locking|'
        r'sleeping function called from invalid context|XR_IABT_FAIL:).*$',
        text, re.M)
    passes = re.findall(r'XR_IABT_TEST_PASS (\S+)', text)
    fails = re.findall(r'XR_IABT_TEST_FAIL (\S+)', text)
    rejects = re.findall(r'XR_IABT_EXPECT_REJECT_OK (\S+)', text)
    unexpected = re.findall(r'XR_IABT_UNEXPECTED_ACCEPT', text)

    def block(tag):
        m = re.search('XR_IABT_' + tag + r'_BEGIN\s*(.*?)\s*XR_IABT_' + tag +
                      '_END', text, re.S)
        return m.group(1).strip() if m else None

    blocks = {name: block(name) for name in
              ('STATUS', 'SCAN', 'DIE', 'KINT', 'KINT_RUN', 'SCAN_RUN',
               'STATUS_RUN')}
    trange = re.search(r'XR_IABT_TEXT_RANGE (\S+) (\S+)', text)

    report.update({
        'qemuExitCode': rc,
        'log': str(log),
        'checksPassed': len(passes),
        'checksFailed': fails,
        'refusalPathsVerified': rejects,
        'unexpectedAccepts': len(unexpected),
        'faults': faults[:40],
        'allOkMarker': 'XR_IABT_VM_ALL_OK' in text,
        'unloadAfterTests': 'XR_IABT_UNLOAD_AFTER_TESTS_OK' in text,
        'unloadWhileArmed': 'XR_IABT_UNLOAD_WHILE_ARMED_OK' in text,
        'guestTextRange': trange.groups() if trange else None,
        'debugfsBlocks': blocks,
    })
    report['passed'] = bool(
        report['guestKernelUnchanged'] and rc == 0 and not faults and
        not fails and not unexpected and not warnings and report['allOkMarker'] and
        'XR_IABT_DEADLINE_UNLOAD_OK' in text and
        text.count('XR_IABT_DIE_BEGIN') == text.count('XR_IABT_DIE_END') >= 1 and
        report['unloadAfterTests'] and report['unloadWhileArmed'] and
        len(passes) >= 43 and len(rejects) == 4)

    (EVIDENCE / ('vm-result-' + STAMP + '.json')).write_text(json.dumps(report, indent=2))
    summary = {k: v for k, v in report.items()
               if k not in ('debugfsBlocks', 'guestKernelBefore',
                            'guestKernelAfter')}
    print(json.dumps(summary, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
