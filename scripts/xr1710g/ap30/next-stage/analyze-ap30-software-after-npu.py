from pathlib import Path
from collections import Counter
import json,re
from xr_two_ap import WORKSPACE
from ap27_forwarding_observer import header_rows
out=WORKSPACE/'development/ap30/forwarding/software-after-npu2';result=json.loads((out/'result.json').read_text());assert result['passed']
checks=[]
for label in ['pc-to-ap2','ap2-to-pc']:
 d=out/label;pings={}
 for unit in [1,2]:
  data=(d/f'ap{unit}-peer-ping.txt').read_text();m=re.search(r'(\d+) packets transmitted, (\d+) packets received',data);assert m
  pings[str(unit)]={'sent':int(m[1]),'received':int(m[2])};assert pings[str(unit)]=={'sent':36,'received':36}
 stages={p.stem:header_rows(p.read_text()) for p in d.glob('*-headers.txt')};assert len(stages)==4
 counts={name:Counter((x['source'],x['destination'],x['type'],x['id'],x['seq']) for x in rows) for name,rows in stages.items()}
 first=next(iter(counts.values()));assert len(first)==144 and all(n==1 for n in first.values())
 assert all(rows==first for rows in counts.values())
 assert all('0 packets dropped by kernel' in p.read_text() for p in d.glob('*-headers.stderr'))
 checks.append({'direction':label,'pings':pings,'eachStageICMPHeaders':144,'allFourStagesMatch':True,'captureKernelDrops':0})
report={'passed':True,'checks':checks,'transfers':result['transfers'],'NpuPpeEnabled':False,'defaultOffObserversUsed':False,'path':result['path'],'configurationPreserved':True,'limits':'Two bounded20-second/P4 transfers and144 total echo exchanges; not long-term or hardware-offload acceptance.'}
(out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
