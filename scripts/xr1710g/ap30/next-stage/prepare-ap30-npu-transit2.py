"""Prepare a new, immutable one-boot experiment using the bounded480 profile."""
from pathlib import Path
import ast
w=Path('D:/ChatGPT/XR1710G')
s=(w/'environment/run-ap30-npu-transit1.py').read_text()
def change(old,new):
 global s
 assert old in s,old
 s=s.replace(old,new)
change('with qualified recovery6.','with a qualified fixed480s recovery profile.')
change("base=WORKSPACE/'development/npu-guarded-boot';recovery=WORKSPACE/'development/npu-recovery6'",
       "candidate=WORKSPACE/'development/ap30/npu-window480'\nbase=candidate/'activation';recovery=candidate/'recovery'")
change('development/ap30/forwarding/npu-transit1','development/ap30/forwarding/npu-transit2')
change("base/'xr-diag-activate-package'", "base/'xr-diag-activate'")
change("WORKSPACE/'development/ap30/npu-gates/ap1/files/xr-recovery-once'", "recovery/'files/xr-recovery-once'")
change("WORKSPACE/'development/ap30/npu-gates/ap1/shipped-shell-qa.json'", "recovery/'shipped-shell-qa.json'")
change("assert items['/usr/libexec/xr-recovery-once'].read_text()==(recovery/'files/xr-recovery-once').read_text().replace('\"$binary\" \"$record\" 180 ','\"$binary\" \"$record\" 240 ')",
       "assert items['/usr/libexec/xr-recovery-once'].read_text()==(WORKSPACE/'development/npu-recovery6/files/xr-recovery-once').read_text().replace('\"$binary\" \"$record\" 180 ','\"$binary\" \"$record\" 480 ')")
change("WORKSPACE/'development/ap24/owner-trace/remote-gates-qa.json'", "candidate/'remote-gates-qa.json'")
start=s.index('for directory,count in ((base,11),(recovery,18)):')
end=s.index("manifest=json.loads((WORKSPACE/'development/ap30/npu-gates/prepared.json').read_text())",start)
checks='''# Bind every changed component to fresh exact-source/native/ARM/VM tests.
prepared=json.loads((candidate/'prepared.json').read_text())
for name,digest in prepared['sourceHashes'].items():assert sha(candidate/name)==digest
limits=json.loads((candidate/'limits-qa.json').read_text())
assert limits['passed'] and limits['maximumSeconds']==480 and limits['maxCollectorRequestSeconds']==495
for name,key in [('recovery/xr-diag-recovery','recoverySHA256'),('recovery/xr-diag-capture','captureSHA256'),('activation/xr-diag-activate','activationSHA256')]:
 assert sha(candidate/name)==limits[key]
for directory,file,source in [(base,'function-qa.json','src/activate.c'),(recovery,'host-qa.json','src/recovery.c'),(recovery,'capture-host-qa.json','src/capture.c')]:
 qa=json.loads((directory/file).read_text());assert qa['passed'] and qa['sourceSHA256']==sha(directory/source)
assert json.loads((base/'function-qa.json').read_text())['binarySHA256']==sha(items['/usr/libexec/xr-diag-activate'])
vm=json.loads((base/'vm/result-latest.json').read_text());assert vm['passed'] and len(vm['cases'])==11
for case in vm['cases']:
 assert case['sourceSHA256']==sha(base/'src/activate.c') and case['guardSHA256']==sha(recovery/'src/recovery.c')
 assert case['captureSHA256']==sha(recovery/'src/capture.c') and not case['durationAdapterUsed']
 assert case['secondBootNpuParameterOff']
assert json.loads((WORKSPACE/'development/npu-recovery6/vm/result-latest.json').read_text())['passed']
live_recovery=json.loads((WORKSPACE/'development/ap30/recovery6-live1/result.json').read_text())
assert live_recovery['passed'] and live_recovery['completeContinuousCollectorClosureRequiredAndObserved']
# Expiry,10s orderly grace, collector and recovery logic are unchanged.
previous=(WORKSPACE/'development/npu-recovery6/src/recovery.c').read_text()
expected=previous.replace('#define _GNU_SOURCE','#define _GNU_SOURCE\\n#include "xr_diag_limits.h"').replace('seconds<15||seconds>240','!xr_diag_duration_valid(seconds)').replace('seconds+15','seconds+XR_DIAG_CAPTURE_TAIL_SECONDS')
assert (recovery/'src/recovery.c').read_text()==expected
assert sha(recovery/'src/capture.c')==sha(WORKSPACE/'development/npu-recovery6/src/capture.c')
qa=json.loads((candidate/'window-gates-qa.json').read_text())
assert qa['passed'] and len(qa['checks'])==52 and qa['sourceSHA256']==sha(Path(__file__).with_name('xr_npu_diagnostic_gates.py'))
assert len(json.loads((candidate/'qa.json').read_text())['checks'])==78
save('candidate-qualified.json',{'limits':limits,'VMcases':len(vm['cases']),'gates':qa,'recovery6LiveInheritedLogic':True,
 'fixedWindowChangedBeforeBoot':True,'runtimeDeadlineExtension':False,'productionPackagesChanged':False})
'''
s=s[:start]+checks+s[end:]
change("WORKSPACE/'development/ap30/npu-gates/activation-vm/result-latest.json'", "base/'vm/result-latest.json'")
change("'deadlineSeconds':240", "'deadlineSeconds':480")
change("'activationWithRecovery6Cases':11", "'activationWithFixed480ProfileCases':11")
change('limit=time.monotonic()+660','limit=time.monotonic()+900')
change('recovery_policy=recovery_policy)','recovery_policy=recovery_policy,maximum_seconds=480)')
change('5331','5332');change(':14D3',':14D4')
change("'AP30ForwardingFixesAndRecovery6Trial':True", "'AP30ForwardingFixesAndFixed480ProfileTrial':True")
# Require matching closure identity/timing, besides sequence completeness.
change("all(closed.get(key) is False for key in ('fault','failed','capped')))",
 '''all(closed.get(key) is False for key in ('fault','failed','capped')) and
  closed.get('pid')==saved.get('ready.json',{}).get('collectorPID') and
  type(closed.get('monotonicMs')) is int and
  0<closed['monotonicMs']<saved.get('ready.json',{}).get('deadlineMs',0))''')
ast.parse(s)
target=w/'environment/run-ap30-npu-transit2.py';assert not target.exists()
target.write_text(s,encoding='utf-8',newline='\n')
print('Fresh fixed480s AP30 trial prepared; not submitted.')
