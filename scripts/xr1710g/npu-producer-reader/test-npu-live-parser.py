from pathlib import Path
import json
from xr_npu_producer_trace import parse_live_snapshot
w=Path(__file__).resolve().parents[1];raw=(w/'development/npu-ap2-debugfs/live-epoch-2/active-producer.txt').read_bytes()
obs={'bootBefore':'cd61bf16-36a9-452b-bb1c-c372cb8fde65','bootAfter':'cd61bf16-36a9-452b-bb1c-c372cb8fde65','monotonicMsBefore':100000,'monotonicMsAfter':100100,'readCode':0,'npuEnable':'Y'}
# This historical byte fixture tests parsing only; these synthetic timing fields
# are not emitted as a hardware observation or accepted as trial evidence.
r=parse_live_snapshot(raw,obs);assert len(r['rows'])==32 and all(x['poolPointerMatchesDescriptor'] for x in r['rows'])
cases=[]
def reject(label,data=raw,**change):
 try:parse_live_snapshot(data,{**obs,**change})
 except ValueError:cases.append(label)
 else:raise AssertionError(label)
reject('cross-boot',bootAfter='11111111-1111-1111-1111-111111111111')
reject('invalid UUID',bootBefore='wrong')
reject('missing read status',readCode=None)
reject('boolean read status',readCode=False)
reject('failed read',readCode=1)
reject('NPU inactive',npuEnable='N')
reject('clock reversal',monotonicMsBefore=100200)
reject('read timeout',monotonicMsAfter=107000)
reject('boolean time',monotonicMsBefore=True)
reject('partial final line',raw[:-1])
reject('missing hart',raw[:raw.index(b'hart=7 count=')])
reject('trailing row',raw+b'hart=7 count=0\n')
reject('wrong producer schema',raw.replace(b'schema=2',b'schema=3',1))
reject('bad commit',raw.replace(b'w11=00000001',b'w11=00000000',1))
reject('over-cap',b'x'*65537)
reject('nonascii',raw+b'\xff\n')
p=w/'development/ap24/owner-trace/live-parser-qa.json';p.write_text(json.dumps({'passed':True,'validHistoricalRawRows':32,'rejectedCases':cases,'hardwareEvidence':False},indent=2)+'\n')
print(json.dumps({'passed':True,'negativeCases':len(cases)}))
