from pathlib import Path
import json,re,sys
attempt=sys.argv[1] if len(sys.argv)>1 else '2';assert attempt in ('1','2')
w=Path(__file__).resolve().parents[1];out=w/('development/ap24/npu-ap1-load'+attempt);j=lambda p:json.loads(p.read_text())
r=j(out/'result.json');assert r['operationCompletedAndRecovered'] and r['ordinaryRecoveryAndCleanupPassed']
closed=j(out/'capture-closed.json');enabled=j(out/'module-enabled.json');recover=j(out/'recovery.json')
assert closed['bootID']==enabled['bootID']==recover['bootID'] and r['captureContinuousAndComplete']
samples=[]
for name in ('activation-observed.json','active-samples.json'):
 if (out/name).exists():
  rows=j(out/name)
  for x in rows if isinstance(rows,list) else [rows]:
   assert x['bootID']==enabled['bootID'] and 'npu_active=1' in x['tokenMetadata']
   m=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',x['tokenMetadata']);assert m
   samples.append({'uptime':x.get('uptime'),'messages':int(m[1]),'shortHeaders':int(m[2]),'lengthMismatches':int(m[3]),'truncations':int(m[4])})
counts_clean=bool(samples) and all(not any(x[k] for k in ('shortHeaders','lengthMismatches','truncations')) for x in samples)
report={'passed':r['bothBoundedTransfersQualified'] and not r['kernelFaultObserved'] and counts_clean,'bootID':enabled['bootID'],'originalNpuFirmware':True,'activeMs':recover['monotonicMs']-enabled['monotonicMs'],'recoveryReason':recover['reason'],'continuousObservedKernelRecords':closed['records'],'faultObserved':r['kernelFaultObserved'],'transferResults':r['traffic'],'scalarSamples':samples,'ordinaryRecoveryAndCleanupPassed':True,'limits':['TCP pacing100Mbps per stream,2streams,8seconds each direction; not maximum throughput','AP-local endpoints exercise Mesh wireless path, not main-router wired routing/PPE offload','No phone or long-term fault acceptance']}
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
