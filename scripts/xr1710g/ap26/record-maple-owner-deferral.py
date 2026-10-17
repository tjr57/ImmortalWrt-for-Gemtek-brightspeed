"""Record the owner's revised acceptance boundary without altering evidence."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

workspace = Path('D:/ChatGPT/XR1710G')
source = Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt')
at = datetime.now(timezone(timedelta(hours=8))).isoformat()
decision = {
    'at': at,
    'directOwnerInstruction': '近期没有复现就先当做是暂时没问题，直至在此出现Maple Tree 内核崩溃为止',
    'status': 'provisionally-accepted-until-recurrence',
    'blocksDevelopmentOrNpuQualification': False,
    'dedicatedRootCauseInvestigationPaused': True,
    'rootCauseProven': False,
    'reopenTrigger': 'A new observed Maple Tree kernel crash; retain the new boot, firmware and fault evidence, then investigate.',
    'recentEvidence': 'development/ap25/maple-progress.json',
    'historicalFaultEvidence': 'development/ap18/npu-hardware/baseline-mode0-v4/qualified-evidence.json',
    'nextWork': 'Continue actual forwarding/PPE integration and NPU hardware validation; do not repeat completed Maple diagnostic epochs or require historical Maple root-cause proof as a prerequisite.',
    'deviceConfigurationChangedByThisDecision': False,
    'historicalEvidencePreserved': True,
}
record = workspace/'development/ap25/maple-deferred-by-owner.json'
assert not record.exists(), 'Decision already recorded; inspect rather than duplicate.'
goal_path = workspace/'development/current-goal.json'
goal = json.loads(goal_path.read_text(encoding='utf-8'))
goal['mapleOwnerDecision'] = decision
goal['currentNpuConclusion']['MapleOops'] = 'Owner provisionally accepts recent non-recurrence. Dedicated investigation is deferred and does not block development or NPU qualification; reopen upon a new Maple Tree kernel crash. Historical physical root remains unproven.'
goal['remainingNpuCodeInvestigation'] = 'Maple专项排查按用户要求暂缓，不阻塞开发；出现新的Maple Tree内核崩溃才重新开启。继续NPU/PPE实际转发与必要的代码、配置和硬件验证。'
goal['objective'] = '完成五项既定开发与适用的候选审查移植。两台AP已部署AP25，历史TXFREE启动缺陷已修复；继续NPU/PPE实际转发衔接与剩余代码、验证、编译和保留配置按AP2后AP1的升级。Maple近期未复现，按用户决定暂视为无问题，不阻塞开发；再次发生Maple Tree内核崩溃后再调查，不宣称历史根因已证明。'
goal['nextConcreteRepair'] = '继续NPU/PPE实际转发路径、策略衔接和必要负载验证。Maple按用户决定暂视为无问题，暂停专项排查，不作为前置阻塞条件；新崩溃发生后再重新定位。不要重复已经完成的诊断周期。'

agents_path = source/'AGENTS.md'
agents = agents_path.read_text(encoding='utf-8')
marker = '<!-- maple-owner-deferral-20261010 -->'
assert marker not in agents
heading = '# XR1710G development context\n'
assert agents.startswith(heading)
block = '''
<!-- maple-owner-deferral-20261010 -->
## Latest owner decision: Maple non-recurrence is provisionally accepted

- Direct owner instruction: treat recent absence of Maple Tree crashes as
  temporarily fine until a new Maple Tree kernel crash occurs.
- Pause dedicated Maple root-cause work. Historical Maple is NOT a blocker
  for development, NPU qualification or the remaining five-item chapter.
- Preserve the original crash and qualified trial evidence; its physical root
  remains unproven. Do not change this provisional acceptance into a claim
  that the historical defect was causally fixed.
- Continue actual NPU/PPE forwarding integration and hardware validation.
  Do not repeat completed Maple epochs or require more Maple-only tests.
- Reopen Maple investigation only upon a new observed Maple Tree crash,
  retaining that event's boot, firmware and fault evidence.
- This latest instruction supersedes earlier Maple-investigation priorities.
  Decision: development/ap25/maple-deferred-by-owner.json. This recording
  itself does not change device flags or configurations.

'''
agents_path.write_text(heading+block+agents[len(heading):], encoding='utf-8', newline='\n')
goal_path.write_text(json.dumps(goal, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
record.write_text(json.dumps(decision, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
assert json.loads(goal_path.read_text(encoding='utf-8'))['mapleOwnerDecision']['blocksDevelopmentOrNpuQualification'] is False
assert marker in agents_path.read_text(encoding='utf-8')
print(json.dumps({'recorded':True, 'record':str(record), 'MapleBlocksDevelopment':False,
                  'rootCauseClaimedFixed':False, 'deviceConfigurationChanged':False}, ensure_ascii=False))
