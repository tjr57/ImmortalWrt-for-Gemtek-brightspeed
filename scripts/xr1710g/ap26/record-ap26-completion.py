"""Record AP26 deployment and the rejected, recovered transit trial honestly."""
from pathlib import Path
from datetime import datetime
import json,shutil

w=Path('D:/ChatGPT/XR1710G')
r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt')
out=w/'development/ap26'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
deployment=read(out/'deployment/final-result.json')
trial=read(out/'npu-wired-mesh-ap1/result.json')
analysis=read(out/'npu-wired-mesh-ap1/analysis.json')
assert deployment['passed'] and trial['ordinaryRecoveryAndCleanupPassed'] and trial['bothHealthy']
assert analysis['evidenceAnalysisPassed'] and not analysis['operationalQualificationPassed']
assert not trial['kernelFaultObserved'] and trial['captureContinuousAndComplete']
ap1=analysis['normalRecoveredBootID']
ap2=read(out/'deployment/ap2/result.json')['bootID']
result={
 'at':datetime.now().astimezone().isoformat(),
 'version':deployment['version'],'imageSHA256':deployment['imageSHA256'],
 'developmentAndDeploymentPassed':True,'bothAP2ThenAP1Upgraded':True,
 'currentBothHealthy':True,'currentBoots':{'AP1':ap1,'AP2':ap2},
 'configurationPreserved':True,'currentNpuPpeFlagsOff':True,
 'transitOperationalQualificationPassed':False,
 'newMapleOrOtherKernelFaultObserved':False,'MapleInvestigationDeferredPerOwner':True,
 'evidence':{'deployment':'development/ap26/deployment/final-result.json',
             'transit':'development/ap26/npu-wired-mesh-ap1/analysis.json',
             'ppeGaps':'development/ap26/ppe-topology-audit.json'},
 'nextWork':[
  'Separate WLAN NPU DMA from PPE forwarding in implementation and acceptance.',
  'Use a new targeted comparison to attribute the single lost Mesh ICMP reply; preserve this rejected epoch and its acceptance threshold.',
  'Establish firmware support for Mesh headers, path/TTL/sequence and peer lifetime before adding a hardware Mesh forward path.',
  'Implement exact permitted-rule publication and ordered policy revocation for supported PPE paths; review inactive bridge-hook latching.',
 ],
 'scopeLimits':['No persistent experimental activation','No phone acceptance in this round',
                'Neither 933Mbps nor clean TXFREE samples qualify the rejected epoch or demonstrate NPU speedup',
                'No main-router, switch, PC-network or original-Debian configuration changes'],
}
(out/'completion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=w/'development/current-goal.json';g=read(p)
g['latestAP26Completion']='development/ap26/completion.json'
g['latestNpuTransit']='development/ap26/npu-wired-mesh-ap1/analysis.json'
g['currentNpuConclusion']['experiments']='AP26实际有线到Mesh转发试验已结束并恢复清理。单向20秒/P4 TCP接收932.84Mbps，但随后AP1到AP2的5次ping丢1包，整轮不通过、反向未运行。73685次采样TXFREE消息无错误，380条连续内核记录无崩溃。不得重跑已提交操作；此前AP25结果保留。'
g['nextConcreteRepair']='AP26已完成PPE桥接策略界面/API修正、编译和双机升级。下一步分开推进无线NPU转发丢包归因，以及PPE的精确规则下发、非活动桥接钩子处理和802.11s固件能力核验；不能仅增加Mesh分支或打开开关就宣称全硬件转发。Maple专项排查继续暂缓。'
for unit,boot in [('AP1',ap1),('AP2',ap2)]:
 g['networkState'][unit]=f'AP26；boot {boot}；最新15项健康检查通过，管理/Mesh/Tizer/Poro正常，实验参数关闭。AP1已从限时诊断自动恢复，AP2保持原启动。'
p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');marker='<!-- ap26-transit-complete -->'
assert marker not in s,'Already recorded; do not duplicate completion context'
block=f'''{marker}
## AP26 real wired/Mesh transit trial complete; rejected and recovered

- Both production AP26 healthy, all15 checks per AP. AP1 ordinary boot
  {ap1}; AP2 unchanged boot {ap2}.
- development/ap26/npu-wired-mesh-ap1 operation COMPLETE and cleaned.
  NEVER rerun its one-shot script or operation. Temporary helpers removed;
  config/root/critical hashes retained, all experimental flags back off.
- One20s/P4 PC->switch->AP1 LAN2->Mesh->AP2 TCP payload finished932.84Mbps,
  but AP1->AP2 post-transfer ping lost1of5. Epoch remains REJECTED; reverse
  was canceled. Do not relax the gate or claim this throughput qualifies NPU.
- 73685 sampled TXFREE messages clean,380 continuous kernel records, no
  new Maple/other kernel fault. Automatic180s deadline recovery confirmed.
  Owner Maple deferral remains controlling; this was a forwarding trial.
- Current mac80211 lacks Mesh net_fill_forward_path and header-offload
  support. PPE also needs exact TC rule publication and correct handling
  of inactive bridge hooks. Do not add a Mesh case without proving firmware
  header/path/TTL/sequence/peer lifetime semantics. Wireless DMA is separate.
- Latest development/ap26/completion.json and ppe-topology-audit.json.

'''
anchor='<!-- ap26-current -->';assert anchor in s
p.write_text(s.replace(anchor,block+anchor,1),encoding='utf-8',newline='\n')
for name in ['analyze-ap26-npu-transit.py','record-ap26-ppe-topology.py','record-ap26-completion.py']:
 shutil.copy2(w/'environment'/name,r/'scripts/xr1710g/ap26'/name)
print(json.dumps({'recorded':True,'bothHealthy':True,'trialQualified':False,'currentBoots':result['currentBoots']}))
