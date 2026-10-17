from pathlib import Path
from datetime import datetime
import json,shutil
w=Path('D:/ChatGPT/XR1710G');r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap30';read=lambda p:json.loads(p.read_text(encoding='utf-8'))
ap={str(u):read(out/f'deployment/ap{u}/result.json') for u in [1,2]};qa=read(out/'packed-files-qa.json')
assert all(v['passed'] and v['imageSHA256']==qa['imageSHA256'] for v in ap.values())
assert ap['2']['at']<read(out/'deployment/ap1/scheduled.json')['at']
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':ap['1']['version'],'imageSHA256':qa['imageSHA256'],'change':'Correct EHT TLV MAC header selection; preserve per-TID replay checks','correctPNCounterSelection':True,'replayChecksPreserved':True,'bothAP2ThenAP1KeepConfigUpgraded':True,'bothHealthy':True,'recorderDefaultOff':True,'NpuDefaultOff':True,'EHTHeaderDefectReproducedAndFixed':True,'postFixLiveProbePending':True,'deployments':ap}
(out/'deployment/final-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=read(p);g['latestAP30']='development/ap30/deployment/final-result.json';g['objective']=g['objective'].replace('两台AP已部署AP29','两台AP已部署AP30')
for u,v in ap.items():g['networkState'][f'AP{u}']=f"AP30保留配置升级通过；boot {v['bootID']}；15项健康检查通过，NPU/PPE和观察点默认关闭。"
g['latestForwardingInvestigation']['deploymentInProgress']=False;g['latestForwardingInvestigation']['bothAP30Deployed']=True;g['nextConcreteRepair']='AP30两台升级完成；重复小报文/1400字节并发探测，验证EHT帧头修复。'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');a=s.index('<!-- ap30-eht-header -->');z=s.index('<!-- ap29-rx-origin -->',a)
note=f'''<!-- ap30-eht-header -->
## AP30 EHT header fix deployed; equivalent probes next

- Both AP30 accepted AP2 then AP1,15 health checks/config retained each.
  AP1 boot {ap['1']['bootID']}; AP2 boot {ap['2']['bootID']}.
  Image {qa['imageSHA256']}. All upgrades complete; NEVER resubmit.
- AP29 captured software PN rejection aligned within0.205ms to a missing
  request onAP2: EHT TLV flag,slot16,seq908,PNdelta-1. Queue drops0.
- Defect reproduced: generic RX header helper read EHT U-SIG type33 as
  management frame control, using wrong PN counter. AP30 honors saved
  mac_header per producer/mac80211 contract.496 exact-source/native/ARM
  cases preserve real replay rejection; built-j12/ABI/packed gates pass.
- Both default-off observers remain present; NPU/PPE off. Next one-shot
  environment/run-ap30-rx-origin1.py repeats56/1400-byte probes with4point
  headers and rejection metadata. Do not claim all historical faults fixed.

'''
p.write_text(s[:a]+note+s[z:],encoding='utf-8',newline='\n')
for n in ['record-ap30-release.py','prepare-ap30-live-test.py','run-ap30-rx-origin1.py','analyze-ap30-rx-origin1.py']:shutil.copy2(w/'environment'/n,r/'scripts/xr1710g/ap30'/n)
print(json.dumps({'passed':True,'version':report['version'],'bothDeployed':True,'imageSHA256':qa['imageSHA256']}))
