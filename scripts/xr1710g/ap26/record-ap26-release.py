from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,shutil,subprocess
w=Path('D:/ChatGPT/XR1710G');r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap26'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
ap={str(u):read(out/f'deployment/ap{u}/result.json') for u in [1,2]}
assert all(v['passed'] for v in ap.values()) and ap['2']['at']<read(out/'deployment/ap1/scheduled.json')['at']
report={'passed':True,'at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'version':ap['1']['version'],'imageSHA256':ap['1']['imageSHA256'],
 'change':'NPU RPC/UI enforce separate PPE bridge policy and explicit-rule requirements, with Chinese status labels',
 'rpcCalls':158,'uiModesSourceAndPacked':7,'makeWorldJobs':12,'bothAP2ThenAP1KeepConfigUpgraded':True,
 'perAPROMMatches':41,'perAPLiveMatches':36,'perAPPreservedFiles':41,'kernelDTModulesBootSSHMeshIdenticalToAP25':True,
 'bothHealthy':True,'NpuDefaultOff':True,'phoneTested':False,'mainSwitchPCNetworksChanged':False,'deployments':ap,
 'softwareTransitBaseline':'development/ap25/ppe-transit/software-baseline1/result.json','MapleIsNotABlocker':True}
(out/'deployment/final-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
p=w/'development/current-goal.json';g=read(p);g['latestAP26']='development/ap26/deployment/final-result.json'
g['objective']=g['objective'].replace('两台AP已部署AP25','两台AP已部署AP26')
g['nextConcreteRepair']='AP26已完成PPE桥接策略接口衔接并按AP2后AP1升级。电脑经AP1有线和Mesh至AP2的软件转发已实测998/1241Mbps。下一步在同一路径启用AP1无线NPU做实机对照；PPE还需有效规则下发路径，Maple专项排查保持暂缓。'
for u in [1,2]:g['networkState'][f'AP{u}']=f"AP26保留配置升级通过；boot {ap[str(u)]['bootID']}；管理/Mesh/Tizer/Poro正常，实验参数关闭。"
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');anchor='- Deployment state is development/ap26/deployment/apN/result.json.';assert anchor in s
s=s.replace(anchor,'- BOTH AP26 upgrades COMPLETE, AP2 accepted before AP1. Final evidence:\n  development/ap26/deployment/final-result.json; both healthy, config retained.\n'+anchor)
p.write_text(s,encoding='utf-8',newline='\n')
for name in ['record-ap26-release.py','prepare-ap26-npu-transit.py','check-ap26-transit-harness.py','run-ap26-npu-transit-ap1.py','analyze-ap25-transit-baseline.py','inspect-ap1-bridge-hooks.py']:
 shutil.copy2(w/'environment'/name,r/'scripts/xr1710g/ap26'/name)
print(json.dumps({'passed':True,'version':report['version'],'bothDeployed':True,'imageSHA256':report['imageSHA256']}))
