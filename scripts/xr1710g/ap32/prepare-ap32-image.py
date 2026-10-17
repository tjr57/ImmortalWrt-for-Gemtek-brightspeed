"""One-shot integration of the privately qualified FDB/STP/packet fence."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl, hashlib, json, re, shutil, subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out=w/'development/ap32';candidate=out/'packet-fence';version='20261011-ap32-d331711d'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (out/'image-preparation.json').exists(),'already started; inspect instead'
prep=json.loads((candidate/'prepared.json').read_text())
for path in ['packet-fence/qa.json','packet-fence/kernel-object-build.json','bridge-transaction/vm-result.json']:
 assert json.loads((out/path).read_text())['passed'],path
for path,h in prep['sources'].items():
 assert sha(candidate/Path(path).name)==h['after']
 if (k/path).exists():assert sha(k/path)==h['before'],path
 else:assert h['before']==hashlib.sha256(b'').hexdigest()
for name in ['br_fdb.c','br_stp.c','br_private.h','br_fwd_policy.c','if_bridge.h','Makefile']:
 assert sha(candidate/name)==sha(out/'bridge-transaction'/name)
patch=r/'target/linux/airoha/patches-6.18/99999h-XR-PPE-bridge-mutation-fence.patch'
assert not patch.exists()
configs=[r/'.config',r/'xr1710g-ap.config']
record={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'version':version,
 'baseline':'20261011-ap31-d331711d','jobs':12,'status':'started',
 'patchSHA256':sha(candidate/patch.name),'configBeforeSHA256':{p.name:sha(p) for p in configs},
 'NpuPpeDefaultsChanged':False,'automaticPublisherIncluded':False,'deviceFlashed':False,
 'sourceEvidence':'development/ap32/packet-fence/qa.json','vmEvidence':'development/ap32/bridge-transaction/vm-result.json'}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 (out/'image-preparation.json').write_text(json.dumps(record,indent=2)+'\n')
 shutil.copy2(candidate/patch.name,patch)
 for p in configs:
  s=p.read_text();assert '20261011-ap31-d331711d' in s
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
gpath=w/'development/current-goal.json';g=json.loads(gpath.read_text(encoding='utf-8-sig'))
g['latestAP32ImageBuild']=record
g['nextConcreteRepair']='AP32 已合入 FDB/STP 修改事务及数据包桥接键版本检查；继续 -j12 完整构建、镜像/ABI/配置检查，再保留配置 AP2 后 AP1。TC及其他策略变更、实际发布器仍未完成；NPU/PPE 默认关闭。'
gpath.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record))
