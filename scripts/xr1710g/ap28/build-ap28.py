from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,re,subprocess,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap28'
assert not (out/'scope.json').exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for f in ['mesh-rx-audit/qa/result.json','mesh-rx-audit/build.json']:assert json.loads((out/f).read_text())['passed']
assert json.loads((out/'mesh-rx-audit/qa/result.json').read_text())['headerSHA256']==sha(out/'mesh-rx-audit.h')
for p in [r/'.config',r/'xr1710g-ap.config']:
    s=p.read_text();assert '20261010-ap27-d331711d' in s
    for key in ['NUMBER','CODE']:
        s,n=re.subn(rf'^CONFIG_VERSION_{key}="[^"]+"$',f'CONFIG_VERSION_{key}="20261010-ap28-d331711d"',s,flags=re.M);assert n==1
    p.write_text(s)
subprocess.run(['make','defconfig'],cwd=r,check=True,stdout=subprocess.DEVNULL)
dest=r/'scripts/xr1710g/ap28';dest.mkdir(exist_ok=True)
for n in ['prepare-ap28-early-rx.py','test-ap28-mesh-audit.py','build-ap28-mesh-audit.py','build-ap28.py']:shutil.copy2(w/'environment'/n,dest/n)
shutil.copy2(out/'mesh-rx-audit.h',dest/'mesh-rx-audit.h')
scope={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'version':'20261010-ap28-d331711d','jobs':12,'change':'Extend default-off Mesh RX metadata to known peer ONLY_MONITOR/FCS/PLCP flags before monitor gate','packetAcceptancePolicyUnchanged':True,'payloadOrKeysCaptured':False,'kernelDTBusyBoxAndStartupUnchanged':True,'preserveConfiguration':True}
(out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
subprocess.run(['python3',str(w/'environment/xr1710g-safe-build.py'),'ap28','--root',str(r),'--artifacts','/home/xrdev/artifacts/xr1710g'],check=True)
