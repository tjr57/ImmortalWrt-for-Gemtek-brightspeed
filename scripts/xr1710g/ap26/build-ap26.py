from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,re,subprocess,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap26'
app=r/'feeds/app_airoha/luci-app-airoha-npu'
assert not (out/'scope.json').exists()
for qa,file in [('rpc-qa.json','root/usr/libexec/rpcd/luci.airoha_npu'),('ui-qa.json','htdocs/luci-static/resources/view/airoha_npu/status.js')]:
 proof=json.loads((out/qa).read_text());assert proof['passed']
 assert proof.get('programSHA256',proof.get('sourceSHA256'))==hashlib.sha256((app/file).read_bytes()).hexdigest()
for file in [r/'.config',r/'xr1710g-ap.config']:
 s=file.read_text();assert '20261010-ap25-d331711d' in s
 for key in ['NUMBER','CODE']:
  s,n=re.subn(rf'^CONFIG_VERSION_{key}="[^"]+"$',f'CONFIG_VERSION_{key}="20261010-ap26-d331711d"',s,flags=re.M);assert n==1
 file.write_text(s)
subprocess.run(['make','defconfig'],cwd=r,check=True,stdout=subprocess.DEVNULL)
d=r/'scripts/xr1710g/ap26';d.mkdir(exist_ok=True)
for name in ['prepare-ap26-ppe-control.py','test-ap26-ppe-control.py','build-ap26.py','run-ap25-transit-baseline.py','inspect-ap25-ppe-transit.py','record-maple-owner-deferral.py']:
 shutil.copy2(w/'environment'/name,d/name)
subprocess.run(['git','add','--','xr1710g-ap.config','patches/feeds/app_airoha/luci-app-airoha-npu/108-npu-report-and-enforce-boot-PPE-policy.patch','scripts/xr1710g/ap26','AGENTS.md'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
scope={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'version':'20261010-ap26-d331711d','jobs':12,
 'change':'NPU RPC enforces independent bridge binding and policy latch; explicit-rule kernels reject legacy sysctl-only enable controls; Chinese UI reasons',
 'kernelBootOrWirelessCodeChanged':False,'defaultsChanged':False,'keepConfiguration':True,'MapleDoesNotBlock':True}
(out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
subprocess.run(['python3',str(w/'environment/xr1710g-safe-build.py'),'ap26','--root',str(r),'--artifacts','/home/xrdev/artifacts/xr1710g'],check=True)
