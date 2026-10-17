from pathlib import Path
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap29'
qa=json.loads((out/'packed-files-qa.json').read_text());assert qa['passed']
dest=r/'scripts/xr1710g/ap29';dest.mkdir(exist_ok=True)
for n in ['check-ap29-build.py','ap29-deploy.py','export-ap29.py']:shutil.copy2(w/'environment'/n,dest/n)
for n in ['run-ap28-mesh-reasons.py','analyze-ap28-mesh-reasons.py','run-ap28-mesh-reasons2.py','analyze-ap28-mesh-reasons2.py']:shutil.copy2(w/'environment'/n,r/'scripts/xr1710g/ap28'/n)
p=r/'AGENTS.md';s=p.read_text();assert '<!-- ap29-rx-origin -->' not in s
s=s.replace('# XR1710G development context','# XR1710G development context\n\n'+f'''<!-- ap29-rx-origin -->
## AP29 candidate: distinguish driver and PN receive rejection

- Both AP28 healthy; software-only720 probes718 received. Both missing
  replies reached AP2 egress but not AP1 ingress; AP1 ONLY_MONITOR within1ms
  of expected arrival. No raw socket or capture overflow. Temporal evidence
  is not unique packet attribution and does not yet identify ICV versus PN.
- AP29 default-off scalar mt76 observer distinguishes pre-existing driver
  flag from mt76 PN rejection. Receive verdicts unchanged;78336 exact old/new
  PN function fixture cases, nativeASan/UBSan/ARM and-j12/ABI/packed checks pass.
- Image {qa['imageSHA256']}; frozen destination
  builds/20261010-ap29-d331711d-development. Not flashed at export.
  One-shot deployment state development/ap29/deployment/apN. AP2 first,
  health/config preserved then AP1; never resubmit scheduled.json.
- NPU remains off. No pending NPU activation. All AP28 live trials complete
  and cleaned; do not rerun them. AP29 live cause still unproven.
''',1);p.write_text(s)
p=w/'development/current-goal.json';g=json.loads(p.read_text());g['latestForwardingInvestigation']['AP28LatestEvidence']='development/ap28/forwarding/software-mesh-reasons2/analysis.json';g['latestForwardingInvestigation']['AP28LossStage']='2/720: AP2 reply egress to AP1 pre-interface RX; ONLY_MONITOR within1ms, source not yet proven';g['latestForwardingInvestigation']['AP29Candidate']=qa['imageSHA256'];g['latestForwardingInvestigation']['deploymentInProgress']=True;g['nextConcreteRepair']='AP29默认关闭的驱动来源观察器编译通过；先AP2后AP1保留配置升级，区分硬件ICV标志和软件PN拒绝。';p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['git','add','--','AGENTS.md','xr1710g-ap.config','scripts/xr1710g/ap28','scripts/xr1710g/ap29','package/kernel/mt76/Makefile','package/kernel/mt76/patches/9999t-XR-opt-in-6GHz-RX-rejection-origin.patch'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
subprocess.run(['python3',str(w/'environment/record-ap-build.py'),'--version','20261010-ap29-d331711d','--destination-name','20261010-ap29-d331711d-development','--artifact-report',str(out/'artifact-qa.json'),'--defaults-qa',str(out/'defaults-qa.json'),'--build-log','build-ap29.log'],check=True)
