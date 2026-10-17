from pathlib import Path
from datetime import datetime
import json,shutil
w=Path('D:/ChatGPT/XR1710G');r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap27'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
ap={str(u):read(out/f'deployment/ap{u}/result.json') for u in [1,2]}
assert all(v['passed'] for v in ap.values()) and ap['2']['at']<read(out/'deployment/ap1/scheduled.json')['at']
packed=read(out/'packed-files-qa.json');assert all(v['imageSHA256']==packed['imageSHA256'] for v in ap.values())
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':ap['1']['version'],'imageSHA256':packed['imageSHA256'],'changes':['BusyBox ping64KiB receive-buffer floor','Default-off scalar mac80211 Mesh RX drop recorder'],'bothAP2ThenAP1KeepConfigUpgraded':True,'bothHealthy':True,'NpuDefaultOff':True,'recorderDefaultOff':True,'phoneTested':False,'mainSwitchPCNetworksChanged':False,'remainingMeshLossRootUnproven':True,'deployments':ap}
(out/'deployment/final-result.json').write_text(json.dumps(report,indent=2)+'\n')
p=w/'development/current-goal.json';g=read(p);g['latestAP27']='development/ap27/deployment/final-result.json';g['objective']=g['objective'].replace('两台AP已部署AP26','两台AP已部署AP27')
for u,v in ap.items():g['networkState'][f'AP{u}']=f"AP27保留配置升级通过；boot {v['bootID']}；15项健康检查通过，Mesh/Tizer/Poro正常，NPU/PPE和接收观察点默认关闭。"
g['latestForwardingInvestigation']['deploymentInProgress']=False;g['latestForwardingInvestigation']['bothAP27Deployed']=True
g['nextConcreteRepair']='AP27已按AP2后AP1部署。ping本地接收缓冲不足已修补并受控验证；继续使用默认关闭、限时启用的Mesh丢弃原因观察点定位NPU关闭时仍可见的链路路径丢包。'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');s=s.replace('## AP27 forwarding-loss investigation resumed; candidate ready for AP2 then AP1','## AP27 deployed AP2 then AP1; continuing software-path loss attribution')
start=s.index('- Current stable AP26 boot AP1');end=s.index('- AP27 software baseline',start)
s=s[:start]+f"- Both AP27 keep-config upgrades accepted, all15 health checks. AP1 boot\n  {ap['1']['bootID']}; AP2 {ap['2']['bootID']}.\n  No pending activation/upgrade. NPU and new observer default off.\n"+s[end:]
s=s.replace('- AP27 software baseline20s/P4','- AP26 software baseline20s/P4');s=s.replace('- Upgrade AP2 first, verify normal return before AP1. State is','- Both upgrades are COMPLETE. State is')
p.write_text(s,encoding='utf-8',newline='\n')
for name in ['record-ap27-release.py','run-ap27-mesh-reasons.py','analyze-ap27-mesh-reasons.py']:shutil.copy2(w/'environment'/name,r/'scripts/xr1710g/ap27'/name)
print(json.dumps({'passed':True,'version':report['version'],'bothDeployed':True,'imageSHA256':report['imageSHA256']}))
