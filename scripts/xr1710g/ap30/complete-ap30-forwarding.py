from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json,hashlib,shutil
from xr_two_ap import WORKSPACE as w,connect,command
r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap30';read=lambda p:json.loads(p.read_text(encoding='utf-8'))
deploy=read(out/'deployment/final-result.json');probe=read(out/'forwarding/software-rx-origin1/analysis.json');transit=read(out/'forwarding/loaded-transit1/analysis.json');qa=read(out/'eht-header/live-pattern/result.json');packed=read(out/'packed-files-qa.json')
assert all(x['passed'] for x in [deploy,probe,transit,qa,packed]);assert probe['sent']==probe['received']==1080
assert all(not v for v in probe['driverReasonCounts'].values());assert all(read(out/'forwarding/software-rx-origin1/cleanup.json').values())
assert all(h['healthy'] for h in read(out/'forwarding/loaded-transit1/health-after.json').values())
def final(u):
 c=connect(u,via='lan')
 try:
  get=lambda s:command(c,s)[0].decode().strip()
  boot=get('cat /proc/sys/kernel/random/boot_id');assert boot==deploy['deployments'][str(u)]['bootID']
  assert get('cat /etc/openwrt_version')=='20261010-ap30-d331711d'
  controls=['mt76/npu_enable','airoha_eth/ppe_bind_enable','airoha_eth/ppe_bridge_bind_enable','mt76/rx_loss_audit','mac80211/mesh_rx_drop_audit']
  flags={p:get('/bin/cat /sys/module/'+p.replace('/','/parameters/',1)) for p in controls};assert set(flags.values())=={'N'}
  modules={p:get('sha256sum /'+p).split()[0] for p in ['bin/busybox','lib/modules/6.18.54/mt76.ko','lib/modules/6.18.54/mt7996e.ko','lib/modules/6.18.54/mac80211.ko']}
  assert all(h==packed['matchedFiles'][p] for p,h in modules.items())
  for p in ['/tmp/xr-ap30-clock','/tmp/xr-ap30-ping-receive-observer.so']:
   assert command(c,'test ! -e '+p+' && test ! -L '+p,check=False)[2]==0
  assert not any(line.split()[1].endswith(':14D2') and line.split()[3]=='0A' for line in get('cat /proc/net/tcp').splitlines()[1:]),'Owned port5330 still listening'
  return {'bootID':boot,'flags':flags,'runtimeHashes':modules,'ownedTemporaryHelpersAbsent':True,'ownedIperfListenerAbsent':True}
 finally:c.close()
with ThreadPoolExecutor(max_workers=2) as pool:live=dict(zip(['1','2'],pool.map(final,[1,2])))
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':'20261010-ap30-d331711d','imageSHA256':packed['imageSHA256'],'chapter':'Owned AP forwarding loss attribution and demonstrated code repairs','confirmedRepairs':[{'component':'BusyBox ping','defect':'Small raw receive queue missed replies already delivered through all four network points','fix':'64KiB requested receive headroom for IPv4/IPv6','evidence':'development/ap27/ping-rxbuf/live-queue-qa.json'},{'component':'mt76 EHT RX header selection','defect':'EHT U-SIG TLV read as MAC frame control, selecting management PN counter for QoS data','fix':'Honor the saved MAC header for radiotap TLV frames; retain replay protection','evidence':'development/ap30/causal-evidence.json'}],'nativeAndARMExactSourceCases':512,'postFixProbes':{'sent':1080,'received':1080,'peerHeadersAtEachOfFourStages':1920,'driverPNOrICVRejections':0},'loadedProbeExchanges':144,'loadedProbeLosses':0,'transfers':transit['transfers'],'bothAP2ThenAP1UpgradedAndHealthy':True,'configurationPreserved':True,'finalLive':live,'mainRouterSwitchPCNetworkOriginalDebianChanged':False,'phoneTested':False,'NpuPpeEnabled':False,'allHistoricalFaultsProvenFixed':False,'broaderProjectGoalComplete':False,'limits':['Live PN-to-ICMP correlation is temporal; exact bug mechanism separately reproduced in source fixtures','Bounded post-fix traffic is not long-term stability or NPU/PPE qualification','Historical NPU epochs remain rejected; do not retroactively mark them accepted']}
(out/'forwarding-completion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=out/'causal-evidence.json';cause=read(p);cause['hardwareFixVerificationPending']=False;cause['hardwareFixVerification']='development/ap30/forwarding-completion.json';cause['extendedObservedManagementOrderingCases']=16;cause['totalExactSourceCases']=512;p.write_text(json.dumps(cause,indent=2)+'\n')
p=out/'deployment/final-result.json';deploy['postFixLiveProbePending']=False;deploy['postFixLiveEvidence']='development/ap30/forwarding-completion.json';p.write_text(json.dumps(deploy,indent=2)+'\n')
p=w/'development/current-goal.json';g=read(p);g['latestForwardingInvestigation'].update({'currentChapterComplete':True,'AP30Completion':'development/ap30/forwarding-completion.json','EHTHeaderFixLiveVerified':True,'softwareLossAttributionCompleteForReproducedDefects':True,'historicalNpuEpochsRequalified':False,'deploymentInProgress':False});g['currentNpuConclusion']['forwardingAttribution']='AP30修复EHT帧头/PN计数器选择缺陷；AP27修复ping本地收包队列。软件路径1080/1080探测及双向负载144/144通过；未重新启用NPU/PPE，历史实验不追溯改判。';g['nextConcreteRepair']='本轮转发丢包归因与两个已证实缺陷的修复、编译、双AP部署及有线/Mesh复测完成。后续先验证recovery6的普通启动实机恢复和AP30版本门禁，再安排新的NPU转发试验；旧steady-npu-3已退役。';g['status']='in-progress';p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=r/'AGENTS.md';s=p.read_text(encoding='utf-8');a=s.index('<!-- ap30-eht-header -->');z=s.index('<!-- ap29-rx-origin -->',a)
note=f'''<!-- ap30-eht-header -->
## AP30 forwarding loss repair chapter completed

- Both AP30 live healthy,AP2 thenAP1 upgrades complete/config retained.
  AP1 boot {live['1']['bootID']}; AP2 boot {live['2']['bootID']}.
  Image {packed['imageSHA256']}. NEVER repeat submitted upgrades/trials.
- Two distinct proven defects repaired: AP27 BusyBox ping receive queue;
  AP30 mt76 EHT U-SIG TLV misread as MAC header, wrongly selecting PN slot16.
  Saved mac_header fix retains duplicate/old/management replay rejection.
-512 exact-source/nativeASan/UBSan/ARM cases pass. AP29 live PN rejection
  aligned within0.205ms to missing1400-byte request; correlation is temporal,
  not raw ICMP identity. Candidate mechanism separately proven by fixtures.
- AP30 post-fix1080/1080 probes,1920 matching headers at EACH of4points,
  zero driver PN/ICV events. Production observers off during two20s/P4 PC
  via switch/AP1 bridge/6GHz Mesh/AP2 endpoint transfers;144/144 load probes.
  Speeds {[round(t['receiverMbps'],2) for t in transit['transfers']]} Mbps.
- Latest D:/ChatGPT/XR1710G/development/ap30/forwarding-completion.json.
  Helpers/listener absent,observers and NPU/PPE off. No phone or mainrouter/
  switch/PC-network/originalDebian changes. Bounded tests not long-term/NPU
  acceptance; historical rejected epochs stay rejected. Broader goal unfinished.
- Next NPU work needs recovery6 live ordinary-boot qualification and fresh
  AP30 manifest/gates; old AP27steady-npu-3 is retired and MUST NOT run.

'''
p.write_text(s[:a]+note+s[z:],encoding='utf-8',newline='\n')
for n in ['record-ap30-release.py','record-ap30-cause.py','test-ap30-live-pattern.py','prepare-ap30-live-test.py','run-ap30-rx-origin1.py','analyze-ap30-rx-origin1.py','prepare-ap30-transit.py','run-ap30-transit.py','analyze-ap30-transit.py','complete-ap30-forwarding.py']:shutil.copy2(w/'environment'/n,r/'scripts/xr1710g/ap30'/n)
print(json.dumps({'passed':True,'version':report['version'],'postFixProbes':report['postFixProbes'],'loadedProbes':144,'transfers':transit['transfers'],'bothHealthy':True},indent=2))
