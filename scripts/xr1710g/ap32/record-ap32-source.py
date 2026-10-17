"""Archive reproducible AP32 source/qualification and track integration state."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap32'
candidate=out/'packet-fence';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
qa=json.loads((candidate/'qa.json').read_text());arm=json.loads((candidate/'kernel-object-build.json').read_text())
vm=json.loads((out/'bridge-transaction/vm-result.json').read_text())
assert qa['passed'] and arm['passed'] and vm['passed']
assert qa['sourceSHA256']==sha(candidate/'airoha_ppe.c')
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
report={'at':now,'stage':'integrated, full image qualification pending','baseline':'20261011-ap31-d331711d',
 'version':'20261011-ap32-d331711d','candidateSHA256':qa['sourceSHA256'],
 'patch':'target/linux/airoha/patches-6.18/99999h-XR-PPE-bridge-mutation-fence.patch',
 'patchSHA256':sha(candidate/'99999h-XR-PPE-bridge-mutation-fence.patch'),
 'qa':'development/ap32/packet-fence/qa.json','ARMObjectBuild':'development/ap32/packet-fence/kernel-object-build.json',
 'realKernelVM':'development/ap32/bridge-transaction/vm-result.json','checksEachNativeSanitizedAndARM':1050,
 'realKernelChecks':len(vm['checks']),'realKernelEvents':vm['eventCount'],
 'implemented':['synchronous BEGIN/END around FDB create/delete/move/admin flags and STP changes',
 'absolute active-writer count with registration INIT and nested/concurrent writer fencing',
 'PPE template revoke before mutation, busy/stale publication rejection',
 'packet-key epoch captured before context read and checked before L2 subflow bind',
 'read-only active-writer telemetry; policy latch remains independent'],
 'realVMContainsNoPPEHardware':True,'oldCodeRacesReproducedInModeledCache':True,
 'VMFixtureFirstRunRetained':'development/ap32/bridge-transaction/vm-20261011-012519.json',
 'VMFixtureRepair':'Wait for asynchronous port states and disable unrelated IPv6 chatter before phase labels; all original checks retained',
 'productionSourceIntegrated':True,'flashed':False,'NpuPpeDefaultOff':True,
 'remaining':['other bridge/VLAN/netdevice/TC policy transition coverage',
 'coherent collector and actual rule execution under qualified kernel policy control',
 'full image/ABI validation and AP2 then AP1 preserve-config upgrade',
 'applicable hardware qualification with new-version recovery/ABI manifests']}
(out/'source-progress.json').write_text(json.dumps(report,indent=2)+'\n')
dest=r/'scripts/xr1710g/ap32';dest.mkdir(exist_ok=True)
for group in ['bridge-transaction','packet-fence']:
 d=dest/group;d.mkdir(exist_ok=True)
 source=out/group;prep=json.loads((source/'prepared.json').read_text())
 names=[Path(p).name for p in prep['sources']]
 names+=['before-'+Path(p).name for p in prep['sources']]
 names+=['99999h-XR-PPE-bridge-mutation-fence.patch','prepared.json','qa.json','kernel-object-build.json','transaction-contract.c']
 if group=='bridge-transaction':names+=['vm-build.json','vm-result.json','vm-20261011-012519.json']
 for name in names:shutil.copy2(source/name,d/name)
for p in (w/'environment').glob('*ap32*.py'):shutil.copy2(p,dest/p.name)
shutil.copy2(out/'source-progress.json',dest/'source-progress.json')
p=r/'AGENTS.md';s=p.read_text();marker='<!-- ap32-integrated -->';assert marker not in s
entry=f'''
{marker}
## AP32 bridge mutation fence integrated ({now})

- Latest evidence D:/ChatGPT/XR1710G/development/ap32/source-progress.json.
  Production patch 99999h adds synchronous FDB/STP mutation guards, coherent
  notifier registration, busy/stale template rejection and packet-key epochs.
- 1050 exact-function native sanitizer and ARM checks each; four actual ARM
  kernel translation units built -j12. Isolated real-kernel VM22checks/47events
  passed, including dynamic learning/move, nested/failure exits, STP and join.
  No hardware PPE binding implied. First fixture timing failure retained.
- Full AP32 build through xr1710g-safe-build.py; inspect build-ap32-process.json
  in /home/xrdev/artifacts/xr1710g. Then check image/ABI/rootfs and export.
- AP31 still deployed, read-only preflight both15health/no kernel faults.
  AP32 upgrade script checks deployment/apN/scheduled.json; never resubmit.
  AP2 before AP1, preserve config; AP2 remains Mesh-only, no cable/TTL assumed.
- NPU/PPE/default diagnostics unchanged/off. TC/other bridge policy coverage
  and actual executor remain unfinished; existing policy latch must remain.
  Never reuse AP30/AP31 kernel/address/recovery manifests for AP32 trials.
<!-- /ap32-integrated -->
'''
p.write_text(s.replace('# XR1710G development context\n','# XR1710G development context\n'+entry,1))
gpath=w/'development/current-goal.json';g=json.loads(gpath.read_text())
g['previousPPECandidates']=g.get('previousPPECandidates',[])+[g['latestPPECandidate']]
g['latestPPECandidate']=report
g['recordInterpretation']='baseline、currentChapter、nextConcreteRepair 及最新带版本的证据定义当前状态；较早记录为历史证据，不代表当前阻塞或重新验收结论。'
g['lastDevelopmentUpdate']=now
gpath.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['git','add','--','AGENTS.md','xr1710g-ap.config','scripts/xr1710g/ap32',report['patch']],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recorded':True,'checksEach':1050,'VMChecks':len(vm['checks']),'imageQualified':False,'flashed':False}))
