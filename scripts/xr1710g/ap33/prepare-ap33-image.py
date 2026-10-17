"""Integrate privately qualified VLAN/port policy fix once, before full build."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl,hashlib,json,re,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out=w/'development/ap33';c=out/'bridge-policy';version='20261011-ap33-d331711d'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (out/'image-preparation.json').exists(),'Already started; inspect journal'
prep=json.loads((c/'prepared.json').read_text())
for name in ['qa.json','kernel-object-build.json','vm-result.json']:
 assert json.loads((c/name).read_text())['passed'],name
for path,h in prep['sources'].items():assert sha(k/path)==h['before'] and sha(c/Path(path).name)==h['after'],path
patch=r/'target/linux/airoha/patches-6.18/99999i-XR-PPE-VLAN-port-policy-fence.patch'
assert not patch.exists()
configs=[r/'.config',r/'xr1710g-ap.config']
record={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'version':version,'baseline':'20261011-ap32-d331711d',
 'jobs':12,'status':'started','patchSHA256':sha(c/patch.name),'configBeforeSHA256':{p.name:sha(p) for p in configs},
 'NpuPpeDefaultsChanged':False,'automaticPublisherIncluded':False,'deviceFlashed':False,
 'sourceEvidence':'development/ap33/bridge-policy/qa.json','vmEvidence':'development/ap33/bridge-policy/vm-result.json'}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 (out/'image-preparation.json').write_text(json.dumps(record,indent=2)+'\n')
 shutil.copy2(c/patch.name,patch)
 for p in configs:
  s=p.read_text();assert '20261011-ap32-d331711d' in s
  for suffix in ['NUMBER','CODE']:
   s,n=re.subn(r'^CONFIG_VERSION_'+suffix+r'="[^"]+"$','CONFIG_VERSION_'+suffix+'="'+version+'"',s,flags=re.M);assert n==1
  p.write_text(s)
 with (out/'prepare-image.log').open('w') as log:
  for target in ['defconfig','target/linux/prepare']:
   p=subprocess.run(['make',target,'-j12'],cwd=r,stdout=log,stderr=subprocess.STDOUT)
   assert p.returncode==0,'see prepare-image.log'
 for path,h in prep['sources'].items():assert sha(k/path)==h['after'],path
record.update(status='prepared',exactCandidateSourcesApplied=True,configAfterSHA256={p.name:sha(p) for p in configs})
(out/'image-preparation.json').write_text(json.dumps(record,indent=2)+'\n')
p=w/'development/current-goal.json';g=json.loads(p.read_text(encoding='utf-8-sig'))
g['latestAP33ImageBuild']=record
g['nextConcreteRepair']='AP33 已合入 VLAN/端口修改事务、每 VLAN 转发资格判断及 PPE 退出前撤销保护；继续 -j12 编译和镜像/ABI 检查，再保留配置 AP2 后 AP1。TC 策略、实际发布器和硬件路径验收仍未完成。'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record))
