"""Analyze an incomplete AP26 transit trial without overriding its rejection."""
from pathlib import Path
import json,re
from xr_npu_diagnostic_gates import complete_iperf,kernel_findings
w=Path('D:/ChatGPT/XR1710G');out=w/'development/ap26/npu-wired-mesh-ap1'
j=lambda name:json.loads((out/name).read_text())
report=j('result.json');assert report['operationCompletedAndRecovered'] and report['ordinaryRecoveryAndCleanupPassed']
assert not report['bothBoundedTransfersQualified'] and report['bothHealthy']
assert report['traffic']==[{'qualified':False,'error':'DiagnosticRejected','reason':'forwarding probe incomplete or lossy'}]
closed=j('capture-closed.json');enabled=j('module-enabled.json');recovery=j('recovery.json')
assert closed['bootID']==enabled['bootID']==recovery['bootID']
assert closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1 and closed['gaps']==0
assert all(closed[k] is False for k in ['failed','capped','fault']) and not report['kernelFaultObserved']
def counters(text):
 result={}
 for line in text.splitlines():
  if ':' not in line:continue
  name,fields=line.split(':',1);v=list(map(int,fields.split()));result[name.strip()]={'rx':v[0],'tx':v[8]}
 return result
def metadata(text):
 m=re.search(r'txfree_messages=(\d+) short_headers=(\d+) length_mismatches=(\d+) truncations=(\d+)',text)
 assert m and 'npu_active=1' in text
 row=dict(zip(['messages','shortHeaders','lengthMismatches','truncations'],map(int,m.groups())))
 assert not any(row[k] for k in ['shortHeaders','lengthMismatches','truncations'])
 return row
samples=[]
for name in ['activation-observed.json','active-samples.json']:
 if not (out/name).exists():continue
 rows=j(name);rows=rows if isinstance(rows,list) else [rows]
 for row in rows:
  assert row['bootID']==enabled['bootID'];samples.append({'file':name,**metadata(row['tokenMetadata'])})
transfers=[];lost_probes=[]
# One direction completed before the post-transfer probe rejected this epoch.
# Preserve the TCP observation separately from the failed operational verdict.
for index in [0]:
 before,after=j(f'before-{index}.json'),j(f'after-{index}.json')
 client=j(f'client-{index}.json');server=j(f'server-{index}.json')
 complete_iperf(client,20,False,4,'client');end=complete_iperf(server,20,False,4,'server')
 case={'reverse':False,'receiverBytes':end['sum_received']['bytes'],
       'receiverSeconds':end['sum_received']['seconds'],'receiverMbps':end['sum_received']['bits_per_second']/1e6}
 assert client['end']['sum_received']==dict(end['sum_received'],sender=True)
 assert all(x['local_host']=='192.168.10.101' and x['remote_host']=='192.168.10.4' for x in client['start']['connected'])
 byte_deltas={}
 for unit in ['1','2']:
  assert before[unit]['bootID']==after[unit]['bootID']
  assert before[unit]['parameters']['wlanNpu']==after[unit]['parameters']['wlanNpu']==('Y' if unit=='1' else 'N')
  assert before[unit]['parameters']['ppe']==after[unit]['parameters']['ppe']=='N'
  for side,document in [('before',before),('after',after)]:
   assert not kernel_findings(document[unit]['kernelLog'])
   for target in ['peerPing','gatewayPing']:
    ping=document[unit][target];assert ping['sent']==5
    if ping['received']!=ping['sent']:
     lost_probes.append({'snapshot':side,'unit':unit,'target':target,**ping})
  n0,n1=map(counters,(before[unit]['interfaceCounters'],after[unit]['interfaceCounters']))
  byte_deltas[unit]={p:{k:n1[p][k]-n0[p][k] for k in ['rx','tx']} for p in ['lan2','lan3','lan4','wan','mesh6g']}
 for side,document in [('before',before),('after',after)]:samples.append({'file':f'{side}-{index}.json',**metadata(document['1']['tokenMetadata'])})
 direction='tx' if case['reverse'] else 'rx';mesh_direction='rx' if case['reverse'] else 'tx'
 assert byte_deltas['1']['lan2'][direction] >= case['receiverBytes']*.95
 assert byte_deltas['1']['mesh6g'][mesh_direction] >= case['receiverBytes']*.95
 assert all(byte_deltas['2'][p][k]==0 for p in ['lan2','lan3','lan4','wan'] for k in ['rx','tx'])
 transfers.append({'qualified':False,'TCPPayloadCompleted':True,'direction':'ap2-to-pc' if case['reverse'] else 'pc-to-ap2','receiverMbps':case['receiverMbps'],'receiverBytes':case['receiverBytes'],
                   'seconds':case['receiverSeconds'],'AP1ForwardsWiredMeshVerified':True,'interfaceByteDeltas':byte_deltas})
assert lost_probes==[{'snapshot':'after','unit':'1','target':'peerPing','sent':5,'received':4}]
assert not (out/'client-1.json').exists()
result={'evidenceAnalysisPassed':True,'operationalQualificationPassed':False,'status':'recovered-cleaned-transit-rejected',
 'rejection':'AP1-to-AP2 post-transfer ICMP probe received4of5; reverse transfer was not started',
 'lossCauseEstablished':False,'lostProbes':lost_probes,
 'version':'20261010-ap26-d331711d','diagnosticBootID':enabled['bootID'],'normalRecoveredBootID':j('recovered.json')['bootID'],
 'transfers':transfers,'highestSampledTxfreeMessages':max(x['messages'] for x in samples),'allTxfreeSamplesClean':True,
 'samples':samples,'continuousKernelRecords':closed['records'],'kernelFaultObserved':False,
 'NpuEnableToRecoveryMs':recovery['monotonicMs']-enabled['monotonicMs'],'recoveryReason':recovery['reason'],
 'allTemporaryDeviceHelpersRemoved':True,'allConfigurationPreserved':True,'bothHealthy':True,
 'currentOrdinaryNpuPpeOff':True,'MapleRemainsProvisionallyAccepted':True,'fullPpeMeshHardwareOffload':False,
 'softwareBaseline':'development/ap25/ppe-transit/software-baseline1/result.json',
 'limits':['Only forward20s/P4 TCP finished; reverse was canceled after a lossy post-transfer probe',
           'Iperf payload totals are observations, not acceptance of the failed diagnostic epoch',
           'Baseline used30s/P4 and radio conditions may differ',
           'WLAN NPU attachment on AP1 with actual wired/Mesh transit; PPE remains off and AP2 terminates TCP',
           'Does not establish a throughput benefit, long-term stability, full hardware bridge offload, phone compatibility or IoT forwarding acceleration']}
(out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['evidenceAnalysisPassed','operationalQualificationPassed','highestSampledTxfreeMessages','continuousKernelRecords','normalRecoveredBootID']}))
print(json.dumps([{'direction':x['direction'],'receiverMbps':x['receiverMbps']} for x in transfers]))
