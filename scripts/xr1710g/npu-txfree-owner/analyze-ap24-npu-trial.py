from pathlib import Path
from datetime import datetime
import json,re,hashlib
w=Path(__file__).resolve().parents[1];out=w/'development/ap24/npu-ap1-epoch1'
def j(p):return json.loads(p.read_text())
r=j(out/'result.json');assert r['operationCompletedAndRecovered'] and r['ordinaryRecoveryAndCleanupPassed']
closed=j(out/'capture-closed.json');enabled=j(out/'module-enabled.json');recover=j(out/'recovery.json')
assert closed['bootID']==enabled['bootID']==recover['bootID']
continuous=closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1 and closed['gaps']==0 and not closed['failed'] and not closed['capped']
sources=[]
for file in ('activation-observed.json','active-samples.json'):
 if (out/file).exists():
  v=j(out/file);sources.extend(v if isinstance(v,list) else [v])
scalars=[]
for entry in sources:
 text=entry['tokenMetadata'];assert entry['bootID']==enabled['bootID'] and 'npu_active=1' in text
 counts=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',text);assert counts
 scalars.append({'uptime':entry.get('uptime'),'messages':int(counts[1]),'shortHeaders':int(counts[2]),'lengthMismatches':int(counts[3]),'truncations':int(counts[4])})
fault_lines=[]
if (out/'capture-kernel.kmsg').exists():fault_lines=[s for s in (out/'capture-kernel.kmsg').read_text().splitlines() if any(x in s for x in ('TXFREE truncated','WARNING:','Oops:','Kernel panic'))]
report={'at':datetime.now().astimezone().isoformat(),'version':r['version'],'diagnosticBootID':enabled['bootID'],
 'originalNpuFirmwareUnchanged':True,'ownershipCandidateInstalled':True,'captureContinuous':continuous,
 'records':closed['records'],'activeUntilRecoveryMs':recover['monotonicMs']-enabled['monotonicMs'],
 'faultObserved':r['kernelFaultObserved'],'recoveryReason':recover['reason'],'ordinaryRecoveryPassed':True,
 'activeScalarSamples':scalars,'faultLines':fault_lines,
 'beforeUninstrumentedFaultEvidence':'development/npu-guarded-boot/live-epoch-3/result.json',
 'beforeInstrumentedPointerMismatchEvidence':'development/npu-ap1-debugfs/live-epoch-1/analysis.json',
 'historicalRootCauseProven':False,'fullNpuHardwareQualificationPassed':False,
 'limits':['One bounded boot, no generated traffic or throughput qualification','Same firmware blob with host-driver candidate; no producer hook in this trial','A clean short run does not establish long-term stability or the separate historical Maple Oops cause']}
assert continuous
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
