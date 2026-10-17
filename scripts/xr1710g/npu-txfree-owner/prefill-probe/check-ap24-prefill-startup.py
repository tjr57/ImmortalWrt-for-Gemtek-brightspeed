"""Execute the assembled image's real ARM startup scripts in a private fixture.

This verifies packaging and default/rejected requests only. Hardware, NPU execution
and recovery behavior are NOT simulated by this user-mode ARM test.
"""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys

W = Path('/mnt/d/ChatGPT/XR1710G')
R = Path('/home/xrdev/projects/xr1710g/openwrt')
OUT = W/'development/ap24/prefill-probe'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert os.geteuid() == 0
assembly = json.loads((OUT/'result.json').read_text())
artifact = Path(assembly['artifact'])
assert assembly['passed'] and sha(artifact) == assembly['artifactSHA256']
sys.path.insert(0, str(R/'scripts'))
from verify_ap4_artifacts import FDT

lab = Path('/home/xrdev/projects/xr1710g/boot-lab')/('npu-packed-startup-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
lab.mkdir()
squash = lab/'packed.squashfs'
squash.write_bytes(FDT(artifact.read_bytes()).payload('/images/rootfs-1'))
ship = lab/'packed'
with (OUT/'packed-extraction.log').open('w') as log:
    subprocess.run([str(R/'staging_dir/host/bin/unsquashfs4'), '-processors', '12',
                    '-no-progress', '-d', str(ship), str(squash)], stdout=log, stderr=subprocess.STDOUT, check=True)
root = lab/'fixture'
for directory in ('bin','lib/functions','etc/init.d','etc/rc.d','usr/libexec','usr/sbin',
                  'tmp/sysinfo','proc/sys/kernel/random','root','dev','fixture'):
    (root/directory).mkdir(parents=True, exist_ok=True)
shutil.copy2('/usr/bin/qemu-aarch64-static', root/'qemu-aarch64-static')
shutil.copy2('/bin/busybox', root/'fixture/busybox')
sources = ['bin/busybox','lib/libc.so','lib/libgcc_s.so.1','etc/rc.common',
           'lib/functions.sh','lib/functions/service.sh',
           'etc/init.d/xr_diag_recovery','etc/init.d/xr_guarded_npu',
           'usr/libexec/xr-recovery-once','usr/libexec/xr-npu-guarded-once']
for rel in sources:
    shutil.copy2(ship/rel, root/rel)
    assert sha(root/rel) == sha(ship/rel)
(root/'lib/ld-musl-aarch64.so.1').symlink_to('libc.so')
applets = sorted({p.name for directory in ('bin','sbin','usr/bin','usr/sbin')
                  for p in (ship/directory).iterdir()
                  if p.is_symlink() and os.readlink(p).endswith('busybox')})
for name in applets:
    if name == 'busybox':
        continue
    path = root/'bin'/name
    path.write_text('#!/fixture/busybox sh\nexec /qemu-aarch64-static -0 '+name+' /bin/busybox "$@"\n')
    path.chmod(0o755)
os.mknod(root/'dev/null', stat.S_IFCHR | 0o666, os.makedev(1,3))
# Unexpected execution is recorded and refused. Real C actors/readers are bound
# below to their prior real-kernel suites, not replaced in the assembled image.
boundaries = ('usr/libexec/xr-diag-activate','usr/libexec/xr-diag-recovery',
              'usr/libexec/xr-diag-capture','bin/insmod','bin/reboot','bin/sync')
for rel in boundaries:
    path = root/rel
    path.write_text('#!/fixture/busybox sh\nprintf "unexpected '+rel+'\\n" >>/tmp/unexpected\nexit 125\n')
    path.chmod(0o755)
role = root/'usr/sbin/xr1710g-ap-role'
role.write_text('#!/fixture/busybox sh\n/fixture/busybox cat /tmp/role\n')
role.chmod(0o755)
for rel in ('etc/rc.d/S08xr_diag_recovery','etc/rc.d/S08xr_guarded_npu'):
    (root/rel).symlink_to(os.readlink(ship/rel))
assert sorted(p.name for p in (root/'etc/rc.d').iterdir()) == ['S08xr_diag_recovery','S08xr_guarded_npu']
current = '11111111-1111-1111-1111-111111111111'
old = '22222222-2222-2222-2222-222222222222'
(root/'proc/sys/kernel/random/boot_id').write_text(current+'\n')
(root/'tmp/sysinfo/board_name').write_text('gemtek,xr1710g\n')
(root/'tmp/role').write_text('{"role":"ap1"}\n')
cases = []


def check(service, action, label, code):
    before = {str(p.relative_to(root)):sha(p) for p in (root/'etc').rglob('*') if p.is_file()}
    result = subprocess.run(['chroot', str(root), '/bin/sh', '/etc/rc.common',
                             '/etc/init.d/'+service, action], capture_output=True, timeout=10)
    assert result.returncode == code, (label,result.returncode,result.stdout,result.stderr)
    assert not (root/'tmp/unexpected').exists(), label
    assert not list((root/'root').iterdir()), label
    assert before == {str(p.relative_to(root)):sha(p) for p in (root/'etc').rglob('*') if p.is_file()}
    cases.append({'case':label,'exitCode':code,'noChildExecutionOrConfigurationWrite':True})


for service, marker, prefix in [('xr_diag_recovery','xr-recovery.once','xr-recovery-v1'),
                                 ('xr_guarded_npu','xr-npu-guarded.once','xr-npu-guarded-v1')]:
    request = root/'etc'/marker
    check(service,'boot',service+' no request',0)
    check(service,'start',service+' manual start remains inert',0)
    request.write_text(prefix+' '+current+'\n');request.chmod(0o600)
    check(service,'boot',service+' same boot remains inert',0)
    request.write_text('invalid\n')
    check(service,'boot',service+' malformed request rejected',1)
    request.unlink();request.symlink_to('/tmp/missing')
    check(service,'boot',service+' dangling symlink rejected',1)
    request.unlink();request.write_text(prefix+' '+old+'\n');request.chmod(0o644)
    check(service,'boot',service+' loose request rejected',1)
    request.chmod(0o600)
    (root/'tmp/role').write_text('{"role":"ap2"}\n')
    check(service,'boot',service+' AP2 request rejected',1)
    request.unlink();(root/'tmp/role').write_text('{"role":"ap1"}\n')

bindings = assembly['sourceBoundVM']
assert len(bindings) == 7 and 'singleStartupPrefill' in bindings
for rel in assembly['changedFiles']:
    expected = assembly['changedFiles'][rel]
    if 'sha256' in expected:
        assert sha(ship/rel) == expected['sha256']
report = {'passed':True,'at':datetime.now().astimezone().isoformat(),
          'artifactSHA256':sha(artifact),'assemblyReportSHA256':sha(OUT/'result.json'),
          'actualPackedARMInputs':{rel:sha(ship/rel) for rel in sources},
          'checks':cases,'sourceBoundRealKernelEvidence':bindings,
          'hardwareBootAlreadyProvenByThisQA':False,'realNpuExecutableTested':False,
          'armUserModeIsNotHardwareBootProof':True,
          'independentPackedExtraction':str(ship),'fixture':str(root)}
(OUT/'packed-startup.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'checks':len(cases),'artifactSHA256':sha(artifact),'hardwareBootAlreadyProvenByThisQA':False}))
