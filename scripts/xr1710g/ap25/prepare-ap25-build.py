from pathlib import Path
from datetime import datetime
import hashlib,json,re,subprocess,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap25'
assert not (out/'scope.json').exists()
qa=json.loads((out/'guard-qa.json').read_text());assert qa['passed']
p=r/'package/network/config/xr1710g-ap-configurator'
assert qa['programSHA256']==hashlib.sha256((p/'files/xr1710g-ap-uplink-guard').read_bytes()).hexdigest()
shutil.copy2(w/'environment/test-ap25-guard.py',p/'tests/test-uplink-guard.py')
for f in [r/'.config',r/'xr1710g-ap.config']:
 s=f.read_text();assert '20261010-ap24-d331711d' in s
 for key in ['NUMBER','CODE']:
  s,n=re.subn(rf'^CONFIG_VERSION_{key}="[^"]+"$',f'CONFIG_VERSION_{key}="20261010-ap25-d331711d"',s,flags=re.M);assert n==1
 f.write_text(s)
subprocess.run(['make','defconfig'],cwd=r,check=True,stdout=subprocess.DEVNULL)
subprocess.run(['git','add','--','xr1710g-ap.config','package/network/config/xr1710g-ap-configurator'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
scope={'at':datetime.now().astimezone().isoformat(),'version':'20261010-ap25-d331711d','jobs':12,'change':'Users BSS guard soft ping debounce; retain open gate on first recovered probe','newFailureThresholdDefault':3,'guardQA':'development/ap25/guard-qa.json','bootKernelManagementBackhaulCodeChanged':False,'preserveExistingConfiguration':True,'NpuDefaultsOff':True}
(out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n');print(json.dumps(scope))
