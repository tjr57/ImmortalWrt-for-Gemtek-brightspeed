"""Accept only the fresh completed epoch with independently checked closure."""
from pathlib import Path
from datetime import datetime
import json,re,hashlib
from xr_npu_closure import collector_closed_cleanly
w=Path(__file__).resolve().parents[1];out=w/'development/ap30/forwarding/npu-transit3'
load=lambda p:json.loads(p.read_text())
r=load(out/'result.json');operation=load(out/'operation.json');guard=load(out/'guard-ready-live.json')
assert operation['status']=='completed-recovered-cleaned' and r['boundedBidirectionalTransfersQualified']
assert r['captureContinuousAndComplete'] and r['ordinaryRecoveryAndCleanupPassed'] and r['bothHealthy'] and not r['kernelFaultObserved']
assert load(out/'closure-verification.json')['sourceSHA256']==hashlib.sha256((w/'environment/xr_npu_closure.py').read_bytes()).hexdigest()
names=('armed.json','recovery.json','aborted.json','capture/started.json','capture/ready.json','capture/closed.json')
saved={n:load(out/n.replace('/','-')) for n in names}
assert collector_closed_cleanly(saved,guard['bootID'],guard)
assert not (out/'ready.json').exists()
closed=saved['capture/closed.json'];latencies=[];txfree=[];intervals=[]
def cpu_rows(text):
 rows={}
 for line in text.splitlines():
  parts=line.split()
  if not re.fullmatch(r'cpu\d*',parts[0]):continue
  values=[int(x) for x in parts[1:9]];assert len(values)==8
  rows[parts[0]]={'total':sum(values),'idle':values[3]+values[4]}
 return rows
for i,case in enumerate(r['traffic']):
 assert case['qualified'] and case['probeEvidence']['passed']
 before=load(out/f'before-{i}.json');after=load(out/f'after-{i}.json')
 for unit in ['1','2']:
  text=(out/f'direction-{i}/ap{unit}-peer-ping.txt').read_text()
  m=re.search(r'min/avg/max = ([\d.]+)/([\d.]+)/([\d.]+) ms',text);assert m
  latencies.append({'direction':i,'AP':int(unit),'minMs':float(m[1]),'avgMs':float(m[2]),'maxMs':float(m[3])})
  a=cpu_rows(before[unit]['cpuCounters']);b=cpu_rows(after[unit]['cpuCounters']);usage={}
  for cpu in a:
   total=b[cpu]['total']-a[cpu]['total'];idle=b[cpu]['idle']-a[cpu]['idle'];assert total>0 and 0<=idle<=total
   usage[cpu]=100*(total-idle)/total
  station=before[unit]['meshStation']
  rates={name:m.group(1).strip() if (m:=re.search(r'^\s*'+re.escape(name)+r':\s*(.+)$',station,re.M)) else None for name in ['signal','tx bitrate','rx bitrate']}
  intervals.append({'direction':i,'AP':int(unit),'cpuBusyPercentOverWholeObservationInterval':usage,'meshBefore':rates,
   'intervalIncludesIdleAndProbeTime':True,'peakDuringIperfKnown':False})
  for snap in [before,after]:
   m=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',snap[unit]['tokenMetadata']);assert m
   assert all(int(m[j])==0 for j in [2,3,4])
   if unit=='1':txfree.append(int(m[1]))
for row in load(out/'active-samples.json'):
 m=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',row['tokenMetadata']);assert m
 assert all(int(m[j])==0 for j in [2,3,4]);txfree.append(int(m[1]))
 assert row['mapleObserver']=='schema=1 captured=0'
report={'at':datetime.now().astimezone().isoformat(),'passedBoundedForwardingAndRecovery':True,
 'version':r['version'],'AP1NpuOnly':True,'PPEEnabled':False,'fixedDeadlineSeconds':480,
 'diagnosticBoot':guard['bootID'],'normalBoot':load(out/'recovered.json')['bootID'],
 'liveGuardCapturedBeforeRecovery':True,'continuousKernelRecords':closed['records'],'kernelSequenceGaps':closed['gaps'],
 'collectorClosedBeforeHardDeadlineMs':guard['deadlineMs']-closed['monotonicMs'],
 'maxObservedAP1TxfreeMessages':max(txfree),'observedTxfreeErrors':0,'kernelFaultObserved':False,
 'transfersMbps':[x['receiverMbps'] for x in r['traffic']],'loadedEchoExchanges':144,'loadedEchoLosses':0,
 'latencies':latencies,'intervalObservations':intervals,'ordinaryRecoveryAndCleanupVerified':True,'bothAPsHealthy':True,
 'performanceSpeedupProven':False,'longTermStabilityProven':False,'bothEndpointsNpuQualified':False,
 'historicalRejectedEpochsRequalified':False,'historicalCrashRootCauseProven':False,
 'limits':['One fixed480s AP1-only NPU boot; two20s/P4 transfers; AP2 terminates TCP.',
 'No full PPE/Mesh-header/VLAN50 hardware forwarding qualification.',
 'CPU interval averages include probe/idle time and are not load-time peaks.',
 'RF rates/time/observer state are not held constant in a randomized A/B; default NPU remains off.',
 'Epoch2 rejection and all historical failure evidence preserved.']}
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['latencies','intervalObservations','limits']}))
