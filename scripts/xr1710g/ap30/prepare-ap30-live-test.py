from pathlib import Path
w=Path('D:/ChatGPT/XR1710G')
for prefix in ['run','analyze']:
 old=w/f'environment/{prefix}-ap29-rx-origin2.py';s=old.read_text().replace('ap29','ap30').replace('AP29','AP30').replace('software-rx-origin2','software-rx-origin1')
 p=w/f'environment/{prefix}-ap30-rx-origin1.py';assert not p.exists();p.write_text(s);compile(s,str(p),'exec')
s=(w/'environment/record-ap29-release.py').read_text().replace('ap29','ap30').replace('AP29','AP30')
s=s.replace("g['objective'].replace('两台AP已部署AP28','两台AP已部署AP30')", "g['objective'].replace('两台AP已部署AP29','两台AP已部署AP30')")
s=s.replace("s.index('<!-- ap30-rx-origin -->')", "s.index('<!-- ap30-eht-header -->')").replace("s.index('<!-- ap28-early-rx-work -->',a)", "s.index('<!-- ap29-rx-origin -->',a)")
a=s.index("note=f'''");z=s.index("p.write_text(s[:a]+note+s[z:]",a)
s=s[:a]+'''note=f\'''<!-- ap30-eht-header -->
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

\'''
'''+s[z:]
s=s.replace('Default-off6GHz mt76 driver versus PN rejection scalar observer','Correct EHT TLV MAC header selection; preserve per-TID replay checks').replace("'packetAcceptancePolicyChanged':False", "'correctPNCounterSelection':True,'replayChecksPreserved':True").replace("'remainingMeshLossRootUnproven':True", "'EHTHeaderDefectReproducedAndFixed':True,'postFixLiveProbePending':True")
s=s.replace('AP30两台升级完成；限时采集驱动ONLY_MONITOR来源和软件PN拒绝的标量元数据，核对四点丢包证据。','AP30两台升级完成；重复小报文/1400字节并发探测，验证EHT帧头修复。')
s=s.replace("['record-ap30-release.py','prepare-ap30-live-test.py','run-ap30-rx-origin1.py','analyze-ap30-rx-origin1.py']", "['record-ap30-release.py','prepare-ap30-live-test.py','run-ap30-rx-origin1.py','analyze-ap30-rx-origin1.py']")
p=w/'environment/record-ap30-release.py';assert not p.exists();p.write_text(s);compile(s,str(p),'exec')
print('Prepared AP30 post-fix equivalent probes and release recorder')
