"""Compare raw bounded measurements without claiming a controlled RF A/B."""
from pathlib import Path
from datetime import datetime
import json,re
w=Path(__file__).resolve().parents[1];base=w/'development/ap30/forwarding'
rows=[]
for mode,folder in [('software-before','loaded-transit1'),('npu-epoch2','npu-transit2'),('software-after','software-after-npu2'),('npu-epoch3','npu-transit3')]:
 d=base/folder
 if not (d/'result.json').exists():continue
 r=json.loads((d/'result.json').read_text());npu=mode.startswith('npu')
 for i,reverse in enumerate((False,True)):
  label='ap2-to-pc' if reverse else 'pc-to-ap2'
  client=d/(f'client-{i}.json' if npu else label+'-client.json')
  server=d/(f'server-{i}.json' if npu else label+'-server.json')
  if not client.exists() or not server.exists():continue
  cli=json.loads(client.read_text());srv=json.loads(server.read_text())
  receive=(cli if reverse else srv)['end']['sum_received']
  transmit=(srv if reverse else cli)['end']['sum_sent']
  row={'mode':mode,'direction':label,'receiverMbps':receive['bits_per_second']/1e6,
   'seconds':receive['seconds'],'senderRetransmits':transmit.get('retransmits'),
   'AP2EndpointCpuPercent':srv['end'].get('cpu_utilization_percent'),
   'epochAccepted':r.get('boundedBidirectionalTransfersQualified') if npu else r.get('passed'),
   'source':str(d.relative_to(w)),'AP1ForwarderPeakCpuKnown':False}
  if npu:
   snap_file=d/f'before-{i}.json'
   if snap_file.exists():
    snap=json.loads(snap_file.read_text())
    row['meshBefore']={u:{k:m.group(1).strip() if (m:=re.search(r'^\s*'+re.escape(k)+r':\s*(.+)$',snap[u].get('meshStation',''),re.M)) else None for k in ['signal','tx bitrate','rx bitrate']} for u in ['1','2']}
  rows.append(row)
report={'at':datetime.now().astimezone().isoformat(),'rawMeasurements':rows,
 'comparisonProvesSpeedup':False,'productionNpuEnableRecommendedFromTheseTests':False,
 'limits':['Same PC/AP addresses,20s TCP/P4 and direction; epochs occurred at different times and in different AP1 boots.',
 'No randomized/repeated RF-controlled A/B. Passive observers and early recovery collector were loaded only during NPU epochs.',
 'iperf CPU reports belong to AP2 endpoint/PC, not AP1 forwarder peak utilization.',
 'NPU epoch2 original finalizer rejection remains in force despite available raw transfer observations.',
 'PPE remains off; these observations do not qualify VLAN50, full Mesh header offload or long-term stability.']}
(base/'npu-software-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'rows':[{k:x[k] for k in ['mode','direction','receiverMbps','senderRetransmits','epochAccepted']} for x in rows],'speedupProven':False}))
