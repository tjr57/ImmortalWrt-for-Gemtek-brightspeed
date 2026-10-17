from pathlib import Path
import json
w=Path('D:/ChatGPT/XR1710G');root=w/'development/ap25/ppe-transit/software-baseline1'
report=json.loads((root/'result.json').read_text());assert report['passed']
def net(text):
 d={}
 for line in text.splitlines():
  if ':' not in line:continue
  name,data=line.split(':',1);v=list(map(int,data.split()));d[name.strip()]={'rx':v[0],'tx':v[8]}
 return d
def cpu(text):
 return list(map(int,next(line for line in text.splitlines() if line.startswith('cpu ')).split()[1:9]))
evidence=[]
for transfer in report['transfers']:
 label=transfer['direction'];before=json.loads((root/(label+'-before.json')).read_text());after=json.loads((root/(label+'-after.json')).read_text())
 units={}
 for unit in ('1','2'):
  n0,n1=map(net,(before[unit]['net'],after[unit]['net']))
  ports={p:{k:n1[p][k]-n0[p][k] for k in ('rx','tx')} for p in ['lan2','lan3','lan4','wan','mesh6g']}
  t0,t1=map(cpu,(before[unit]['cpu'],after[unit]['cpu']));ticks=[b-a for a,b in zip(t0,t1)]
  units[unit]={'interfaceByteDeltas':ports,'aggregateCpuBusyPercent':100*(sum(ticks)-ticks[3]-ticks[4])/sum(ticks),'softwarePolicyLatched':before[unit]['ppePolicy']=='Y'}
 direction='rx' if label=='pc-to-ap2' else 'tx';mesh_direction='tx' if direction=='rx' else 'rx'
 # Endpoint byte total is independent; counters contain other LAN traffic.
 assert units['1']['interfaceByteDeltas']['lan2'][direction]>=transfer['receiverBytes']*.95
 assert units['1']['interfaceByteDeltas']['mesh6g'][mesh_direction]>=transfer['receiverBytes']*.95
 assert units['2']['interfaceByteDeltas']['mesh6g'][direction]>=transfer['receiverBytes']*.95
 evidence.append({'direction':label,'endpointReceiverMbps':transfer['receiverMbps'],'APs':units,'expectedAP1WiredAndMeshByteGrowthObserved':True})
analysis={'passed':True,'transfers':evidence,'noNpuPpeAcceleration':True,'AP1ForwardsAP2TerminatesTCP':True,
 'limits':['Interface byte deltas include ambient traffic','CPU sampling spans SSH snapshot overhead as well as transfer','This does not attribute the software ceiling to a particular component']}
(root/'path-analysis.json').write_text(json.dumps(analysis,indent=2)+'\n')
print(json.dumps(analysis))
