from pathlib import Path
from datetime import datetime
import json,hashlib,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap25'
read=lambda p:json.loads(p.read_text())
ap={str(u):read(out/f'deployment/ap{u}/result.json') for u in [1,2]}
assert all(v['passed'] for v in ap.values())
assert ap['2']['at']<read(out/'deployment/ap1/scheduled.json')['at']
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':ap['1']['version'],'imageSHA256':ap['1']['imageSHA256'],'fix':'Tizer survives isolated gateway probe loss; default consecutive-failure threshold3, closed-gate recovery3','guardActualTicks':109,'oldCodeNegativeControlPassed':True,'makeWorldJobs':12,'bothAP2ThenAP1KeepConfigUpgraded':True,'perAPROMMatches':39,'perAPLiveMatches':34,'perAPPreservedFiles':41,'kernelDTModulesBootSSHMeshIdenticalToAP24':True,'bothHealthy':True,'NpuDefaultOff':True,'phoneTested':False,'mainSwitchPCNetworksChanged':False,'deployments':ap}
(out/'deployment/final-result.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'AP25-发布与验证.txt').write_text('AP25 已按 AP2→AP1 顺序保留配置升级完成。\n\n修复：Tizer 守护默认连续三次网关探测失败才关闭，短暂丢包后的首次恢复不会再误关闭；持续断网仍关闭，恢复需连续三次成功。\n验证：109 次完整守护检查、旧代码负对照、make world -j12、模块 ABI、14 项出厂/升级默认配置检查通过。两台分别核对39个ROM文件、34个生效文件、41个保留文件，管理、Mesh、Tizer/Poro正常。\n镜像SHA256：'+report['imageSHA256']+'\n内核、DT、模块、SSH及Mesh启动组件与AP24逐字节一致。NPU实验默认关闭，未做手机测试。\n用户已回家并授权直接实机推进。下一步：单次启动接入被动Maple故障观察模块，继续查明独立的历史内核异常；此前已证实并修复的TXFREE启动预填充问题不重复试验。\n',encoding='utf-8')
p=w/'development/current-goal.json';g=read(p);g['latestAP25']='development/ap25/deployment/final-result.json';g['objective']=g['objective'].replace('已恢复并部署 AP24','已恢复并部署 AP25');g['nextConcreteRepair']='接入已验证的被动Maple观察模块，先AP2单次NPU启动，继续独立的历史内核异常定位。'
for u in [1,2]:g['networkState'][f'AP{u}']=f"AP25 保留配置升级通过；boot {ap[str(u)]['bootID']}；管理/Mesh/Tizer/Poro正常，所有实验参数关闭。"
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();anchor='- Latest exact deployment evidence: development/ap25/deployment/ap2|ap1.';assert anchor in s
s=s.replace(anchor,'- Both keep-config upgrades COMPLETE, AP2 accepted before AP1;39ROM/34live/\n  41preserved files each, both healthy. Final: development/ap25/deployment/final-result.json.\n'+anchor)
p.write_text(s)
shutil.copy2(w/'environment/record-ap25-release.py',r/'scripts/xr1710g/ap25/record-ap25-release.py')
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap25/record-ap25-release.py'],cwd=r,check=True)
print(json.dumps({'passed':True,'AP25BothDeployed':True,'imageSHA256':report['imageSHA256']}))
