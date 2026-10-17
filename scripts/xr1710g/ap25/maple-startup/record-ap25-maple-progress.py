from pathlib import Path
from datetime import datetime
import json,re,shutil,subprocess,hashlib
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap25'
read=lambda p:json.loads(p.read_text())
records={}
for unit,name in [(2,'maple-ap2-epoch1'),(1,'maple-ap1-load1')]:
 d=out/name
 if (d/'analysis.json').exists():records[str(unit)]={'analysis':read(d/'analysis.json'),'recovered':read(d/'recovered.json'),'result':read(d/'result.json')}
 elif (d/'operation.json').exists():records[str(unit)]={'operation':read(d/'operation.json')['status'],'completed':False}
report={'at':datetime.now().astimezone().isoformat(),'version':'20261010-ap25-d331711d','ownerHomeMode':True,'bothAP25KeepConfigDeployed':True,'newStartupARMChecks':28,'passiveModulePreviouslyGuestAndHardwareQualified':True,'kernelAndNpuBlobUnchanged':'AP24 accepted kernel; original uninstrumented NPU firmware','records':records,'TXFREEStartupRootCauseAlreadyProvenAndFixed':True,'MaplePhysicalRootStillUnproven':True,'goalComplete':False,'phoneTested':False}
(out/'maple-progress.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['AP25 Maple/NPU 实机推进记录',report['at'],'','两台 AP25 已完成保留配置升级，用户在家模式；新启动脚本28项 ARM 检查通过。']
for u,rec in records.items():
 if 'analysis' in rec:
  a=rec['analysis'];lines.append(f"AP{u}：本轮通过={a['passed']}，NPU启用{a['activeMs']/1000:.3f}秒，最高采样TXFREE={a['highestSampledTxfreeMessages']}，内核异常={a['kernelFaultObserved']}，已自动恢复并清理临时工具。")
  for t in a['transfers']:
   if t.get('qualified'):lines.append(f"  reverse={t['reverse']}，接收端实测 {t['receiverMbps']:.2f} Mbps。")
 else:lines.append(f"AP{u}：本轮已提交，正在收尾，不能重复启动。")
lines+=['','已证实的 TXFREE 启动预填充缺陷已修复。独立 Maple 异常尚未复现/证明根因，不能据短期无异常宣称整个 NPU 完全验收。未做手机、主路由有线 PPE 或长期负载验收。']
(out/'AP25-NPU与Maple实机结果.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
p=w/'development/current-goal.json';g=read(p);g['latestMapleEvidence']='development/ap25/maple-progress.json'
for u,rec in records.items():
 if 'recovered' in rec:g['networkState']['AP'+u]=f"AP25，单次NPU/Maple观察已结束并清理；boot {rec['recovered']['bootID']}；管理/Mesh/Tizer/Poro恢复，实验参数关闭。"
g['currentNpuConclusion']['MapleOops']='Passive observer integrated before NPU activation. Latest bounded hardware evidence is development/ap25/maple-progress.json; physical root remains unproven.'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=r/'AGENTS.md';s=p.read_text();s=re.sub(r'<!-- ap25-maple-current:start -->.*?<!-- ap25-maple-current:end -->\n*','',s,flags=re.S)
notice='''<!-- ap25-maple-current:start -->
## AP25 home-mode passive Maple observer trials

- Both AP25 upgrades COMPLETE; latest development/ap25/deployment/final-result.json.
- Exact new epoch state/results: development/ap25/maple-progress.json and
  maple-ap2-epoch1 / maple-ap1-load1. NEVER resubmit any existing operation.json.
- New role-specific startup helpers add qualified passive Maple observer before
  original NPU activation; 28 actual ARM shell cases passed. Native recovery/
  activation/address observer unchanged. AP2 first, then AP1 unpaced20s/P4
  each direction if AP2 accepted. Independent180s recovery always retained.
- TXFREE startup-prefill cause already proven/fixed. Separate historical Maple
  Oops physical cause remains unknown; no fault in bounded trials is not proof.
  Do not label AP-local TCP as wired/PPE, phone or long-term qualification.
<!-- ap25-maple-current:end -->

'''
pos=s.index('<!-- ap25-current');p.write_text(s[:pos]+notice+s[pos:])
d=r/'scripts/xr1710g/ap25/maple-startup'
for name in ['prepare-ap25-maple-load.py','run-ap25-maple-ap1-load1.py','analyze-ap25-maple.py','record-ap25-maple-progress.py','snapshot-ap25-maple-ap2-active.py']:
 shutil.copy2(w/'environment'/name,d/name)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap25/maple-startup'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'unitsWithEvidence':list(records),'goalComplete':False}))
