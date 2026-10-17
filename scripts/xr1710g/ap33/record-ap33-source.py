"""Archive AP33 source and qualification after integration, once."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap33';c=out/'bridge-policy'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (out/'source-progress.json').exists(),'Already recorded'
qa=json.loads((c/'qa.json').read_text());vm=json.loads((c/'vm-result.json').read_text())
assert qa['passed'] and vm['passed'] and json.loads((c/'kernel-object-build.json').read_text())['passed']
assert qa['candidateSHA256']==sha(c/'airoha_ppe.c')
assert json.loads((out/'image-preparation.json').read_text())['status']=='prepared'
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
report={'at':now,'stage':'integrated; full image qualification pending','baseline':'20261011-ap32-d331711d',
 'version':'20261011-ap33-d331711d','patch':'target/linux/airoha/patches-6.18/99999i-XR-PPE-VLAN-port-policy-fence.patch',
 'patchSHA256':sha(c/'99999i-XR-PPE-VLAN-port-policy-fence.patch'),'candidateSHA256':qa['candidateSHA256'],
 'qa':'development/ap33/bridge-policy/qa.json','ARMObjectBuild':'development/ap33/bridge-policy/kernel-object-build.json',
 'realKernelVM':'development/ap33/bridge-policy/vm-result.json','nativeSanitizedAndARMChecksEach':{'context':66758,'packet':78682},
 'realKernelChecks':len(vm['checks']),'realKernelEvents':vm['eventCount'],'guardSites':15,
 'implemented':['VLAN membership/filter/protocol/default-PVID/state mutation fences',
 'netlink/sysfs port policy, MST enable, bridge attach/detach mutation fences',
 'require selected VLAN forwarding state on both ports and packet ingress',
 'latch/revoke L2 binding before notifier teardown'],
 'realVMContainsNoPPEHardware':True,'kernelAPIsModeledInExactFunctionFixtures':True,
 'fixtureFailedRunsRetained':[str(p.relative_to(w)) for p in sorted(c.glob('vm-20*.json')) if not json.loads(p.read_text())['passed']],
 'fixtureRepairs':['carry preexisting BPDU netlink companion changes and rebuild copied dependencies',
 'enable actual switchdev support and inject both atomic and blocking notifier paths'],
 'productionSourceIntegrated':True,'flashed':False,'NpuPpeDefaultOff':True,
 'remaining':['other netdevice and TC policy transition coverage','actual publisher and coherent collector',
 'full image/ABI validation and AP2 then AP1 keep-config upgrade','applicable hardware qualification with current recovery/ABI manifests']}
(out/'source-progress.json').write_text(json.dumps(report,indent=2)+'\n')
dest=r/'scripts/xr1710g/ap33';dest.mkdir(exist_ok=True);d=dest/'bridge-policy';d.mkdir(exist_ok=True)
for p in c.iterdir():
 if p.suffix in ['.c','.h','.patch','.json']:shutil.copy2(p,d/p.name)
for p in (w/'environment').glob('*ap33*.py'):shutil.copy2(p,dest/p.name)
shutil.copy2(out/'source-progress.json',dest/'source-progress.json')
p=r/'AGENTS.md';s=p.read_text();marker='<!-- ap33-integrated -->';assert marker not in s
entry=f'''
{marker}
## AP33 VLAN/port policy fence integrated ({now})

- Patch 99999i adds 15 balanced policy guards, per-VLAN forwarding eligibility,
  and L2 revoke before observer teardown. NPU/PPE/default diagnostics stay off.
- Evidence D:/ChatGPT/XR1710G/development/ap33/source-progress.json.
  Exact native sanitizer/ARM context66758 + packet78682 checks each; seven
  actual ARM objects; isolated real kernel {len(vm['checks'])} checks/{vm['eventCount']} events.
  Real switchdev failures and rollback covered; failed VM fixture runs retained.
- Full image/ABI/defaults validation pending. Use safe-build ap33, -j12.
  AP32 remains live until AP33 one-shot keep-config AP2, then AP1 acceptance.
  AP2 Mesh-only, no cable/TTL assumed. Never rerun scheduled upgrades/trials.
- TC/remaining policy, actual publisher/collector, applicable hardware proof
  remain outstanding. No hardware PPE gain or broad goal completion implied.
<!-- /ap33-integrated -->
'''
p.write_text(s.replace('# XR1710G development context\n','# XR1710G development context\n'+entry,1))
p=w/'development/current-goal.json';g=json.loads(p.read_text())
g['previousPPECandidates']=g.get('previousPPECandidates',[])+[g['latestPPECandidate']]
g['latestPPECandidate']=report;g['lastDevelopmentUpdate']=now
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['git','add','--','AGENTS.md','xr1710g-ap.config','scripts/xr1710g/ap33',report['patch']],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recorded':True,'VMChecks':len(vm['checks']),'imageQualified':False,'flashed':False}))
