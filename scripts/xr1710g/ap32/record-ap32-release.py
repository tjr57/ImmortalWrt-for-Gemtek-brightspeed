"""Finalize AP32 only after both one-shot deployments and postflight pass."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap32'
assert not (out/'release-result.json').exists(),'release already finalized'
packed=json.loads((out/'packed-files-qa.json').read_text())
results=[json.loads((out/f'deployment/ap{u}/result.json').read_text()) for u in [1,2]]
assert all(x['passed'] and x['configurationPreserved'] and x['version']==packed['version'] and x['imageSHA256']==packed['imageSHA256'] for x in results)
post=json.loads((out/'postflight.json').read_text());assert post['passed']
vm=json.loads((out/'bridge-transaction/vm-result.json').read_text());assert vm['passed']
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
remaining=['other bridge/VLAN/netdevice and TC policy transition coverage',
 'actual rule execution with coherent live collection and qualified policy control',
 'applicable hardware qualification with fresh AP32 ABI/address/recovery manifests']
report={'at':now,'version':packed['version'],'imageSHA256':packed['imageSHA256'],
 'bothAPsDeployed':True,'deploymentOrder':[2,1],'configurationPreserved':True,
 'healthChecksEach':15,'bootIDs':{str(x['unit']):x['bootID'] for x in results},
 'sourceEvidence':'development/ap32/source-progress.json','imageEvidence':'development/ap32/packed-files-qa.json',
 'implemented':['FDB/STP mutation fence with nested and concurrent writer tracking',
 'PPE template publication and packet binding reject busy or stale bridge epochs'],
 'nativeSanitizedAndARMChecksEach':1050,'realKernelVMChecks':len(vm['checks']),
 'liveWriterCountReturnsZero':True,'NpuPpeEnabled':False,'policyLatchRetained':True,
 'automaticRulePublisherShipped':False,'hardwareBindingProven':False,'phoneTested':False,
 'newThroughputOrLongTermQualification':False,'softwarePostflight':'development/ap32/postflight.json',
 'APBidirectionalProbes':'60/60','wiredPCtoAP2Probes':'10/10','remaining':remaining,
 'mainRouterSwitchPCNetworkChanged':False}
(out/'release-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=json.loads(p.read_text())
g['latestAP32ImageBuild'].update(status='both-deployed-healthy',flashed=True,evidence='development/ap32/release-result.json')
g['latestAP32Release']=report
g['latestPPECandidate']['currentIntegration']={'version':packed['version'],'integrated':True,'bothAPsDeployed':True,
 'evidence':'development/ap32/release-result.json','automaticPublisherImplemented':False}
g['latestPPECandidate'].update(stage='deployed; remaining bridge/TC policy work',flashed=True,remaining=remaining)
g['baselineHistory']=g.get('baselineHistory',[])+[g['baseline']]
g['baseline']={'version':packed['version'],'evidence':'development/ap32/release-result.json','evidenceAt':now,
 'bothAPsDeployedAndHealthyAtEvidenceTime':True,'configurationPreserved':True,'NpuPpeEnabled':False,
 'priorSoftwarePerformanceEvidence':'development/ap30/forwarding-completion.json','performanceRemeasuredOnThisVersion':False}
g['nextConcreteRepair']='两台已保留配置升级 AP32 并通过启动/Mesh/服务及 70 个连通探测。FDB/STP 修改事务及数据包读取上下文的并发窗口已实现并验证；继续梳理其他桥接/VLAN/netdevice/TC 策略变更，随后完成适用路径的实际发布器和一致性采集。NPU/PPE 默认关闭；新硬件试验必须采用 AP32 ABI/地址/恢复清单，不复用旧轮次。'
g['preflashPolicy'].update(currentCandidate=packed['version'],currentCandidateRequiresVM=True,currentCandidateVMGatePassed=True,
 currentCandidateVMGateScope='Actual FDB/STP mutation ordering, nested/failure exits, active-writer registration; exact PPE functions native/ARM; linked ARM image and module ABI',
 currentCandidateVMGateEvidence='development/ap32/boot-lab/result.json',currentCandidateImageSHA256=packed['imageSHA256'])
g['lastDevelopmentUpdate']=now
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();marker='<!-- ap32-deployed -->';assert marker not in s
entry=f'''
{marker}
## AP32 deployed to both APs ({now})

- Accepted {packed['version']}, AP2 then AP1, same retained configuration,
  138 ROM/130 live files and 15 health checks each. Image {packed['imageSHA256']}.
- AP1 boot {results[0]['bootID']}; AP2 boot {results[1]['bootID']}.
  Both deployment/apN/scheduled.json journals are FINAL; never repeat upgrades.
- New FDB/STP/packet-epoch guards present; writer telemetry returns zero.
  NPU/PPE/default diagnostics remain off and filtering policy latch retained.
  Postflight 1400-byte software probes AP60/60, PC through Mesh10/10; no new
  throughput, long-term, hardware binding or phone verdict.
- Current evidence development/ap32/release-result.json, Windows workspace.
  Continue other bridge/VLAN/netdevice/TC policy coverage and actual executor/
  coherent collector. This release alone does not complete the broader goal.
- AP2 remains Mesh-only. New NPU/PPE trials require fresh AP32 ABI/address/
  recovery manifests. Previous epochs/upgrades remain final and must not run.
<!-- /ap32-deployed -->
'''
p.write_text(s.replace('# XR1710G development context\n','# XR1710G development context\n'+entry,1))
dest=r/'scripts/xr1710g/ap32'
for name in ['record-ap32-release.py','ap32-postflight.py']:shutil.copy2(w/'environment'/name,dest/name)
for name in ['postflight.json','release-result.json']:shutil.copy2(out/name,dest/name)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap32'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recorded':True,**report}))
