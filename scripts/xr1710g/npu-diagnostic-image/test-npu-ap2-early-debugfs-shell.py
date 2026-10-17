"""Actual ARM shell gate: early mount success and bounded/fail-closed paths."""
from pathlib import Path
import subprocess,json,hashlib
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/npu-ap2-debugfs'
script=(w/'development/npu-ap2-guard/arm-activation-test.py').read_text()
script=script.replace('development/npu-ap2-guard/activation','development/npu-ap2-debugfs/activation')
anchor="exec(compile(source,'ARM-shell-activation-fixture','exec'),{'__name__':'__main__'})"
assert script.count(anchor)==1
adapter=r'''
anchor="current='11111111-1111-1111-1111-111111111111'"
setup=r"""
(root/'sys/kernel/debug').mkdir(parents=True)
(root/'proc/mounts').write_text('debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,noatime 0 0\n')
(root/'bin/mount').write_text('#!/fixture/busybox sh\n[ ! -e /tmp/mount-fail ] || exit 1\n[ ! -e /tmp/mount-slow ] || /fixture/busybox sleep 6\nprintf "called\\n" >>/tmp/mounted\nprintf "debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,noatime 0 0\\n" >/proc/mounts\n')
(root/'bin/mount').chmod(0o755)
"""
assert source.count(anchor)==1
source=source.replace(anchor,setup+anchor)
anchor="expect('valid next-boot request consumed and guarded actor called',True)"
extra=r"""
assert not (root/'tmp/mounted').exists()
(root/'proc/mounts').write_text('tmpfs /sys/kernel/debug tmpfs rw 0 0\n')
arm();expect('wrong existing filesystem rejected without mount',False);assert not (root/'tmp/mounted').exists() and not request.exists() and not called.exists()
(root/'proc/mounts').write_text('');(root/'tmp/mount-fail').touch()
arm();expect('early mount failure rejected',False);assert not request.exists() and not called.exists();(root/'tmp/mount-fail').unlink()
(root/'tmp/mount-slow').touch();arm();expect('early mount timeout rejected',False);assert not request.exists() and not called.exists();(root/'tmp/mount-slow').unlink()
(root/'sys/kernel/debug').rmdir();(root/'sys/kernel/debug').symlink_to('/tmp')
arm();expect('debugfs target symlink rejected',False);assert not request.exists() and not called.exists()
(root/'sys/kernel/debug').unlink();(root/'sys/kernel/debug').mkdir()
arm();expect('missing early debugfs mounted before activation',True);assert called.exists() and (root/'tmp/mounted').read_text()=='called\n';called.unlink()
arm()
"""
assert source.count(anchor)==1
source=source.replace(anchor,extra+anchor)
'''
script=script.replace(anchor,adapter+'\n'+anchor)
generated=out/'arm-shell-test.py';generated.write_text(script)
subprocess.run(['sudo','-n','python3',str(generated)],check=True)
report=json.loads((out/'activation/shipped-shell-qa.json').read_text())
assert report['passed'] and len(report['checks'])==23
report['mountBoundaryMockedInArmTest']=True
report['realMountAndRecoveryRequireSeparateKernelVM']=True
(out/'activation/shipped-shell-qa.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'checks':len(report['checks']),'helperSHA256':report['helperSHA256']}))
