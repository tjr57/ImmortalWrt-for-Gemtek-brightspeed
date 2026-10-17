"""Finalize AP33 only after both one-shot deployments and postflight pass."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap33'
assert not (out/'release-result.json').exists(),'Already finalized'
packed=json.loads((out/'packed-files-qa.json').read_text())
results=[json.loads((out/f'deployment/ap{u}/result.json').read_text()) for u in [1,2]]
assert all(x['passed'] and x['configurationPreserved'] and x['version']==packed['version'] and x['imageSHA256']==packed['imageSHA256'] for x in results)
assert json.loads((out/'postflight.json').read_text())['passed']
vm=json.loads((out/'bridge-policy/vm-result.json').read_text());assert vm['passed']
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
remaining=['other netdevice and TC policy transition coverage','actual publisher and coherent collector under qualified policy control',
 'applicable hardware qualification with fresh AP33 ABI/address/recovery manifests']
report={'at':now,'version':packed['version'],'imageSHA256':packed['imageSHA256'],'imageSize':packed['imageSize'],
 'bothAPsDeployed':True,'deploymentOrder':[2,1],'configurationPreserved':True,
 'healthChecksEach':15,'bootIDs':{str(x['unit']):x['bootID'] for x in results},
 'sourceEvidence':'development/ap33/source-progress.json','imageEvidence':'development/ap33/packed-files-qa.json',
 'implemented':['15 VLAN/port/MST/membership mutation fences including error rollback',
 'PPE templates/packet key require per-VLAN forwarding state','L2 binding latched/revoked before policy observer teardown'],
 'nativeSanitizedAndARMChecksEach':{'context':66758,'packet':78682},'realKernelVMChecks':len(vm['checks']),
 'realKernelVMEvents':vm['eventCount'],'realKernelFailureInjections':len(vm['injections']),
 'liveWriterCountReturnsZero':True,'NpuPpeEnabled':False,'policyLatchRetained':True,
 'automaticRulePublisherShipped':False,'hardwareBindingProven':False,'phoneTested':False,
 'newThroughputOrLongTermQualification':False,'softwarePostflight':'development/ap33/postflight.json',
 'APBidirectionalProbes':'60/60','wiredPCtoAP2Probes':'10/10','remaining':remaining,
 'nextPolicyAudit':'development/ap33/next-policy-audit.json','mainRouterSwitchPCNetworkChanged':False}
(out/'release-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=json.loads(p.read_text())
g['latestAP33ImageBuild'].update(status='both-deployed-healthy',flashed=True,evidence='development/ap33/release-result.json')
g['latestAP33Release']=report
g['latestPPECandidate']['currentIntegration']={'version':packed['version'],'integrated':True,'bothAPsDeployed':True,
 'evidence':'development/ap33/release-result.json','automaticPublisherImplemented':False}
g['latestPPECandidate'].update(stage='deployed; remaining netdevice/TC policy and publisher work',flashed=True,remaining=remaining)
g['baselineHistory']=g.get('baselineHistory',[])+[g['baseline']]
g['baseline']={'version':packed['version'],'evidence':'development/ap33/release-result.json','evidenceAt':now,
 'bothAPsDeployedAndHealthyAtEvidenceTime':True,'configurationPreserved':True,'NpuPpeEnabled':False,
 'priorSoftwarePerformanceEvidence':'development/ap30/forwarding-completion.json','performanceRemeasuredOnThisVersion':False}
g['nextConcreteRepair']='AP33 两台保留配置升级完成，VLAN/端口修改事务及每 VLAN 转发资格通过源码、VM、编译和实机启动验证。继续其他 netdevice/TC 策略切换、实际发布器和一致性采集；适用硬件路径必须以新 ABI/地址/恢复契约单独验收。NPU/PPE 默认关闭。'
g['preflashPolicy'].update(currentCandidate=packed['version'],currentCandidateRequiresVM=True,currentCandidateVMGatePassed=True,
 currentCandidateVMGateScope='Real VLAN/port/MST mutations, switchdev failures and rollback; exact PPE context/key native/ARM; linked ARM image/module ABI',
 currentCandidateVMGateEvidence='development/ap33/boot-lab/result.json',currentCandidateImageSHA256=packed['imageSHA256'])
g['lastDevelopmentUpdate']=now
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();marker='<!-- ap33-deployed -->';assert marker not in s
entry=f'''
{marker}
## AP33 deployed to both APs ({now})

- Accepted {packed['version']}, AP2 then AP1; configuration preserved and
  15 health checks each. Image {packed['imageSHA256']}.
- AP1 boot {results[0]['bootID']}; AP2 boot {results[1]['bootID']}.
  Both AP33 deployment journals FINAL: never repeat an upgrade submission.
- VLAN/port policy fences and per-VLAN eligibility are deployed. VM38 checks,
  151 events, 5 injected failures; actual ARM and module ABI gates passed.
  NPU/PPE/default diagnostics remain off, policy latch retained, writers zero.
- Postflight AP60/60 plus wiredPC through Mesh10/10 (1400-byte payloads).
  No new throughput, hardware PPE, long-term or phone acceptance implied.
- Evidence D:/ChatGPT/XR1710G/development/ap33/release-result.json.
  Continue remaining netdevice/TC policy and actual publisher/collector work.
  New hardware trials require fresh AP33 manifests; AP2 remains Mesh-only.
<!-- /ap33-deployed -->
'''
p.write_text(s.replace('# XR1710G development context\n','# XR1710G development context\n'+entry,1))
dest=r/'scripts/xr1710g/ap33'
for name in ['record-ap33-release.py','ap33-postflight.py','record-ap33-next-policy-audit.py','record-ap33-image-qualification.py']:shutil.copy2(w/'environment'/name,dest/name)
for name in ['postflight.json','release-result.json','next-policy-audit.json','image-qualified.json']:shutil.copy2(out/name,dest/name)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap33'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recorded':True,**report}))
