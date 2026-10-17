from pathlib import Path
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap30'
qa=json.loads((out/'packed-files-qa.json').read_text());assert qa['passed']
dest=r/'scripts/xr1710g/ap30';dest.mkdir(exist_ok=True)
for n in ['check-ap30-build.py','ap30-deploy.py','export-ap30.py']:shutil.copy2(w/'environment'/n,dest/n)
for n in ['record-ap29-release.py','prepare-ap29-live-test.py','run-ap29-rx-origin1.py','analyze-ap29-rx-origin1.py','prepare-ap29-size-test.py','run-ap29-rx-origin2.py','analyze-ap29-rx-origin2.py']:shutil.copy2(w/'environment'/n,r/'scripts/xr1710g/ap29'/n)
p=r/'AGENTS.md';s=p.read_text();assert '<!-- ap30-eht-header -->' not in s
s=s.replace('# XR1710G development context','# XR1710G development context\n\n'+f'''<!-- ap30-eht-header -->
## AP30 EHT header correction candidate

- AP29 live small/large probes1080/1079. Missing requestAP1->AP2 aligns
  within0.205ms with software PN rejection onAP2, flagEHT_TLV,slot16,
  seq908,PNdelta-1,previousseq0. Socketdrops0; no driverICV events.
- Proven code defect: mt76_skb_get_hdr skipped HE metadata only. EHT
  U-SIG type33 at skb->data was misclassified as management, selecting
  the wrong PN slot16. Producer/mac80211 contract requires saved mac_header.
- AP30 uses that saved header for TLV frames.496 exact-source fixtures,
  including240 old-code cross-TID false rejects, nativeASan/UBSan/ARM pass.
  Same-TID equal/older PN and actual management replay rejection preserved.
- Built-j12/ABI/packed checks pass. Image {qa['imageSHA256']}.
  Not flashed at export. One-shot state development/ap30/deployment/apN;
  accept AP2 then AP1, preserve config, never resubmit scheduled operations.
- Both AP29 healthy and all diagnostic trials cleaned. NPU/PPE off; no
  pending NPU activation. AP30 post-fix live reproduction still required.
''',1);p.write_text(s)
p=w/'development/current-goal.json';g=json.loads(p.read_text());g['latestForwardingInvestigation']['AP29CauseEvidence']='development/ap29/forwarding/software-rx-origin2/analysis.json';g['latestForwardingInvestigation']['AP30Candidate']=qa['imageSHA256'];g['latestForwardingInvestigation']['EHTHeaderDefectReproduced']=True;g['latestForwardingInvestigation']['deploymentInProgress']=True;g['nextConcreteRepair']='AP30修复EHT元数据被误读为管理帧头导致选错PN计数器；编译通过，保留配置AP2后AP1升级并复测。';p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['git','add','--','AGENTS.md','xr1710g-ap.config','scripts/xr1710g/ap29','scripts/xr1710g/ap30','package/kernel/mt76/Makefile','package/kernel/mt76/patches/9999u-XR-use-saved-MAC-header-for-EHT-RX.patch'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
subprocess.run(['python3',str(w/'environment/record-ap-build.py'),'--version','20261010-ap30-d331711d','--destination-name','20261010-ap30-d331711d-development','--artifact-report',str(out/'artifact-qa.json'),'--defaults-qa',str(out/'defaults-qa.json'),'--build-log','build-ap30.log'],check=True)
