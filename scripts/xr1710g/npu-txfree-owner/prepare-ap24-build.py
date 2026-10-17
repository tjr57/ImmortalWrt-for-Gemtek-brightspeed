from pathlib import Path
from datetime import datetime
import hashlib,json,re,subprocess,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap24';out.mkdir(exist_ok=True)
assert not (out/'scope.json').exists()
qa=json.loads((w/'development/npu-txfree-owner/vm-result-latest.json').read_text());assert qa['passed']
assert qa['sourceBindings']['after']['sourceSHA256']==hashlib.sha256((w/'development/npu-txfree-owner/after/dma.c').read_bytes()).hexdigest()
for p in (r/'.config',r/'xr1710g-ap.config'):
    text=p.read_text();assert '20261010-ap23-d331711d' in text
    for field in ('NUMBER','CODE'):
        text,n=re.subn(rf'^CONFIG_VERSION_{field}="[^"]+"$',f'CONFIG_VERSION_{field}="20261010-ap24-d331711d"',text,flags=re.M);assert n==1
    p.write_text(text)
subprocess.run(['make','defconfig'],cwd=r,stdout=subprocess.DEVNULL,check=True)
tools=r/'scripts/xr1710g/npu-txfree-owner';tools.mkdir(exist_ok=True)
for name in ('prepare-npu-txfree-owner-fix.py','test-npu-txfree-owner-vm.py'):shutil.copy2(w/'environment'/name,tools/name)
subprocess.run(['git','add','--','xr1710g-ap.config','scripts/xr1710g/npu-txfree-owner'],cwd=r,check=True)
scope={'at':datetime.now().astimezone().isoformat(),'version':'20261010-ap24-d331711d','jobs':12,
       'changes':['mt76 release14 prevents generic refill/poll/cleanup/reset of firmware-owned TXFREE buffers'],
       'bootLoadedDriverChanged':True,'VMRelevantChangedFunctionsPassed':True,'VMReport':'development/npu-txfree-owner/vm-result-latest.json',
       'NpuHistoricalRootProven':False,'originalNpuFirmwareUnchanged':True,'experimentalDefaultsOff':True,
       'optionalDiagnosticActivationPackageRelease4NotSelected':True,'hardwareApplied':False}
(out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n');print(json.dumps(scope))
