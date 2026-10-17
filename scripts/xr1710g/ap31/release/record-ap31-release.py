"""Record AP31 only after both one-shot upgrade acceptances exist."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib, json, shutil, subprocess

w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap31'
packed=json.loads((out/'packed-files-qa.json').read_text())
results=[json.loads((out/f'deployment/ap{u}/result.json').read_text()) for u in (1,2)]
assert all(x['passed'] and x['configurationPreserved'] and x['version']==packed['version'] and x['imageSHA256']==packed['imageSHA256'] for x in results)
post=json.loads((out/'postflight.json').read_text());assert post['passed']
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
report={'at':now,'version':packed['version'],'imageSHA256':packed['imageSHA256'],'bothAPsDeployed':True,
 'deploymentOrder':[2,1],'configurationPreserved':True,'healthChecksEach':15,
 'bootIDs':{str(x['unit']):x['bootID'] for x in results},'NpuPpeEnabled':False,
 'sourceEvidence':'development/ap31/ppe-context/progress.json','imageEvidence':'development/ap31/packed-files-qa.json',
 'TCDependenciesPresent':True,'automaticRulePublisherShipped':False,'hardwareBindingProven':False,
 'phoneTested':False,'newThroughputOrLongTermQualification':False,
 'softwarePostflight':'development/ap31/postflight.json','APBidirectionalProbes':'60/60','wiredPCtoAP2Probes':'10/10',
 'remaining':['synchronous TC/bridge policy handoff and FDB mutation ordering',
              'actual rule executor/coherent collector/transaction cleanup',
              'applicable PPE hardware qualification with fresh AP31 ABI and recovery manifests'],
 'mainRouterSwitchPCNetworkChanged':False}
(out/'release-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=json.loads(p.read_text(encoding='utf-8-sig'))
g['latestAP31ImageBuild'].update(status='both-deployed-healthy',flashed=True,evidence='development/ap31/release-result.json')
g['latestAP31Release']=report
g['latestPPECandidate']['currentIntegration']={'version':packed['version'],'integrated':True,'bothAPsDeployed':True,
 'evidence':'development/ap31/release-result.json','automaticPublisherImplemented':False}
g['baselineHistory']=g.get('baselineHistory',[])+[g['baseline']]
g['baseline']={'version':packed['version'],'evidence':'development/ap31/release-result.json','evidenceAt':now,
 'bothAPsDeployedAndHealthyAtEvidenceTime':True,'configurationPreserved':True,'NpuPpeEnabled':False,
 'priorSoftwarePerformanceEvidence':'development/ap30/forwarding-completion.json','performanceRemeasuredOnThisVersion':False}
g['nextConcreteRepair']='两台已保留配置升级AP31并通过启动/Mesh/服务健康检查；继续实现TC/桥接策略同步撤销及FDB变更顺序，再补实际规则执行器和一致性采集器。现有policy latch保持；PPE/NPU默认关闭。若安排硬件PPE/NPU试验，必须重新匹配AP31内核/ABI/恢复清单，不能复用AP30一次性试验或地址清单。'
g['lastDevelopmentUpdate']=now
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();marker='<!-- ap31-deployed -->';assert marker not in s
entry=f'''
{marker}
## AP31 deployed to both APs ({now})

- Both devices accepted {packed['version']}, AP2 then AP1; configuration
  hashes, ROM/live files, TC/modules and 15 health checks each passed.
- Image {packed['imageSHA256']}.
  AP1 boot {results[0]['bootID']}; AP2 boot {results[1]['bootID']}.
- Windows evidence development/ap31/release-result.json and deployment/apN.
  Both scheduled operations are FINAL: NEVER resubmit either AP31 upgrade.
- Kernel guards/dependencies integrated; automatic PPE publisher NOT shipped.
  NPU/PPE/default diagnostics remain off. No new throughput or phone verdict.
- Continue synchronous TC/bridge policy handoff and FDB mutation ordering,
  then actual executor/coherent collector. Keep policy latch. Existing AP30
  one-shot experiments remain final and their kernel/ABI/address manifests
  must not authorize a new AP31 hardware trial.
<!-- /ap31-deployed -->
'''
p.write_text(s.replace('# XR1710G development context\n','# XR1710G development context\n'+entry,1))
dest=r/'scripts/xr1710g/ap31/release'
shutil.copy2(w/'environment/record-ap31-release.py',dest/'record-ap31-release.py')
shutil.copy2(w/'environment/ap31-postflight.py',dest/'ap31-postflight.py')
shutil.copy2(out/'postflight.json',dest/'postflight.json')
shutil.copy2(out/'release-result.json',dest/'release-result.json')
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap31/release'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recorded':True,**report}))
