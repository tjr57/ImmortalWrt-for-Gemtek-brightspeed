from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,re,subprocess,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap27'
assert not (out/'scope.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for q in ['ping-rxbuf/build.json','ping-rxbuf/live-queue-qa.json','mesh-rx-audit/qa/result.json','mesh-rx-audit/build.json']:
    assert json.loads((out/q).read_text())['passed'],q
assert json.loads((out/'mesh-rx-audit/qa/result.json').read_text())['headerSHA256']==sha(out/'mesh-rx-audit.h')
for p in [r/'.config',r/'xr1710g-ap.config']:
    s=p.read_text();assert '20261010-ap26-d331711d' in s
    for key in ['NUMBER','CODE']:
        s,n=re.subn(rf'^CONFIG_VERSION_{key}="[^"]+"$',f'CONFIG_VERSION_{key}="20261010-ap27-d331711d"',s,flags=re.M);assert n==1
    p.write_text(s)
subprocess.run(['make','defconfig'],cwd=r,check=True,stdout=subprocess.DEVNULL)
assert '# CONFIG_PACKAGE_xr1710g-diag-recovery is not set' in (r/'.config').read_text()
dest=r/'scripts/xr1710g/ap27';dest.mkdir(exist_ok=True)
for n in ['prepare-ap27-busybox.py','build-ap27-busybox.py','test-ap27-ping-queue2.py','qualify-ap27-ping-queue.py','prepare-ap27-mesh-audit.py','test-ap27-mesh-audit.py','build-ap27-mesh-audit.py','build-ap27.py']:
    shutil.copy2(w/'environment'/n,dest/n)
shutil.copy2(out/'mesh-rx-audit.h',dest/'mesh-rx-audit.h')
scope={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'version':'20261010-ap27-d331711d','jobs':12,'changes':['BusyBox ping IPv4/IPv6 minimum RX buffer64KiB','mac80211 optional32-entry Mesh RX drop reason/time/length ring'],'defaultObserverEnabled':False,'configurationPreserved':True,'bootloaderKernelDTOrStartupScriptsChanged':False,'BusyBoxAndMac80211Changed':True,'recovery6NotIncludedInImage':True,'NpuDefaultsOff':True}
(out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
subprocess.run(['python3',str(w/'environment/xr1710g-safe-build.py'),'ap27','--root',str(r),'--artifacts','/home/xrdev/artifacts/xr1710g'],check=True)
