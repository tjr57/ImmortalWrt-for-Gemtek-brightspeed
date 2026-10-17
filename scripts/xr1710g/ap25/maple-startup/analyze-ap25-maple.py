"""Read-only analysis: fault evidence and bounded load are separate from root proof."""
from pathlib import Path
import json,re,sys
w=Path(__file__).resolve().parents[1];unit=int(sys.argv[1]);assert unit in (1,2)
out=w/'development/ap25'/('maple-ap2-epoch1' if unit==2 else 'maple-ap1-load1')
j=lambda name:json.loads((out/name).read_text())
r=j('result.json');assert r['operationCompletedAndRecovered'] and r['ordinaryRecoveryAndCleanupPassed']
closed=j('capture-closed.json');enabled=j('module-enabled.json');recover=j('recovery.json')
assert closed['bootID']==enabled['bootID']==recover['bootID']
continuous=closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1 and closed['gaps']==0 and not closed['failed'] and not closed['capped']
kernel=(out/'activation-kernel.txt').read_text()
matches=re.findall(r'\[\s*([0-9]+\.[0-9]+)\] XR_MAPLE_OBSERVER ready exact_site=d4 passive=1',kernel)
assert len(matches)==1
observer_ms=int(float(matches[0])*1000);assert observer_ms<=enabled['monotonicMs']
samples=[]
for name in ['activation-observed.json','active-samples.json','before-0.json','after-0.json','before-1.json','after-1.json']:
 if not (out/name).exists():continue
 data=j(name)
 if name.startswith(('before-','after-')):rows=[data['1']]
 else:rows=data if isinstance(data,list) else [data]
 for d in rows:
  assert d['bootID']==enabled['bootID'] and 'npu_active=1' in d['tokenMetadata']
  m=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',d['tokenMetadata']);assert m
  samples.append({'file':name,'uptime':d.get('uptime'),'messages':int(m[1]),'shortHeaders':int(m[2]),'lengthMismatches':int(m[3]),'truncations':int(m[4]),'maple':d.get('mapleObserver')})
clean=bool(samples) and all(not any(d[k] for k in ['shortHeaders','lengthMismatches','truncations']) for d in samples)
passed=continuous and clean and not r['kernelFaultObserved'] and not closed['fault']
if unit==1:passed=passed and r['bothBoundedTransfersQualified']
report={'passed':passed,'unit':unit,'diagnosticBootID':enabled['bootID'],'observerReadyMs':observer_ms,'npuBootParameterVerifiedMs':enabled['monotonicMs'],'activeMs':recover['monotonicMs']-enabled['monotonicMs'],'activeMsMeaning':'Boot parameter verified until recovery; driver attachment completes later and is independently observed via npu_active=1','recoveryReason':recover['reason'],'kernelFaultObserved':r['kernelFaultObserved'] or closed['fault'],'mapleFaultSnapshotObserved':r['newMapleSnapshotObserved'],'continuousKernelObservation':continuous,'observedKernelRecords':closed['records'],'highestSampledTxfreeMessages':max(d['messages'] for d in samples),'txfreeSamplesClean':clean,'samples':samples,'transfers':r['traffic'],'originalNpuFirmware':True,'ordinaryRecoveryAndCleanupPassed':True,'MapleRootCauseProven':False,'fullNpuHardwareQualification':False,'limits':['Observer records metadata only at the exact historical Maple fault site; absence does not prove historical cause fixed','Built-in NPU firmware boots before the S08 observer; observer is ready before WLAN NPU attachment, not before initial firmware boot','AP-to-AP CPU endpoints exercise Mesh/NPU, not wired forwarding/PPE or phone behavior','Single bounded boot per role; no long-term or all-client qualification']}
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
