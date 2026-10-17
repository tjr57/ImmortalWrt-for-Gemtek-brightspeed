"""A new epoch fixes an observed BusyBox ping CLI incompatibility; never resumes load1."""
from pathlib import Path
import hashlib,json
w=Path(__file__).resolve().parents[1];p=w/'environment/run-ap24-bounded-load.py';t=p.read_text()
assert "out=WORKSPACE/'development/ap24/npu-ap1-load1'" in t
t=t.replace("out=WORKSPACE/'development/ap24/npu-ap1-load1'", "out=WORKSPACE/'development/ap24/npu-ap1-load2'")
old="data,_,code=command(c,'ping -I br-lan.1 -i 0.2 -c 5 -W 1 '+ip,timeout=10,check=False)"
new="data,error,code=command(c,'ping -I br-lan.1 -i 1 -c 5 -W 1 '+ip,timeout=12,check=False)"
assert t.count(old)==1;t=t.replace(old,new)
old="row[label]={'sent':int(match[1]),'received':int(match[2])} if match else {'sent':0,'received':0}"
new="row[label]={'sent':int(match[1]),'received':int(match[2])} if match and code==0 else {'sent':0,'received':0}\n    row[label+'Raw']={'stdout':data.decode(),'stderr':error.decode(),'code':code}"
assert t.count(old)==1;t=t.replace(old,new)
anchor="assert len(sys.argv)==2 and sys.argv[1]=='run' and not operation.exists(),'Inspect one-shot journal; do not restart this epoch'"
assert t.count(anchor)==1;t=t.replace(anchor,anchor+"\nassert json.loads((WORKSPACE/'development/ap24/npu-ap1-load1/result.json').read_text())['ordinaryRecoveryAndCleanupPassed']")
target=w/'environment/run-ap24-bounded-load2.py';assert not target.exists();target.write_text(t)
print(json.dumps({'preparedNewEpochOnly':True,'previousHarnessSHA256':hashlib.sha256(p.read_bytes()).hexdigest(),'newHarnessSHA256':hashlib.sha256(target.read_bytes()).hexdigest(),'fix':'integer interval1 supported by shipped BusyBox ping; retain raw stdout/stderr/exit evidence'}))
