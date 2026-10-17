"""Record AP31 candidate evidence without replacing older trial verdicts."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
out=w/'development/ap31/ppe-revocation';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
qa=json.loads((out/'qa.json').read_text());build=json.loads((out/'kernel-object-build.json').read_text())
assert qa['passed'] and build['passed'] and qa['sourceSHA256']==build['candidateSHA256']==sha(out/'airoha_ppe.c')
for rel,digest in build['heldHashes'].items():assert sha(r/rel)==digest,rel
at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
candidate={'at':at,'evidence':'development/ap31/ppe-revocation/qa.json','packetEvidence':'development/ap31/ppe-vlan/packet-qa.json','kernelObjectBuild':'development/ap31/ppe-revocation/kernel-object-build.json',
 'patch':'development/ap31/ppe-revocation/99999g-XR-exact-PPE-bridge-publication.patch',
 'candidateSHA256':qa['sourceSHA256'],'candidatePrepared':True,'productionKernelOrFirmwareChanged':False,'integratedOrFlashed':False,
 'implemented':['single valid terminal redirect','canonical VLAN actions and bridge egress agreement','distinct tagged and PVID-normalized ingress authorization keys','invalidate in-flight rule preparation on context revocation'],
 'validation':{'packetAndActionChecksPerNativeAndARM':78679,'publicationChecksPerNativeAndARM':210,'nativeASanUBSan':True,'kernelAPIsModeledInBehaviorChecks':True,'actualArmKernelObjectBuild':True,'jobs':12},
 'historicalLossOrCrashCauseClaimed':False,
 'remaining':['actual rule publisher and ownership/reconciliation','bridge policy activation/reauthorization treatment','hardware binding and firmware semantics','full-image integration and deployment']}
goal_path=w/'development/current-goal.json';g=json.loads(goal_path.read_text(encoding='utf-8'))
prior=g.get('latestPPECandidate')
if prior and prior.get('evidence')!=candidate['evidence']:g.setdefault('previousPPECandidates',[]).append(prior)
g['latestPPECandidate']=candidate
g['nextConcreteRepair']='AP31已准备VLAN动作/带标签入口键/撤销代次候选，旧代码负对照、native/ARM和实际内核目标文件检查通过；尚未合入生产镜像。继续补齐精确规则发布与所有权/撤销协调、bridge policy处理，再进行完整编译和AP2后AP1升级。既有AP30实机试验不重跑、不追溯改判。'
g['lastDevelopmentUpdate']=at
goal_path.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'progress.json').write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n')
dest=r/'scripts/xr1710g/ap31/bridge-publication';dest.mkdir(parents=True,exist_ok=True)
names=['prepare-ap31-ppe-vlan.py','test-ap31-ppe-vlan.py','test-ap31-ppe-packet-key.py','build-ap31-ppe-vlan.py','prepare-ap31-ppe-revocation.py','test-ap31-ppe-revocation.py','record-ap31-ppe-progress.py']
for n in names:shutil.copy2(w/'environment'/n,dest/n)
shutil.copy2(out/'99999g-XR-exact-PPE-bridge-publication.patch',dest/'candidate.patch')
note=f'''<!-- ap31-bridge-publication-candidate -->
## AP31 bridge action/context candidate ({at})

- Latest scope/evidence: Windows development/current-goal.json and
  development/ap31/ppe-revocation/progress.json. Production remains unchanged.
- Private candidate fixes canonical VLAN/egress actions, distinguishes tagged
  packets from untagged PVID-normalized packets, and rejects in-flight rules
  prepared before a context revocation. Includes the earlier single-target check.
- Old-code negative controls reproduce tag-key aliasing and stale publication.
  Native ASan/UBSan + ARM:78679 action/packet checks and210 ordered pthread checks.
  Actual ARM kernel translation unit compiled-j12; this is not a linked image
  or hardware qualification. Kernel/cache APIs in behavioral fixtures are modeled.
- Continue exact rule publisher/ownership/reconciliation and policy handling.
  Do not clear the policy latch to enable an unrepresented bridge policy.
  Existing hardware/RF/PPE acceptance remains separate; no crash root claim.
- Candidate patch is scripts/xr1710g/ap31/bridge-publication/candidate.patch,
  NOT installed in target/linux/airoha/patches-6.18 yet.
- All AP30 submitted operations remain complete and must not run again.
<!-- /ap31-bridge-publication-candidate -->

'''
p=r/'AGENTS.md';s=p.read_text();assert '<!-- ap31-bridge-publication-candidate -->' not in s
p.write_text(s.replace('# XR1710G development context\n','# XR1710G development context\n\n'+note,1))
print(json.dumps({'recorded':True,'at':at,'candidateEvidence':candidate['evidence'],'productionOrDevicesChanged':False,'scriptsArchived':len(names)}))
