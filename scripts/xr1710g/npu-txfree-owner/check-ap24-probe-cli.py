"""Validate actual failed/successful CLI observations, not synthetic ping replies."""
from pathlib import Path
import json,re,hashlib
w=Path(__file__).resolve().parents[1];p=w/'development/ap24/npu-ap1-load1';j=lambda n:json.loads((p/n).read_text())
bad=j('probe-parser-inspection.json');good=j('probe-integer-interval.json')
for unit in ('1','2'):
 assert bad[unit]['bootID']==good[unit]['bootID']
 assert bad[unit]['code']==1 and not bad[unit]['stdout'] and "invalid number '0.2'" in bad[unit]['stderr']
 assert good[unit]['code']==0 and not good[unit]['stderr']
 m=re.search(r'(\d+) packets transmitted, (\d+) packets received',good[unit]['stdout']);assert m and tuple(map(int,m.groups()))==(5,5)
script=w/'environment/run-ap24-bounded-load2.py';t=script.read_text();assert ' -i 0.2 ' not in t and ' -i 1 -c 5 ' in t and "row[label+'Raw']" in t
report={'passed':True,'actualDevices':2,'negativeCase':'BusyBox fractional interval command rejected before any packet was sent','positiveCase':'same-boot integer interval actual5/5 responses on each device','newHarnessSHA256':hashlib.sha256(script.read_bytes()).hexdigest(),'epoch1TrafficQualified':False}
(p/'probe-cli-qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
