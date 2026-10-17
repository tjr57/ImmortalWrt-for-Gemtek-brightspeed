"""Prepare the already AP2-qualified diagnostic artifact and early-mount helper for AP1.

No router contact. Prior evidence is retained. Generated deployment remains one-shot.
"""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil

w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
base=w/'development/npu-ap2-debugfs';out=w/'development/npu-ap1-debugfs'
out.mkdir(exist_ok=True)
assert not (out/'preparation.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for kind in ('activation','recovery'):
    d=out/kind;d.mkdir(exist_ok=True)
    shutil.copytree(base/kind/'src',d/'src')
    shutil.copytree(base/kind/'files',d/'files')
    for name in ('function-qa.json','fixture-build.json'):
        if (base/kind/name).exists():shutil.copy2(base/kind/name,d/name)
    helper=d/'files'/('xr-npu-guarded-once' if kind=='activation' else 'xr-recovery-once')
    text=helper.read_text();assert text.count('"ap2"')==1
    text=text.replace('"ap2"','"ap1"').replace('# AP2 only,','# AP1 only,');helper.write_text(text)
    assert text.replace('"ap1"','"ap2"').replace('# AP1 only,','# AP2 only,')==(base/kind/'files'/helper.name).read_text()
runner=(base/'vm-runner.py').read_text().replace('npu-ap2-debugfs','npu-ap1-debugfs')
assert runner.count('"role":"ap2"')==1
runner=runner.replace('"role":"ap2"','"role":"ap1"')
(out/'vm-runner.py').write_text(runner)
oldlab=r.parent/'boot-lab/npu-ap2-debugfs';lab=r.parent/'boot-lab/npu-ap1-debugfs';lab.mkdir(exist_ok=True)
shutil.copy2(oldlab/'kmodloader',lab/'kmodloader')
for variant in ('normal','parameter-reset','fault'):
    shutil.copytree(oldlab/('module-'+variant),lab/('module-'+variant))
# Nested ARM test template contains escaped quotes. Swap the role literals at
# both quoting depths, preserving the wrong-role rejection case.
arm=(base/'arm-shell-test.py').read_text().replace('npu-ap2-debugfs','npu-ap1-debugfs')
for q in ('"','\\"'):
    arm=arm.replace(q+'role'+q+':'+q+'ap2'+q,q+'role'+q+':'+q+'SWAP'+q).replace(q+'role'+q+':'+q+'ap1'+q,q+'role'+q+':'+q+'ap2'+q).replace(q+'role'+q+':'+q+'SWAP'+q,q+'role'+q+':'+q+'ap1'+q)
arm=arm.replace('AP1 rejected','AP2 rejected');(out/'arm-shell-test.py').write_text(arm)
# Recovery helper is now byte-identical to the original qualified AP1 release5.
assert sha(out/'recovery/files/xr-recovery-once')==sha(w/'development/npu-recovery5/files/xr-recovery-once')
original_qa=w/'development/npu-recovery5/shipped-shell-qa.json'
if not original_qa.exists():original_qa=w/'development/npu-recovery/shipped-shell-qa.json'
qa=json.loads(original_qa.read_text());assert qa['helperSHA256']==sha(out/'recovery/files/xr-recovery-once') and qa['passed']
shutil.copy2(original_qa,out/'recovery/shipped-shell-qa.json')

source=w/'environment/deploy-npu-diag-ap2.py';deploy=source.read_text()
deploy=deploy.replace('AP2','TEMPPEER').replace('AP1','AP2').replace('TEMPPEER','AP1')
deploy=deploy.replace('connect(1,','connect(PEER,').replace('connect(2,','connect(1,').replace('connect(PEER,','connect(2,')
deploy=deploy.replace('identity(c,2)','identity(c,1)').replace('health(2,VERSION)','health(TARGET,VERSION)').replace('health(1,VERSION)','health(2,VERSION)').replace('health(TARGET,VERSION)','health(1,VERSION)')
deploy=deploy.replace("'unit':2","'unit':1").replace('producer-ap2-verified','producer-ap1-verified')
deploy=deploy.replace("out=w/'development/npu-diagnostic-ap2/deployment'","out=w/'development/npu-diagnostic-ap1/deployment'")
deploy=deploy.replace("assert absent(peer,'/etc/xr1710g-diagnostic.json')","assert json.loads(read(peer,'cat /etc/xr1710g-diagnostic.json'))['id']==lab['id']")
anchor="if sys.argv[1]=='upgrade':"
deploy=deploy.replace(anchor,"assert json.loads((w/'development/npu-ap2-debugfs/live-epoch-2/result.json').read_text())['ordinaryRecoveryAndCleanupPassed']\n"+anchor)
(w/'development/npu-diagnostic-ap1').mkdir(exist_ok=True)
compile(deploy,'AP1-deployment','exec');(w/'environment/deploy-npu-diag-ap1.py').write_text(deploy)
baseline=(w/'environment/read-npu-ap2-producer-baseline.py').read_text().replace('AP2','AP1').replace('npu-diagnostic-ap2','npu-diagnostic-ap1').replace('connect(2,','connect(1,').replace("'unit':2","'unit':1")
(w/'environment/read-npu-ap1-producer-baseline.py').write_text(baseline)
report={'at':datetime.now().astimezone().isoformat(),'prepared':True,'CUnchanged':True,
        'helperSHA256':sha(out/'activation/files/xr-npu-guarded-once'),
        'AP2FirmwareArtifactReused':True,'AP2RecoveryMustPassBeforeAP1Flash':True,
        'AP1EarlyMountVmPending':True,'originalHardwareFaultWasOnAP1':True}
(out/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
