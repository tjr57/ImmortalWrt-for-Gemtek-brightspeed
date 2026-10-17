"""Fix the observed S08 versus S10 debugfs ordering in an AP2-only helper."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
base=w/'development/npu-ap2-guard';out=w/'development/npu-ap2-debugfs'
out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (out/'preparation.json').exists()
for kind in ('activation','recovery'):
    d=out/kind;d.mkdir(exist_ok=True)
    shutil.copytree(base/kind/'src',d/'src',dirs_exist_ok=True)
    shutil.copytree(base/kind/'files',d/'files',dirs_exist_ok=True)
    for name in ('function-qa.json','fixture-build.json'):
        p=base/kind/name
        if p.exists():shutil.copy2(p,d/name)
helper=out/'activation/files/xr-npu-guarded-once'
text=helper.read_text();anchor='# Failed observer loading consumes this request and leaves NPU disabled.'
assert text.count(anchor)==1
insertion='''# S08 precedes OpenWrt S10boot, which normally mounts debugfs. Do not confuse
# a missing mount with a failed firmware fingerprint. Reject a wrong filesystem
# instead of hiding it under another mount; bound any new mount operation.
[ -d /sys/kernel/debug ] && [ ! -L /sys/kernel/debug ] || exit 1
if ! grep -q '^[^ ]* /sys/kernel/debug debugfs ' /proc/mounts; then
 [ -f /proc/mounts ] || exit 1
 if grep -q '^[^ ]* /sys/kernel/debug ' /proc/mounts; then exit 1; fi
 timeout 3 mount -t debugfs -o nosuid,nodev,noexec,noatime debugfs /sys/kernel/debug || exit 1
 grep -q '^[^ ]* /sys/kernel/debug debugfs ' /proc/mounts || exit 1
fi
'''
text=text.replace(anchor,insertion+anchor);helper.write_text(text)
assert text.replace(insertion,'')==(base/'activation/files/xr-npu-guarded-once').read_text()
runner=(base/'vm-runner.py').read_text()
runner=runner.replace('development/npu-ap2-guard','development/npu-ap2-debugfs')
# Every previous success/fault case now starts without a debugfs mount.
line='mount -t debugfs debugfs /sys/kernel/debug\n'
assert runner.count(line)==1
runner=runner.replace(line,'# debugfs intentionally absent before the S08 helper\n')
# Unique fixture directory prevents aliasing retained prior guest inputs.
runner=runner.replace("boot-lab/npu-ap2-guard'","boot-lab/npu-ap2-debugfs'")
oldlab=r.parent/'boot-lab/npu-ap2-guard';lab=r.parent/'boot-lab/npu-ap2-debugfs';lab.mkdir(exist_ok=True)
shutil.copy2(oldlab/'kmodloader',lab/'kmodloader')
for variant in ('normal','parameter-reset','fault'):
    shutil.copytree(oldlab/('module-'+variant),lab/('module-'+variant),dirs_exist_ok=True)
# Verify filesystem and mount flags after real helper success, before snapshot.
anchor=' [ -d /sys/module/xr_npu_addresses ] && [ -d /sys/module/xr_npu_producer ] || fail observer_not_loaded'
assert runner.count(anchor)==1
runner=runner.replace(anchor," grep -q '^debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,noatime' /proc/mounts || fail debugfs_mount_flags\n"+anchor)
(out/'vm-runner.py').write_text(runner)
report={'prepared':True,'at':datetime.now().astimezone().isoformat(),
        'helperSHA256':sha(helper),'CSourceUnchanged':True,'mountOptions':'nosuid,nodev,noexec,noatime',
        'mountTimeoutSeconds':3,'wrongExistingFilesystemRejected':True,'realKernelChecksPending':True,
        'finding':'Production S10boot mounts debugfs after S08 fingerprint preflight; previous VM prematurely mounted it',
        'sourceEvidenceSHA256':sha(r/'package/base-files/files/etc/init.d/boot'),
        'hardwareEpoch':'development/npu-ap2-guard/live-epoch-1/activation-failed.json'}
(out/'preparation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
