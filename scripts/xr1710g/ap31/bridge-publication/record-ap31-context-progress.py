"""Record this completed private-candidate stage without claiming deployment."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib, json, shutil

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
out = w / 'development/ap31/ppe-context'
publisher = w / 'development/ap31/publisher'
now = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
qa = json.loads((out / 'qa.json').read_text())
build = json.loads((out / 'kernel-object-build.json').read_text())
vm = json.loads((publisher / 'vm-result.json').read_text())
unit = json.loads((publisher / 'unit-qa.json').read_text())
readback = json.loads((publisher / 'readback-qa.json').read_text())
tc = json.loads((publisher / 'tc-tiny-build.json').read_text())
assert all(x['passed'] for x in (qa, build, vm, unit, readback, tc))
assert qa['candidateSHA256'] == build['sourceSHA256']['airoha_ppe.c'] == sha(out / 'airoha_ppe.c')
assert vm['sourceSHA256'] == unit['sourceSHA256'] == readback['sourceSHA256'] == sha(publisher / 'xr_ppe_rules.py')
assert tc['binarySHA256'] == sha(publisher / 'tc-tiny-arm')
assert build['heldHashes'] == {p: sha(Path(p)) for p in build['heldHashes']}
progress = {
 'at': now, 'stage': 'private bridge-context and publisher-planner qualification',
 'patch': 'development/ap31/ppe-context/99999g-XR-exact-PPE-bridge-publication.patch',
 'candidateSHA256': qa['candidateSHA256'], 'qa': 'development/ap31/ppe-context/qa.json',
 'kernelObjectBuild': 'development/ap31/ppe-context/kernel-object-build.json',
 'publisherSource': 'development/ap31/publisher/xr_ppe_rules.py',
 'publisherUnitQA': 'development/ap31/publisher/unit-qa.json',
 'publisherReadbackQA': 'development/ap31/publisher/readback-qa.json',
 'realKernelVM': 'development/ap31/publisher/vm-result.json',
 'tcTinyBuild': 'development/ap31/publisher/tc-tiny-build.json',
 'implemented': [
  'inherit exact redirect/VLAN actions, tagged ingress key and generation revocation',
  'reject non-forwarding/down/carrierless ports and unsupported bridge port policies/MST',
  'RCU FDB API rejects missing, local, locked, expired and wrong-port forwarding entries',
  'MAC bridge templates reject tagged-to-tagged PCP/DEI loss; TC nonzero chains rejected',
  'expose revocation generation for future publisher reconciliation',
  'host planner builds hardware-only TC argv and exact-owned delete/re-add plans',
  'strict TC JSON selector/action/cookie readback; no adoption of software-only filters',
  'tc-tiny dependency chosen and privately compiled with flower/mirred/VLAN/clsact parsers'
 ],
 'validation': {'nativeASanUBSanAndARMContextChecksEach': 65734,
                'plannerCases': unit['checks'], 'readbackCases': readback['checks'],
                'realKernelBridgeProbeCases': vm['bridgeProbeCount'],
                'realKernelTCPrograms': 3, 'actualARMKernelObjects': ['airoha_ppe', 'br_fdb'],
                'jobs': 12, 'hardwarePositiveReadbackFlagsModeled': True},
 'previousActionPacketEvidence': 'development/ap31/ppe-vlan/packet-qa.json',
 'previousRevocationEvidence': 'development/ap31/ppe-revocation/qa.json',
 'contextTestsSupersedePreviousContextAcceptance': True,
 'previousFailedVMFixtureRunsRetained': True,
 'productionSourceConfigImageChanged': False, 'deviceChangedOrFlashed': False,
 'actualRuleExecutionImplemented': False,
 'policyLatchBypassed': False, 'hardwareBindingProven': False,
 'remaining': [
  'synchronous TC/bridge policy handoff before enabling a conflicting policy; userspace polling is insufficient',
  'FDB pre-notify/mutate/post-notify concurrency beyond the generation check',
  'rule executor plus coherent live collector and transaction cleanup under a qualified kernel policy lease',
  'full firmware dependency integration, ARM image/ABI build, AP2 then AP1 upgrade and hardware qualification'
 ]
}
(out / 'progress.json').write_text(json.dumps(progress, indent=2, ensure_ascii=False) + '\n')
goalpath = w / 'development/current-goal.json'
goal = json.loads(goalpath.read_text(encoding='utf-8-sig'))
previous = goal.get('latestPPECandidate')
history = goal.setdefault('previousPPECandidates', [])
if isinstance(history, list) and previous and previous not in history:
    history.append(previous)
goal['latestPPECandidate'] = progress
goal['lastDevelopmentUpdate'] = now
goal['latestPPEPublisherAudit'] = {'at': now, 'evidence': 'development/ap31/ppe-context/progress.json',
 'status': 'planner/readback and actual kernel API tests passed; executor/policy handoff unfinished',
 'tcVariant': 'tc-tiny', 'dependencies': tc['requiredPackages'],
 'runtimePolicyLatchRetained': True, 'productionFirmwareChanged': False}
goal['nextConcreteRepair'] = 'AP31桥接上下文修复已通过native/ARM、实际ARM内核目标文件和独立Linux VM；规则规划/所有权回读和tc-tiny候选已验证，尚未实现实际发布执行器。继续补齐TC/桥接策略生效前同步撤销、FDB通知与变更窗口以及执行器事务清理，再合入完整镜像、-j12编译并保留配置按AP2后AP1升级。保留现有policy latch；不能以用户态轮询代替内核顺序保证。'
goalpath.write_text(json.dumps(goal, indent=2, ensure_ascii=False) + '\n')

archive = r / 'scripts/xr1710g/ap31/bridge-publication'
for name in ('context', 'publisher'):
    (archive / name).mkdir(exist_ok=True)
for n in ('airoha_ppe.c', 'airoha_eth.h', 'br_fdb.c', 'if_bridge.h', 'progress.json'):
    shutil.copy2(out / n, archive / 'context' / n)
shutil.copy2(out / '99999g-XR-exact-PPE-bridge-publication.patch', archive / 'context/candidate.patch')
for n in ('xr_ppe_rules.py', 'unit-qa.json', 'readback-qa.json', 'vm-result.json', 'tc-tiny-build.json'):
    shutil.copy2(publisher / n, archive / 'publisher' / n)
for n in ('prepare-ap31-ppe-context.py', 'test-ap31-ppe-context.py', 'build-ap31-ppe-context.py',
          'test-ap31-ppe-publisher.py', 'test-ap31-ppe-readback.py', 'build-ap31-publisher-vm.py',
          'run-ap31-publisher-vm.py', 'build-ap31-tc-tiny.py', 'record-ap31-context-progress.py'):
    shutil.copy2(w / 'environment' / n, archive / n)
agent = r / 'AGENTS.md'
text = agent.read_text()
marker = '<!-- ap31-context-publisher-vm -->'
assert marker not in text, 'This record insertion has already run; do not repeat it.'
section = f'''
{marker}
## AP31 bridge context and publisher planner ({now})

- Current evidence: development/ap31/ppe-context/progress.json in Windows workspace.
- Private source only; production AP30 source/config/image and both APs unchanged.
- Adds real FDB forwarding lookup (local/locked/expired/wrong-port rejection),
  STP/carrier/port-policy/MST checks, chain-zero guard, and tagged-to-tagged
  fallback because POP/PUSH loses PCP/DEI. Supersedes prior context acceptance.
- 65734 nativeASan/UBSan + ARM context checks; actual ARM PPE and bridge objects
  built -j12. Independent Linux VM calls real FDB API and actual port predicate:
  14 probes; 3 real TC action programs, skip_sw failure and separate tagged/
  untagged priorities pass. VM fixture failures retained, no AP fault implied.
- Host planner/readback: 96+57 checks. No live executor yet. Positive hardware
  flags modeled; classifier in_hw is not proof of a bound PPE subflow.
- tc-tiny ARM privately built with required parsers. Dependencies also require
  kmod-sched-core/flower/act-vlan; not integrated into firmware config yet.
- Next: synchronous TC/bridge policy handoff, FDB notification mutation window,
  coherent collector and transaction executor. Keep policy latch; no polling-
  only permission. Mesh PPE path still unqualified. Then full image/AP2/AP1.
- Current combined patch: scripts/xr1710g/ap31/bridge-publication/context/candidate.patch.
  It is NOT installed under target/linux/airoha/patches-6.18 yet.
- Existing one-shot AP30 upgrades/trials remain final; never rerun them.
<!-- /ap31-context-publisher-vm -->

'''
agent.write_text(text.replace('# XR1710G development context\n', '# XR1710G development context\n' + section, 1))
print(json.dumps({'recorded': True, 'evidence': 'development/ap31/ppe-context/progress.json',
                  'productionOrDeviceChanged': False, 'goalStillInProgress': True}))
