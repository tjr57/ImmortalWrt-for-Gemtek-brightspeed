"""Reconcile current evidence with the active next-stage goal; no device writes."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,shutil,hashlib
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
load=lambda p:json.loads((w/p).read_text())
state=load('development/current-goal.json')
trial_number=3 if (w/'development/ap30/forwarding/npu-transit3/operation.json').exists() else 2
trial=f'development/ap30/forwarding/npu-transit{trial_number}'
operation=load(trial+'/operation.json')
done=(w/trial/'result.json').exists() and operation['status']=='completed-recovered-cleaned'
state['status']='in-progress'
state['preflashPolicy']['ownerAway']=False
state['preflashPolicy']['ownerPresenceSource']='Latest direct owner instruction: 我已经回到家了，可以按照在家的模式推进项目，不需要保守。仍不得据此假设AP2已有有线或TTL。'
state['physicalRecoveryStatus']={'AP2MeshOnly':True,'independentCableOrTTLConfirmed':False,
 'ownerAcceptedProceedingWithinExistingScope':True,'missingPhysicalFallbackAloneIsNotCurrentBlocker':True}
state['latestFeatureCoverage']={'at':now,'evidence':'development/ap30/feature-coverage.json',
 'currentTopologyReviewed':True,'allInternetExhaustivelyReviewed':False,
 'nextMissingImplementation':'PPE rule publication and exact egress/VLAN/policy handling; Mesh egress firmware capability unproven.'}
state['latestDiagnosticWindow']={'at':now,'profileSeconds':480,'productionDefaultsChanged':False,
 'source':'development/ap30/npu-window480','limitsAndActualARMTestsPassed':True,
 'combinedVMRebootPairs':11,'shippedARMShellCases':12,'originalGateCases':78,'remotePolicyCases':40,'newWindowCases':52,
 'noRunningDeadlineExtension':True,'hardwareDeadlineAndClosureConfirmed':False}
state['currentNpuConclusion']['experiments']='AP30 transit1仅剩73.754秒，未发送负载；transit2原始流量144/144成功，但收尾脚本错误依赖已删除ready.json，原最终失败判定保留。transit3改为运行时保存就绪证据，使用固定480秒窗口。历史被拒绝试验保留原判。'
state['latestNpuTransit']={'at':now,'operation':trial+'/operation.json','status':operation['status'],
 'priorNoTrafficTrial':'development/ap30/forwarding/npu-transit1/result.json',
 'PPEEnabled':False,'NpuEnabledOnlyInBoundedAP1Boot':True,'noHistoricalRequalification':True}
if done:
 result=load(trial+'/result.json');recovery=load(trial+'/recovered.json')
 assert result['operationCompletedAndRecovered'] and result['ordinaryRecoveryAndCleanupPassed'] and result['bothHealthy']
 state['latestDiagnosticWindow']['hardwareDeadlineAndClosureConfirmed']=result['captureContinuousAndComplete']
 state['latestNpuTransit'].update(evidence=trial+'/result.json',
  boundedBidirectionalPassed=result['boundedBidirectionalTransfersQualified'],
  continuousCollector=result['captureContinuousAndComplete'],kernelFaultObserved=result['kernelFaultObserved'],
  receiverMbps=[x.get('receiverMbps') for x in result['traffic']],allTemporaryToolsRemoved=True,
  longTermAndPpeQualification=False)
 if (w/trial/'analysis.json').exists():state['latestNpuTransit']['analysis']=trial+'/analysis.json'
 state['networkState']['AP1']='AP30普通启动 '+recovery['bootID']+'；15项健康检查通过，NPU/PPE关闭，临时工具移除。证据时间 '+result['at']
 state['networkState']['AP2']='AP30，boot '+operation['AP2Before']['bootID']+' 未改变；15项健康检查通过，NPU/PPE关闭。证据时间 '+result['at']
 state['currentNpuConclusion']['experiments']+=f' transit{trial_number}双向限时验收='+str(result['boundedBidirectionalTransfersQualified'])+'；普通恢复和清理通过，不能代替长期稳定/PPE验收。'
 if result['boundedBidirectionalTransfersQualified']:
  state['nextConcreteRepair']='AP30新一轮限时双向NPU和完整恢复验收通过；继续按链路/CPU/重传证据核对吞吐差异，保持默认关闭。推进PPE规则发布、出口/VLAN动作及策略撤销衔接；AP31出口候选尚未合入完整镜像。所有已提交操作不得重跑。'
 else:
  state['nextConcreteRepair']='AP30 transit2收尾脚本错误依赖恢复后已删除的ready.json，原失败判定保留。修复采集闭合校验，下一轮必须在运行时保存guard-ready-live.json，再用新试验验证。继续PPE规则发布、出口/VLAN与策略衔接；AP31候选尚未合入镜像。所有已提交操作不得重跑。'
else:
 state['networkState']['AP1']='AP30固定480秒NPU诊断正在进行；仅监听现有operation，不得重复提交。'
 state['nextConcreteRepair']=f'等待现有AP30 transit{trial_number}操作自动恢复并读取result；不得再次提交。继续独立PPE源码审查，之后据证据推进规则/出口/VLAN与策略衔接。'
if (w/'development/ap30/forwarding/software-after-npu2/analysis.json').exists():
 state['latestSoftwareControl']={'evidence':'development/ap30/forwarding/software-after-npu2/analysis.json','passed':True,
  'receiverMbps':[1031.2672856892987,1114.6753801874977],'loadedEchoExchanges':144,'losses':0,'NpuPpeEnabled':False,
  'comparison':'development/ap30/forwarding/npu-software-comparison.json','randomizedRFControlledAB':False}
state['latestClosureRepair']={'evidence':'development/ap30/npu-closure/qa.json','offlineChecks':37,
 'liveGuardMustBeSavedBeforeRemoval':True,'oldEpoch2VerdictPreserved':True}
if (w/'development/ap30/ppe-path-scope.json').exists():
 state['latestPpePathScope']={'evidence':'development/ap30/ppe-path-scope.json','paths':6,
  'currentMeshFullPpeEgressImplemented':False,'firmwareCapabilityUnproven':True,'PpeHardwareQualified':False}
state['latestPPECandidate']={'evidence':'development/ap31/ppe-target/qa.json','candidatePrepared':True,
 'nativeAndARMChecksEach':1036,'productionKernelOrFirmwareChanged':False,'integratedOrFlashed':False,
 'scope':'Require one non-null redirect before flow preparation; reject multiple destinations. Not proof of any historical crash cause.',
 'nullTargetAlreadyCheckedByDSAAndLateL2Code':True,'rulePublicationAndVlanPolicyWorkStillNeeded':True}
if (w/'development/ap31/ppe-target/kernel-object-build.json').exists():
 state['latestPPECandidate']['kernelObjectBuild']='development/ap31/ppe-target/kernel-object-build.json'
state['lastDevelopmentUpdate']={'at':now,'goalStatus':'active','goalComplete':False,
 'progress':'recovery6实机验证、480秒诊断窗口源码/ARM/VM检查完成；PPE单一有效出口候选已离线复现并测试。',
 'next':state['nextConcreteRepair'],'NpuState':'off after recovery' if done else 'AP1 bounded diagnostic','PpeEnabled':False}
(w/'development/current-goal.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')

# Preserve reproducible source/tools, with evidence continuing to live in the
# workspace. Do not replace the distinct instrumented-firmware actor package.
dest=r/'scripts/xr1710g/ap30/next-stage';dest.mkdir(parents=True,exist_ok=True)
names=['prepare-ap30-recovery6-live.py','test-ap30-recovery6-live.py','test-npu-recovery6-ap30-shell.py',
 'prepare-ap30-npu-gates.py','run-ap30-npu-gates-vm.py','test-ap30-npu-recovery-shell.py','test-ap30-npu-startup.py',
 'audit-ap30-feature-coverage.py','audit-ap30-ppe-paths.py','prepare-ap30-npu-transit.py','run-ap30-npu-transit1.py',
 'prepare-ap30-window480.py','test-ap30-window480.py','test-ap30-window480-shell.py','test-ap30-window480-gates.py',
 'prepare-ap30-npu-transit2.py','run-ap30-npu-transit2.py','analyze-ap30-npu-transit2.py',
 'prepare-ap30-software-after-npu.py','run-ap30-software-after-npu.py','analyze-ap30-software-after-npu.py',
 'prepare-ap30-npu-transit3.py','run-ap30-npu-transit3.py','analyze-ap30-npu-transit3.py','compare-ap30-npu-software.py',
 'xr_npu_diagnostic_gates.py','xr_npu_closure.py','test-ap30-npu-closure.py','record-ap30-next-stage.py']
for name in names:shutil.copy2(w/'environment'/name,dest/name)
for p in (w/'development/ap30/npu-window480').glob('*/src/*'):
 target=dest/'window480'/p.relative_to(w/'development/ap30/npu-window480');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
candidate=r/'scripts/xr1710g/ap31/ppe-target';candidate.mkdir(parents=True,exist_ok=True)
for name in ['prepare-ap31-ppe-target.py','test-ap31-ppe-target.py','build-ap31-ppe-target.py']:shutil.copy2(w/'environment'/name,candidate/name)
shutil.copy2(w/'development/ap31/ppe-target/99999g-PPE-require-one-valid-egress.patch',candidate/'candidate.patch')
marker='<!-- ap30-window480-next-stage -->'
note=f'''{marker}
## AP30 bounded NPU validation and next PPE work ({now})

- The replacement app goal is active. Authoritative current scope and evidence:
  D:/ChatGPT/XR1710G/development/current-goal.json. Never mark the broad goal complete from a bounded test.
- Recovery6 ordinary hardware recovery passed; AP30 transit1 completed/recovered without throughput traffic because only73.754s remained before its fixed deadline. No old epoch was requalified.
- New fixed480s profile: exact native/ARM timing and actor/guard tests,11 real-kernel VM reboot pairs,12 actual shipped-shell checks,78 old gates+40 authorization-policy cases+52 explicit-window cases pass. No live deadline extension. Production instrumented actor package unchanged.
- AP30 transit2 original rejection is retained: finalizer expected ready.json after recovery intentionally removed it.37 closure checks pass; transit3 saves the live guard before removal. Software control after epoch2:1031.27/1114.68Mbps,144/144 probes.
- Current transit{trial_number} status: {operation['status']}. Journal {trial}/operation.json. NEVER submit this experiment again. {'Ordinary recovery/cleanup verified; both APs healthy and NPU/PPE off. Bounded acceptance: '+str(result['boundedBidirectionalTransfersQualified'])+'.' if done else 'Inspect existing process/artifacts and wait for automatic recovery; do not infer health until final checks.'}
- AP30 feature-coverage.json reviews the original5 and7 candidate groups using pinned source. Existing applicable ports are distinguished from physical acceptance; no claim allInternet is exhaustive.
- AP31 ppe-target is a candidate only: one valid egress before preparation;1036 native and ARM cases. DSA already handlesNULL and oldL2 rejects absent egress later, so this is NOT a demonstrated NULL-crash repair. Multiple redirect semantics and remaining VLAN/rule-publication/policy paths require completion. No firmware built/flashed from it.
- Preserve config and AP2-before-AP1 deployment order. AP2 still Mesh-only; no cable/TTL assumed. Main router/switch/PC network untouched. Phone acceptance remains separate.
<!-- /ap30-window480-next-stage -->

'''
p=r/'AGENTS.md';s=p.read_text()
if marker in s:
 start=s.index(marker);end=s.index('<!-- /ap30-window480-next-stage -->',start)+len('<!-- /ap30-window480-next-stage -->')
 s=s[:start]+s[end:].lstrip('\n')
anchor='# XR1710G development context\n';assert s.startswith(anchor)
p.write_text(anchor+'\n'+note+s[len(anchor):].lstrip('\n'))
print(json.dumps({'goalActive':True,'completedExperiment':done,'recordSynced':True,'sourceToolsPreserved':len(names)},ensure_ascii=False))
