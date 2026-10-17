from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,re,subprocess,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap30'
assert not (out/'scope.json').exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for f in ['eht-header/qa/result.json','eht-header/build.json']:assert json.loads((out/f).read_text())['passed']
assert json.loads((out/'eht-header/qa/result.json').read_text())['headerSHA256']==sha(out/'patched-mt76.h')
for p in [r/'.config',r/'xr1710g-ap.config']:
    s=p.read_text();assert '20261010-ap29-d331711d' in s
    for key in ['NUMBER','CODE']:
        s,n=re.subn(rf'^CONFIG_VERSION_{key}="[^"]+"$',f'CONFIG_VERSION_{key}="20261010-ap30-d331711d"',s,flags=re.M);assert n==1
    p.write_text(s)
subprocess.run(['make','defconfig'],cwd=r,check=True,stdout=subprocess.DEVNULL)
dest=r/'scripts/xr1710g/ap30';dest.mkdir(exist_ok=True)
for n in ['prepare-ap30-eht-header.py','test-ap30-eht-header.py','build-ap30-driver.py','build-ap30.py','prepare-ap30-build.py']:shutil.copy2(w/'environment'/n,dest/n)
shutil.copy2(out/'patched-mt76.h',dest/'patched-mt76.h')
scope={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'version':'20261010-ap30-d331711d','jobs':12,'change':'Fix EHT TLV header selection and prevent cross-TID false replay rejection','correctPNCounterSelection':True,'replayChecksPreserved':True,'payloadOrKeysCaptured':False,'kernelDTBusyBoxAndStartupUnchanged':True,'preserveConfiguration':True}
(out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
subprocess.run(['python3',str(w/'environment/xr1710g-safe-build.py'),'ap30','--root',str(r),'--artifacts','/home/xrdev/artifacts/xr1710g'],check=True)
