from pathlib import Path
from datetime import datetime
import json,shutil
w=Path('D:/ChatGPT/XR1710G');r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap29';read=lambda p:json.loads(p.read_text(encoding='utf-8'))
ap={str(u):read(out/f'deployment/ap{u}/result.json') for u in [1,2]};qa=read(out/'packed-files-qa.json')
assert all(v['passed'] and v['imageSHA256']==qa['imageSHA256'] for v in ap.values())
assert ap['2']['at']<read(out/'deployment/ap1/scheduled.json')['at']
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':ap['1']['version'],'imageSHA256':qa['imageSHA256'],'change':'Default-off6GHz mt76 driver versus PN rejection scalar observer','packetAcceptancePolicyChanged':False,'bothAP2ThenAP1KeepConfigUpgraded':True,'bothHealthy':True,'recorderDefaultOff':True,'NpuDefaultOff':True,'remainingMeshLossRootUnproven':True,'deployments':ap}
(out/'deployment/final-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=read(p);g['latestAP29']='development/ap29/deployment/final-result.json';g['objective']=g['objective'].replace('两台AP已部署AP28','两台AP已部署AP29')
for u,v in ap.items():g['networkState'][f'AP{u}']=f"AP29保留配置升级通过；boot {v['bootID']}；15项健康检查通过，NPU/PPE和观察点默认关闭。"
g['latestForwardingInvestigation']['deploymentInProgress']=False;g['latestForwardingInvestigation']['bothAP29Deployed']=True;g['nextConcreteRepair']='AP29两台升级完成；限时采集驱动ONLY_MONITOR来源和软件PN拒绝的标量元数据，核对四点丢包证据。'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');a=s.index('<!-- ap29-rx-origin -->');z=s.index('<!-- ap28-early-rx-work -->',a)
note=f'''<!-- ap29-rx-origin -->
## AP29 deployed; RX origin trial next

- Both AP29 accepted AP2 then AP1,15 health checks/config retained each.
  AP1 boot {ap['1']['bootID']}; AP2 boot {ap['2']['bootID']}.
  Image {qa['imageSHA256']}. All submitted upgrades complete; NEVER repeat.
- AP28 software720/718: two AP2 replies absent at AP1 ingress, each within
  1ms of ONLY_MONITOR. Socket/capture drops0. Temporal, not unique identity.
- AP29 adds default-off6GHz scalar mt76 driver-flag/PN-rejection origins.
  Receive policy unchanged;78336 exact PN old/new fixture comparisons,
  nativeASan/UBSan/ARM,-j12,ABI,packed delta checks passed. NPU/PPE remain off.
- Next one-shot environment/run-ap29-rx-origin1.py; inspect journals before
  executing. Never repeat existing trial paths. Recorders/helpers cleaned
  after bounded tests. Root cause still unproven; no pending NPU activation.

'''
p.write_text(s[:a]+note+s[z:],encoding='utf-8',newline='\n')
for n in ['record-ap29-release.py','prepare-ap29-live-test.py','run-ap29-rx-origin1.py','analyze-ap29-rx-origin1.py']:shutil.copy2(w/'environment'/n,r/'scripts/xr1710g/ap29'/n)
print(json.dumps({'passed':True,'version':report['version'],'bothDeployed':True,'imageSHA256':qa['imageSHA256']}))
