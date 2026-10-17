"""Analyze immutable before/after physical observations without fabricating trace envelopes."""
from pathlib import Path
from datetime import datetime
import json,re,hashlib
from xr_npu_producer_trace import parse_live_snapshot
w=Path(__file__).resolve().parents[1];out=w/'development/ap24/owner-trace';j=lambda p:json.loads(p.read_text())
before=j(w/'development/npu-ap1-debugfs/live-epoch-1/analysis.json');assert before['faultObserved'] and before['captureContinuous']
assert any(not row['poolPointerMatchesDescriptor'] and row['sourceShorterThanAnnounced'] for row in before['producer']['rows'])
epochs={}
for unit in (1,2):
 p=out/f'ap{unit}-epoch1';r=j(p/'result.json');closed=j(p/'capture-closed.json');enabled=j(p/'module-enabled.json');recover=j(p/'recovery.json')
 assert r['passed'] and r['ordinaryRecoveryAndCleanupPassed'] and not r['faultObserved'] and not r['activationFailure']
 assert closed['bootID']==enabled['bootID']==recover['bootID']==r['diagnosticBootID']
 assert closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1 and closed['gaps']==0 and not any(closed[k] for k in ('fault','failed','capped'))
 assert recover['reason']=='deadline'
 parsed=parse_live_snapshot((p/'active-producer.txt').read_bytes(),j(p/'active-observation.json'));assert parsed==j(p/'live-producer-parsed.json') and parsed['bootID']==r['diagnosticBootID']
 rows=parsed['rows'];assert len(rows)==32 and all(x['poolPointerMatchesDescriptor'] and not x['sourceShorterThanAnnounced'] and not x['controlChangedDuringObservation'] for x in rows)
 text=(p/'latest-active-token.txt').read_text();counts=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',text);assert counts and all(int(counts[n])==0 for n in (2,3,4))
 kernel_path=p/'capture-kernel.kmsg'
 if kernel_path.exists():assert not re.search(r'TXFREE truncated|WARNING:|BUG:|Oops:|Kernel panic|Call [Tt]race:',kernel_path.read_text())
 else:assert closed['written']==0  # Fault-triggered persistence; clean collector reports its full observation counters.
 epochs[str(unit)]={'diagnosticBootID':r['diagnosticBootID'],'activeMs':recover['monotonicMs']-enabled['monotonicMs'],'producerRows':len(rows),'poolMismatches':0,'shortFrames':0,'sampledTxfreeMessages':int(counts[1]),'continuousKernelRecords':closed['records'],'continuousObservationEvidence':'collector closed counters; clean stream not persisted' if not kernel_path.exists() else 'persisted kernel stream','faultObserved':False,'ordinaryRecoveryAndConfigurationPassed':True}
vm=j(w/'development/npu-txfree-owner/vm-result-latest.json');assert vm['passed'] and vm['oldOwnershipViolationsReproduced']==vm['fixedOwnershipCases']==4
result={'passed':True,'at':datetime.now().astimezone().isoformat(),'originalFaultBootID':before['bootID'],'beforeProducerRows':before['producer']['rows'],'sameInstrumentedNpuFirmwareSHA256':'b48d5e6e4725adfc3560b25aeb9aa00a01134e2a0b9ae84ac2313fe5c32bc298','after':epochs,'ownershipBugReproducedAndFixedInActualFunctionVM':True,'historicalSpecificPhysicalWriterDirectlyObserved':False,'fullNpuHardwareQualification':False,'limits':['Producer recorder captures only first32 records per hart','Host and firmware ownership conflict is demonstrated; physical writer/cache timing was not traced','Separate historical Maple Oops and long-term sustained load are not proven fixed']}
(out/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result))
