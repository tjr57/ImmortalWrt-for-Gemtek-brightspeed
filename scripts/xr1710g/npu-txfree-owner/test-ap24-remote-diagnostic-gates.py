"""Keep all old gates, add only the owner's explicitly authorized access policy."""
from pathlib import Path
from copy import deepcopy
import json,hashlib
from xr_npu_diagnostic_gates import DiagnosticEpoch,DiagnosticRejected
w=Path(__file__).resolve().parents[1];out=w/'development/ap24/owner-trace'
# Existing actual malformed hardware/iperf and synthetic negative regressions
# run unchanged. Redirect the latest report to this new revision's directory.
source=(w/'environment/test-npu-diagnostic-gates.py').read_text()
source=source.replace("result_dir=w/'development/npu-recovery/diagnostic-gates'","result_dir=w/'development/ap24/owner-trace'")
scope={'__file__':str(w/'environment/test-npu-diagnostic-gates.py'),'__name__':'__main__'};exec(compile(source,'existing-gate-tests','exec'),scope)
fixture=scope['fixture'];versions=scope['versions'];boot=scope['boot'];old=scope['old']
digest=hashlib.sha256((w/'development/npu-diagnostic-ap2/promotion.json').read_bytes()).hexdigest()
policy={'ownerAcceptedRemoteLoss':True,'authorizationSHA256':digest}
def sample():
 s=fixture();s['independentAP2WiredRecovery']=False;s['remoteRecoveryAuthorizationSHA256']=digest;return s
def accepted(s,p=policy):DiagnosticEpoch(versions,boot,old,recovery_policy=p).before_traffic(s)
accepted(sample());checks=['explicit owner remote-only policy accepted with healthy actual-style recovery evidence']
def rejected(name,s,p=policy):
 try:accepted(s,p)
 except DiagnosticRejected:checks.append(name)
 else:raise AssertionError(name)
rejected('old default still refuses unavailable wire',sample(),{})
rejected('no owner acceptance',sample(),{**policy,'ownerAcceptedRemoteLoss':False})
rejected('invalid authorization digest',sample(),{**policy,'authorizationSHA256':'x'})
s=sample();s['remoteRecoveryAuthorizationSHA256']='0'*64;rejected('mismatched authorization',s)
s=sample();s.pop('independentAP2WiredRecovery');rejected('missing access state',s)
for name,change in scope['guard_changes']:
 s=sample();change(s['1']['recoveryGuard']);rejected('remote policy preserves '+name,s)
for name,change in scope['changes'][1:]:
 s=sample();change(s);rejected('remote policy preserves '+name,s)
s=sample();s['1']['kernelLog']='TXFREE truncated';rejected('remote consent never accepts a faulted kernel',s)
report={'passed':True,'checks':checks,'sourceSHA256':hashlib.sha256((w/'environment/xr_npu_diagnostic_gates.py').read_bytes()).hexdigest(),
 'authorizationSHA256':digest,'authorizationFromExistingDirectOwnerInstructions':True,'hardwareActivated':False}
(out/'remote-gates-qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'newPolicyCases':len(checks)}))
