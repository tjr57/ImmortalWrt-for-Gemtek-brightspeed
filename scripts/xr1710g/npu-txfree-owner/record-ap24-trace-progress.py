from pathlib import Path
from datetime import datetime
import json,hashlib,re,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap24/owner-trace'
paths=['result.json','packed-startup.json','live-parser-qa.json','deployment/ap2-trace/result.json','ap2-epoch1/result.json','deployment/ap1-trace/result.json','ap1-epoch1/result.json','deployment/ap2-restore/result.json','deployment/ap1-restore/result.json','comparison.json']
records={n:{'sha256':hashlib.sha256((out/n).read_bytes()).hexdigest(),'data':json.loads((out/n).read_text())} for n in paths if (out/n).exists()}
progress={'at':datetime.now().astimezone().isoformat(),'previousGoalTurnClassification':'progress: AP24 code compiled, both upgraded, first original-firmware NPU trial clean with1155 TXFREE messages',
 'currentWork':'Compare NPU producer pointers after host ownership fix, then restore uninstrumented AP24 and bounded AP-to-AP load validation',
 'evidence':records,'goalComplete':False,'mainRouterSwitchPCNetworkChanged':False,'phoneTested':False}
(out/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
p=w/'development/current-goal.json';g=json.loads(p.read_text());g['status']='in-progress';g['latestAP24Trace']='development/ap24/owner-trace/progress.json';p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();s=re.sub(r'<!-- ap24-trace-current:start -->.*?<!-- ap24-trace-current:end -->\n?', '',s,flags=re.S)
notice='''<!-- ap24-trace-current:start -->
## AP24 ownership trace follow-up (2026-10-10)

- Previous goal turn made real progress: both AP24 production upgrades and
 original-firmware AP1 NPU178709ms/1155messages/zero mismatches, recovery passed.
- Now strengthen causal evidence with the same b48d5e6e producer hook as the
 before-fix AP1 failure. Private AP24 diagnostic FIT SHA
 36118e7b92ae453a38acfce4efc63b240f7ab4682a6a20e0b8f710fc817a3f4c.
 AP24 kernel/DT/modules/39 packed files unchanged; qualified recovery5,
 activation3 C plus early-debugfs helper4,14 packed ARM startup cases passed.
- Authoritative current transitions and trial results: development/ap24/
 owner-trace/progress.json; individual deployment/apN-trace|restore records.
 Never repeat any scheduled upgrade or submitted one-shot epoch. AP2 first,
 then AP1; restore original uninstrumented AP24 in that same order afterward.
- Scripts: ap24-trace-deploy.py UNIT trace|restore upgrade|inspect;
 run-ap24-trace-apN-epoch1.py run. Fixed role helpers source-bound to real VM.
 Live parser now separately accepts actual before/after SSH boot/time records;
 it must never forge a recovery5 envelope from raw debugfs bytes.
- No phone tests, main/switch/PC/global WSL changes, force upgrades or bootloader
 changes. Owner explicitly accepts remote access loss; do not ask again.
<!-- ap24-trace-current:end -->
'''
pos=s.index('<!-- ap24-current:start -->');p.write_text(s[:pos]+notice+'\n'+s[pos:])
d=r/'scripts/xr1710g/npu-txfree-owner'
for n in ('build-ap24-owner-trace.py','prepare-ap24-trace-tools.py','check-ap24-trace-startup.py','ap24-trace-deploy.py','prepare-ap24-trace-epochs.py','run-ap24-trace-ap1-epoch1.py','run-ap24-trace-ap2-epoch1.py','record-ap24-trace-progress.py'):
 shutil.copyfile(w/'environment'/n,d/n)
for n in ('xr_npu_producer_trace.py','test-npu-live-parser.py'):
 shutil.copyfile(w/'environment'/n,r/'scripts/xr1710g/npu-producer-reader'/n)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-txfree-owner','scripts/xr1710g/npu-producer-reader'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recordedEvidence':len(records),'goalComplete':False}))
