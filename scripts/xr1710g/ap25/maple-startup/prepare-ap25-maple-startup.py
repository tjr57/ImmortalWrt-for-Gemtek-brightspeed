"""Prepare original-firmware Maple-observer one-boot helper, separate from ROM."""
from pathlib import Path
import hashlib,json,shutil
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap25/maple-startup';out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
observer=w/'development/ap24/maple-observer'
q=json.loads((observer/'result-latest.json').read_text());assert q['passed'] and q['moduleSHA256']==sha(observer/'xr_maple_observer.ko')
assert json.loads((observer/'live-baseline2/result.json').read_text())['passed']
assert json.loads((w/'development/ap25/boot-lab/result.json').read_text())['criticalBootManagementBackhaulIdenticalToAP24']
assert not (out/'prepared.json').exists()
source=(w/'development/npu-ap2-debugfs/activation/files/xr-npu-guarded-once').read_text()
begin=source.index('[ -f /usr/libexec/xr_npu_producer.ko ]')
source=source[:begin]+f'''# The passive Maple observer must be ready before any NPU-backed WLAN load.
# Failure consumes the one-boot request and leaves the normal NPU-off boot.
[ -f /usr/libexec/xr_maple_observer.ko ] && [ ! -L /usr/libexec/xr_maple_observer.ko ] || exit 1
[ "$(sha256sum /usr/libexec/xr_maple_observer.ko | cut -d' ' -f1)" = {q['moduleSHA256']} ] || exit 1
timeout 5 insmod /usr/libexec/xr_maple_observer.ko || exit 1
[ "$(timeout 2 cat /sys/kernel/debug/xr_maple_observer)" = 'schema=1 captured=0' ] || exit 1
exec /usr/libexec/xr-diag-activate
'''
for unit in [2,1]:
 d=out/f'ap{unit}';d.mkdir();f=d/'files';f.mkdir()
 (f/'xr-npu-guarded-once').write_text(source.replace('"ap2"',f'"ap{unit}"'))
 recovery=(w/'development/npu-recovery/files/xr-recovery-once').read_text().replace('AP1 only',f'AP{unit} only').replace('"ap1"',f'"ap{unit}"')
 (f/'xr-recovery-once').write_text(recovery)
 for src,name in [(w/'development/npu-guarded-boot/files/xr_guarded_npu','xr_guarded_npu'),(w/'development/npu-recovery/files/xr_diag_recovery','xr_diag_recovery')]:shutil.copy2(src,f/name)
 for p in f.iterdir():p.chmod(0o755)
report={'prepared':True,'npuBlob':'original e743d1b5','newNativeCode':False,'passiveObserverSHA256':q['moduleSHA256'],'nativeRecoveryAndActivatorUnchanged':True,'helperChanges':['qualified early debugfs mount','AP role-specific helper','replace producer observer with qualified passive Maple observer before activation'],'helperHashes':{str(p.relative_to(out)):sha(p) for p in out.glob('ap*/files/*')},'physicalActivationSubmitted':False}
(out/'prepared.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
