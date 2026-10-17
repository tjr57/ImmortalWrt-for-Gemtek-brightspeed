"""Reproduce the report bug from archived metadata; do not change that verdict."""
from pathlib import Path
from copy import deepcopy
import json,hashlib
from xr_npu_closure import collector_closed_cleanly
w=Path(__file__).resolve().parents[1];epoch=w/'development/ap30/forwarding/npu-transit2'
out=w/'development/ap30/npu-closure';out.mkdir(exist_ok=True)
names=('armed.json','recovery.json','aborted.json','capture/started.json','capture/ready.json','capture/closed.json')
saved={n:json.loads((epoch/n.replace('/','-')).read_text()) for n in names}
before=json.loads((epoch/'before-0.json').read_text())['1']['recoveryGuard']
assert before['collectorAlive'] and before['supervisorAlive'] and before['deadlineAlive']
assert not (epoch/'ready.json').exists()
# Reconstruct this test fixture from the guard identity confirmed at runtime
# plus immutable recovery metadata. Future runners must save ready.json while
# it exists; this fixture does not replace that requirement or reaccept epoch2.
live={k:saved['recovery.json'][k] for k in ('bootID','pid','deadlinePID','collectorPID','deadlineMs')}
live['monotonicMs']=before['captureReady']['monotonicMs']+100
assert live['collectorPID']==before['collectorPID'] and live['deadlineMs']==before['deadlineMs']
boot=live['bootID'];checks=[]
def check(name,records=saved,guard=live,expected=False):
 assert collector_closed_cleanly(records,boot,guard)==expected,name;checks.append(name)
check('collector closure positive; missing retired ready file allowed',expected=True)
for n in names:
 d=deepcopy(saved);d.pop(n);check('missing '+n,d)
 d=deepcopy(saved);d[n]['bootID']='wrong';check('wrong boot '+n,d)
for name,field,value in [('capture/closed.json','pid',99),('capture/closed.json','pid',True),
 ('capture/ready.json','records',1),('capture/closed.json','records',0),('capture/closed.json','lastSeq',0),
 ('capture/closed.json','firstSeq',1),('capture/closed.json','gaps',1),('capture/closed.json','gaps',False),
 ('capture/closed.json','fault',True),('capture/closed.json','failed',True),('capture/closed.json','capped',True),
 ('capture/closed.json','monotonicMs',live['deadlineMs']),('recovery.json','reason','operator-abort'),
 ('recovery.json','pid',98),('recovery.json','deadlinePID',98),('recovery.json','collectorPID',98),
 ('recovery.json','deadlineMs',live['deadlineMs']+1),('armed.json','pid',98)]:
 d=deepcopy(saved);d[name][field]=value;check(name+' '+field+' '+repr(value),d)
for field,value in [('collectorPID',0),('collectorPID',True),('deadlineMs',True),('monotonicMs',-1),('bootID','wrong')]:
 guard=deepcopy(live);guard[field]=value;check('invalid live guard '+field,guard=guard)
check('no captured live guard',guard=None)
report={'passed':True,'checks':checks,'sourceSHA256':hashlib.sha256((w/'environment/xr_npu_closure.py').read_bytes()).hexdigest(),
 'actualMissingReadyFileReproduced':True,'fixtureLiveGuardPartlyReconstructed':True,'originalEpochVerdictChanged':False,
 'futureRunnerMustCaptureLiveGuardBeforeRecovery':True,
 'defect':'Finalizer incorrectly required ready.json after recovery deliberately unlinked it; healthy continuous evidence was rejected.',
 'originalEvidence':'development/ap30/forwarding/npu-transit2/result.json','devicesChanged':False}
(out/'qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'checks':len(checks),'priorVerdictUnchanged':True}))
