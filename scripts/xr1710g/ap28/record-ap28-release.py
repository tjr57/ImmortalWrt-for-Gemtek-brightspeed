from pathlib import Path
from datetime import datetime
import json,shutil
w=Path('D:/ChatGPT/XR1710G');r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap28';read=lambda p:json.loads(p.read_text(encoding='utf-8'))
ap={str(u):read(out/f'deployment/ap{u}/result.json') for u in [1,2]};packed=read(out/'packed-files-qa.json')
assert all(v['passed'] and v['imageSHA256']==packed['imageSHA256'] for v in ap.values())
assert ap['2']['at']<read(out/'deployment/ap1/scheduled.json')['at']
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':ap['1']['version'],'imageSHA256':packed['imageSHA256'],'change':'Default-off Mesh early RX drop flags for known peers','packetAcceptancePolicyChanged':False,'bothAP2ThenAP1KeepConfigUpgraded':True,'bothHealthy':True,'recorderDefaultOff':True,'NpuDefaultOff':True,'remainingMeshLossRootUnproven':True,'deployments':ap}
(out/'deployment/final-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=read(p);g['latestAP28']='development/ap28/deployment/final-result.json';g['objective']=g['objective'].replace('两台AP已部署AP27','两台AP已部署AP28')
for u,v in ap.items():g['networkState'][f'AP{u}']=f"AP28保留配置升级通过；boot {v['bootID']}；15项健康检查通过，NPU/PPE和观察点默认关闭。"
g['latestForwardingInvestigation']['deploymentInProgress']=False;g['latestForwardingInvestigation']['bothAP28Deployed']=True
g['nextConcreteRepair']='AP28两台升级完成；限时采集已知Mesh对端的驱动早期丢弃标记、mac80211处理器原因及四点ICMP头部，继续定位无线侧偶发丢包。'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');start=s.index('<!-- ap28-early-rx-work -->');end=s.index('<!-- owner-pause-for-appeal-20261010 -->')
note=f'''<!-- ap28-early-rx-work -->
## AP28 deployed; continuing early RX attribution

- Both AP28 accepted AP2 then AP1, configuration retained,15 checks each.
  AP1 boot {ap['1']['bootID']};
  AP2 boot {ap['2']['bootID']}.
  Image {packed['imageSHA256']}.
- All AP28 scheduled upgrades are complete: never resubmit. Records in
  development/ap28/deployment. No pending NPU activation.
- AP27 ping buffer fix remains proven by controlled4-point A/B. A distinct
  1/400 Mesh loss remained; receiver raw socket drops0 and no handler event
  within estimated arrival+/-100ms. That excludes neither delayed drops nor
  pre-handler stages. AP28 adds known-peer ONLY_MONITOR/FCS/PLCP observations.
- Observer remains default off; receive policy/kernel/DT/BusyBox/startup
  unchanged from AP27. NativeSanitizers/ARM/package/-j12/ABI/image checks pass.
- Next bounded test: environment/run-ap28-mesh-reasons.py. Each test path is
  one-shot. Check existing result/journal before invoking any tool again.

'''
p.write_text(s[:start]+note+s[end:],encoding='utf-8',newline='\n')
for n in ['record-ap28-release.py','run-ap28-mesh-reasons.py','analyze-ap28-mesh-reasons.py']:shutil.copy2(w/'environment'/n,r/'scripts/xr1710g/ap28'/n)
print(json.dumps({'passed':True,'version':report['version'],'bothDeployed':True,'imageSHA256':report['imageSHA256']}))
