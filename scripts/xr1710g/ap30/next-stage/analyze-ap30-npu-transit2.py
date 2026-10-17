"""Describe completed raw observations; retain the finalizer's rejected verdict."""
from pathlib import Path
from datetime import datetime
import json,re,hashlib
w=Path(__file__).resolve().parents[1];out=w/'development/ap30/forwarding/npu-transit2'
load=lambda p:json.loads(p.read_text())
result=load(out/'result.json');operation=load(out/'operation.json')
assert operation['status']=='completed-recovered-cleaned'
assert not result['boundedBidirectionalTransfersQualified'] and not result['captureContinuousAndComplete']
assert result['ordinaryRecoveryAndCleanupPassed'] and result['bothHealthy'] and not result['kernelFaultObserved']
closed=load(out/'capture-closed.json');ready=load(out/'before-0.json')['1']['recoveryGuard'];recovery=load(out/'recovery.json')
assert closed['bootID']==ready['bootID']==recovery['bootID']
assert recovery['reason']=='deadline' and recovery['deadlineMs']==ready['deadlineMs']
assert closed['pid']==ready['collectorPID'] and closed['monotonicMs']<ready['deadlineMs']
latencies=[];txfree=[]
for i,case in enumerate(result['traffic']):
 assert not case['qualified'] and case['probeEvidence']['passed']
 for unit in [1,2]:
  s=(out/f'direction-{i}/ap{unit}-peer-ping.txt').read_text()
  m=re.search(r'min/avg/max = ([\d.]+)/([\d.]+)/([\d.]+) ms',s);assert m
  latencies.append({'direction':i,'AP':unit,'minMs':float(m[1]),'avgMs':float(m[2]),'maxMs':float(m[3])})
 for phase in ['before','after']:
  snap=load(out/f'{phase}-{i}.json')
  for unit in ['1','2']:
   for m in re.finditer(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',snap[unit]['tokenMetadata']):
    assert all(int(m[j])==0 for j in [2,3,4])
    if unit=='1':txfree.append(int(m[1]))
for row in load(out/'active-samples.json'):
 m=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',row['tokenMetadata']);assert m
 assert all(int(m[j])==0 for j in [2,3,4]);txfree.append(int(m[1]))
 assert row['mapleObserver']=='schema=1 captured=0'
baseline=load(w/'development/ap30/forwarding/loaded-transit1/analysis.json')
report={'at':datetime.now().astimezone().isoformat(),'passedBoundedForwardingAndRecovery':False,
 'originalFinalVerdictPreserved':True,'rawTrafficObservationsAvailable':True,
 'failureReason':'Finalizer required ready.json after recovery intentionally removed it. Fresh epoch must save live guard identity. See development/ap30/npu-closure/qa.json.',
 'version':result['version'],'AP1NpuOnly':True,'PPEEnabled':False,'diagnosticBoot':ready['bootID'],
 'fixedDeadlineSeconds':480,'continuousKernelRecords':closed['records'],'kernelSequenceGaps':closed['gaps'],
 'collectorClosedBeforeHardDeadlineMs':ready['deadlineMs']-closed['monotonicMs'],
 'maxObservedAP1TxfreeMessages':max(txfree),'observedTxfreeErrors':0,'kernelFaultObserved':False,
 'transfersMbps':[x['receiverMbps'] for x in result['traffic']],
 'previousSoftwareMbps':[x['receiverMbps'] for x in baseline['transfers']],
 'loadedEchoExchanges':144,'loadedEchoLosses':0,'headersPerStagePerDirection':144,'latencies':latencies,
 'ordinaryRecoveryVerified':True,'bothAPsHealthy':True,'allTemporaryToolsRemoved':True,
 'performanceSpeedupProven':False,'longTermStabilityProven':False,'bothEndpointsNpuQualified':False,
 'historicalRejectedEpochsRequalified':False,'historicalCrashRootCauseProven':False,
 'limits':['AP2 is the TCP endpoint, AP1 is the forwarding device; only AP1 NPU enabled.',
 'Two20s/P4 transfers completed, but final epoch acceptance remains rejected; no long-term stability claim.',
 'Historical software baseline is not a randomized RF/CPU-controlled A/B; both NPU rates are lower, so default NPU stays off.',
 'No PPE forwarding, Mesh firmware header-offload or VLAN50 hardware acceleration qualification.',
 'No phone or main-router/switch/PC network changes.']}
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
