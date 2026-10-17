"""Record observed AP24 state without changing frozen builds or old evidence."""
from pathlib import Path
from datetime import datetime
import json,hashlib,re
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap24'
def read(p):return json.loads(p.read_text())
paths=['build-process.json','ownership-compiled-qa.json','boot-lab/result.json','deployment/ap2-upgrade/upgrade-returned.json','deployment/ap2-upgrade/result.json','deployment/ap1-upgrade/upgrade-returned.json','deployment/ap1-upgrade/result.json','deployment/final-result.json','npu-ap1-epoch1/result.json','npu-ap1-epoch1/analysis.json']
evidence={p:{'sha256':hashlib.sha256((out/p).read_bytes()).hexdigest(),'result':read(out/p)} for p in paths if (out/p).exists()}
report={'at':datetime.now().astimezone().isoformat(),'version':'20261010-ap24-d331711d',
 'imageSHA256':'411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0',
 'scope':'Guard generic host refill, cleanup, reset and polling from NPU-owned TXFREE descriptors',
 'reason':'AP1 producer captured table-derived 8a500080 vs descriptor 94671000 with len20/header92; AP2 normal first32 matched',
 'priorFaultEvidence':'development/npu-ap1-debugfs/live-epoch-1/analysis.json',
 'vmScope':'Actual changed DMA function bodies in real KASAN/lockdep kernel; DMA/allocator/queue fixtures, no NPU emulation',
 'firmwareBlob':'Original uninstrumented e743d1b5; not the diagnostic producer ROM',
 'historicalRootProven':False,'goalComplete':False,'evidence':evidence}
(out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
g=read(w/'development/current-goal.json');g['status']='in-progress-after-explicit-owner-resume';g['latestAP24']='development/ap24/progress.json'
for unit in (1,2):
 accepted=out/f'deployment/ap{unit}-upgrade/result.json';returned=out/f'deployment/ap{unit}-upgrade/upgrade-returned.json'
 if accepted.exists():g['networkState'][f'AP{unit}']='AP24 已保留配置升级，普通重启和 Mesh/无线/管理连接验证通过；NPU 默认关闭。'
 elif returned.exists():g['networkState'][f'AP{unit}']='AP24 已启动，41 个保留文件、设备身份和驱动镜像校验通过；正在验证无线恢复与普通重启。'
if (out/'deployment/final-result.json').exists():
 g['objective']=g['objective'].replace('两台 AP 已恢复并部署 AP23','两台 AP 已恢复并部署 AP24')
if (out/'npu-ap1-epoch1/analysis.json').exists():
 result=read(out/'npu-ap1-epoch1/analysis.json')
 g['NpuFinding']['AP24OwnershipFix']={'codeImplemented':True,'realGuestKernelChecked':True,'builtJobs':12,'bothFlashed':True,
  'firstUninstrumentedHardwareTrial':'development/ap24/npu-ap1-epoch1/analysis.json',
  'activeMs':result['activeUntilRecoveryMs'],'highestSampledTxfreeMessages':max(s['messages'] for s in result['activeScalarSamples']),
  'faultObserved':result['faultObserved'],'captureGaps':0,'automaticRecoveryPassed':True,
  'historicalRootCauseProven':False,'fullLoadAndLongTermQualificationPassed':False}
(w/'development/current-goal.json').write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
notice='''<!-- ap24-current:start -->
## AP24 current work (2026-10-10)

- Owner explicitly says continue remote flashing; no repeated approval needed.
- AP24 20261010-ap24-d331711d SHA 411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0
 built -j12, actual-source guest-kernel ownership tests, module ABI, packed files,
 defaults and export gates passed. Original NPU blob, all experimental flags off.
- Changed mt76 generic fill/cleanup/reset/poll to leave NPU TXFREE entries to
 firmware. AP1 instrumented producer before-fix showed table/descriptor pointer
 mismatch and len20/header92. This is a candidate fix; historical root unproven.
- Exact latest build/deployment/trial state: development/ap24/progress.json.
 AP2 goes first; never rerun a scheduled one-shot upgrade or NPU epoch.
 New scripts: environment/ap24-deploy.py, verify-ap24-deployment.py,
 run-ap24-npu-ap1-epoch1.py. All use pinned LAN interface; AP2 is Mesh-only.
- Candidate uninstrumented NPU trial reuses qualified AP1 activation2/recovery4
 and read-only address observer, 180-second deadline, no generated traffic.
 No new boot-helper/native-code change in that harness. AP2/primary/switch/PC
 remain untouched during AP1 trial. No phone testing or blanket NPU acceptance.
- First AP1 AP24 trial completed: active178709ms, last sample1155 TXFREE messages,
 zero short headers/mismatches/truncations,377 continuous kernel records/no fault.
 180s guard deadline recovered to41d0771d; temporary tools removed, both healthy.
 AP2 boot1253f2a6 unchanged. This is positive bounded evidence, not full load/
 long-term acceptance or proof of the separate historical Maple Oops cause.
<!-- ap24-current:end -->
'''
p=r/'AGENTS.md';s=p.read_text();s=re.sub(r'<!-- ap24-current:start -->.*?<!-- ap24-current:end -->\n?', '',s,flags=re.S)
pos=s.index('<!-- owner-remote-npu-authorization');s=s[:pos]+notice+'\n'+s[pos:];p.write_text(s)
print(json.dumps({'version':report['version'],'evidenceItems':len(evidence),'goalComplete':False}))
