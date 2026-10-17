"""Exercise the bounded profile while preserving historical rejected epochs."""
from pathlib import Path
import json,hashlib
from xr_npu_diagnostic_gates import DiagnosticEpoch,DiagnosticRejected
w=Path(__file__).resolve().parents[1];out=w/'development/ap30/npu-window480'
source=(w/'environment/test-ap24-remote-diagnostic-gates.py').read_text()
source=source.replace('development/ap24/owner-trace','development/ap30/npu-window480')
scope={'__file__':str(w/'environment/test-ap24-remote-diagnostic-gates.py'),'__name__':'__main__'}
exec(compile(source,'preserved-gates-and-owner-policy','exec'),scope)
sample=scope['sample'];policy=scope['policy'];versions=scope['versions'];boot=scope['boot'];old=scope['old']
checks=[]
def attempt(name,s,profile=480,accept=False):
 try:DiagnosticEpoch(versions,boot,old,recovery_policy=policy,maximum_seconds=profile).before_traffic(s)
 except DiagnosticRejected:
  assert not accept,name
 else:assert accept,name
 checks.append(name)
for remaining in (30000,120000,240000,240001,480000):
 s=sample();s['1']['recoveryGuard']['deadlineMs']=100000+remaining
 attempt('480 profile accepts remaining '+str(remaining),s,accept=True)
for remaining in (-1,0,29999,480001,600000):
 s=sample();s['1']['recoveryGuard']['deadlineMs']=100000+remaining
 attempt('480 profile rejects remaining '+str(remaining),s)
s=sample();s['1']['recoveryGuard']['deadlineMs']=580000
attempt('240 profile still rejects 480s evidence',s,profile=240)
for profile in (True,0,180,481,600,'480',None):
 attempt('unqualified profile '+repr(profile),sample(),profile=profile)
for name,change in scope['scope']['guard_changes']:
 s=sample();s['1']['recoveryGuard']['deadlineMs']=580000;change(s['1']['recoveryGuard'])
 attempt('480 profile preserves '+name,s)
for name,change in scope['scope']['changes'][1:]:
 s=sample();s['1']['recoveryGuard']['deadlineMs']=580000;change(s)
 attempt('480 profile preserves '+name,s)
s=sample();s['1']['recoveryGuard']['deadlineMs']=580000;s['1']['kernelLog']='BUG: actual failure'
epoch=DiagnosticEpoch(versions,boot,old,recovery_policy=policy,maximum_seconds=480)
try:epoch.before_traffic(s)
except DiagnosticRejected:pass
else:raise AssertionError('fault accepted')
try:epoch.before_traffic(sample())
except DiagnosticRejected:checks.append('480 profile fault cannot be cleared by clean sample')
else:raise AssertionError('fault latch cleared')
report={'passed':True,'checks':checks,'sourceSHA256':hashlib.sha256((w/'environment/xr_npu_diagnostic_gates.py').read_bytes()).hexdigest(),
 'oldDefaultMaximumSeconds':240,'newExplicitMaximumSeconds':480,'hardwareActivated':False,
 'historicalTestsReusedWithoutRejudging':True}
(out/'window-gates-qa.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'newBoundedProfileChecks':len(checks)}))
