"""Analyze one-variable startup intervention against frozen corrected control."""
from pathlib import Path
from datetime import datetime
import json,re,hashlib,sys
from xr_npu_producer_trace import parse_snapshot,parse_live_snapshot
W=Path(__file__).resolve().parents[1];O=W/'development/ap24/prefill-probe'
j=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
units=[int(sys.argv[1])] if len(sys.argv)==2 else [1,2]
image=j(O/'result.json');build=j(O/'module-build.json');source=j(O/'source-order.json')
assert image['passed'] and build['passed'] and source['passed']
assert image['changedFiles']['lib/modules/6.18.54/mt76.ko']['sha256']==build['moduleSHA256']
assert source['diagnosticSourceSHA256']==build['sourceSHA256']==sha(O/'dma.c')
rows={}
for unit in units:
 p=O/f'ap{unit}-epoch1';r=j(p/'result.json');saved=r['saved'];b=r['diagnosticBootID']
 assert r['passed'] and r['ordinaryRecoveryAndCleanupPassed'] and r['activationObserved'] and not r['activationFailure']
 closed=saved['capture/closed.json'];recover=saved['recovery.json'];enabled=saved['module-enabled.json']
 assert closed['bootID']==recover['bootID']==enabled['bootID']==b
 assert closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1 and closed['gaps']==0 and not closed['failed'] and not closed['capped']
 fault=p/'fault-npu-producer.txt';live=p/'active-producer.txt'
 if fault.exists():data=fault.read_bytes();parsed=parse_snapshot(data,b)
 else:data=live.read_bytes();parsed=parse_live_snapshot(data,j(p/'active-observation.json'));assert parsed['bootID']==b
 kernel='\n'.join(q.read_text() for q in (p/'capture-kernel.kmsg',p/'capture-first-fault.kmsg',p/'active-kernel.txt') if q.exists())
 starts=set(re.findall(r'XR_PREFILL_PROBE after q=(\d+) queued=(\d+) head=(\d+) buf0=([0-9a-f]{8}) ctrl=([0-9a-f]{8})',kernel))
 assert len(starts)==1,starts
 qid,queued,head,buf0,ctrl=next(iter(starts));assert int(queued)==511 and int(head)==511
 first=re.search(r'hart=\d+ record=0 w0=([0-9a-f]{8}) .*? w5=([0-9a-f]{8}) w6=([0-9a-f]{8}) ',data.decode());assert first
 descriptors=[{'index':int(m[1],16),'control':m[2],'poolBuffer':m[3],'descriptorBuffer':m[4]}
              for m in re.finditer(r'hart=\d+ record=\d+ w0=([0-9a-f]{8}) w1=([0-9a-f]{8}) .*? w5=([0-9a-f]{8}) w6=([0-9a-f]{8}) ',data.decode())]
 assert len(descriptors)==len(parsed['rows'])
 mismatches=[x for x in parsed['rows'] if not x['poolPointerMatchesDescriptor']]
 truncated=any(x['sourceShorterThanAnnounced'] for x in parsed['rows'])
 faulttext=(p/'capture-first-fault.kmsg').read_text() if (p/'capture-first-fault.kmsg').exists() else ''
 faults=[line for line in faulttext.splitlines() if re.search(r'TXFREE truncated|WARNING:|BUG:|Oops:|Kernel panic|Call [Tt]race:',line)]
 control=j(W/'development/ap24/owner-trace/analysis.json')['after'][str(unit)]
 assert not control['faultObserved'] and control['poolMismatches']==0 and control['shortFrames']==0
 exact_first_buffer_match=first[3]==buf0 if int(first[1],16)==0 else None
 low_control_match=(int(descriptors[0]['control'],16)&0xffff)==(int(ctrl,16)&0xffff)
 causal=bool(mismatches and truncated and r['faultObserved'] and 'TXFREE truncated' in faulttext and low_control_match)
 row={'unit':unit,'bootID':b,'activeMs':recover['monotonicMs']-enabled['monotonicMs'],'faultObserved':r['faultObserved'],
  'startupPrefill':{'queue':int(qid),'queued':int(queued),'head':int(head),'firstHostBuffer':buf0,'control':ctrl},
  'firstRecordedRingIndex':int(first[1],16),'firstProducerPoolBuffer':first[2],'firstProducerDescriptorBuffer':first[3],
  'producerDescriptorMatchesStartupHostBuffer':exact_first_buffer_match,'producerRows':len(parsed['rows']),
  'descriptorMetadata':descriptors,
  'firstDescriptorLowControlMatchesStartup':low_control_match,
  'poolMismatches':len(mismatches),'shortFrames':sum(x['sourceShorterThanAnnounced'] for x in parsed['rows']),
  'mismatchRingIndices':[x['ringIndex'] for x in mismatches],
  'startupPrefillOwnershipMismatchDemonstrated':bool(mismatches and low_control_match),
  'continuousKernelRecords':closed['records'],'kernelFaults':faults,'recoveryReason':recover['reason'],
  'ordinaryRecoveryAndConfigurationPassed':True,'singleStartupInterventionReproducedHistoricalFault':causal,
  'controlBootID':control['diagnosticBootID'],'controlRows':control['producerRows'],'controlActiveMs':control['activeMs'],
  'producer':parsed,'historicalMapleOopsExplained':False,'physicalPrefetchWritebackDirectlyObserved':False}
 (p/'analysis.json').write_text(json.dumps(row,indent=2)+'\n');rows[str(unit)]=row
report={'at':datetime.now().astimezone().isoformat(),'experimentQualified':True,'artifactSHA256':image['artifactSHA256'],
 'moduleSHA256':build['moduleSHA256'],'sourceSHA256':build['sourceSHA256'],'units':rows,
 'startupPrefillCausalityDemonstrated':any(x['singleStartupInterventionReproducedHistoricalFault'] for x in rows.values()),
 'startupPrefillOwnershipMismatchDemonstrated':any(x['startupPrefillOwnershipMismatchDemonstrated'] for x in rows.values()),
 'limits':['Runtime ownership guards retained throughout; sole semantic intervention is startup prefill, plus two informational metadata log lines',
 'AP1 first recorded ring index is not assumed zero; startup logs record buffer0 only, so no direct equality claim for a different ring index',
 'Clean comparison uses prior qualified same-device same-producer AP24 epochs, not simultaneous randomized controls',
 'PCIe prefetch/writeback/cache internals are not directly observed; hardware timing and allocator layout may influence reproducibility',
 'Separate Maple Oops and full sustained NPU hardware acceptance remain outside this diagnosis']}
(O/('analysis.json' if len(units)==2 else f'analysis-ap{units[0]}.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'qualified':True,'startupPrefillCausalityDemonstrated':report['startupPrefillCausalityDemonstrated'],
 'units':{u:{k:r[k] for k in ('bootID','faultObserved','producerRows','poolMismatches','shortFrames','producerDescriptorMatchesStartupHostBuffer')} for u,r in rows.items()}}))
