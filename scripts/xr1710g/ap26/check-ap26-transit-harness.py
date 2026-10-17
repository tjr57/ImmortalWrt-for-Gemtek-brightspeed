"""Bind the new network workload to previously qualified unchanged safety code."""
from pathlib import Path
import ast,difflib,hashlib,json,re
w=Path('D:/ChatGPT/XR1710G');out=w/'development/ap26'
old=(w/'environment/run-ap25-maple-ap1-load1.py').read_text()
new=(w/'environment/run-ap26-npu-transit-ap1.py').read_text()
def functions(source):return {x.name:ast.dump(x,include_attributes=False) for x in ast.parse(source).body if isinstance(x,ast.FunctionDef)}
a,b=map(functions,(old,new));assert a.keys()==b.keys()
changed=[name for name in a if a[name]!=b[name]];assert changed==['snapshot']
# The one changed snapshot only adds interface counters for transit evidence.
assert new.replace("row={'interfaceCounters':read(c,'cat /proc/net/dev'),'version'","row={'version'").count("row={'version'")==1
normalized=functions(new.replace("row={'interfaceCounters':read(c,'cat /proc/net/dev'),'version'","row={'version'"))
assert normalized['snapshot']==a['snapshot']
patterns=[n.args[0].value for n in ast.walk(ast.parse(new)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='fullmatch' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str) and n.args[0].value.startswith('/tmp/')]
assert len(patterns)==1
assert all(re.fullmatch(patterns[0],'/tmp/xr-ap26-transit-deadbeef-'+str(i)+suffix) for i in [0,1] for suffix in ['.json','.json.exit'])
assert not re.fullmatch(patterns[0],'/tmp/xr-ap26-transit-deadbeef-2.json')
old_safe=old[old.index('c=connect(1)\ntry:\n assert not kernel_findings'):old.index('fault_event=threading.Event()')]
new_safe=new[new.index('c=connect(1)\ntry:\n assert not kernel_findings'):new.index('fault_event=threading.Event()')]
assert new_safe.replace('PC.101 to AP2.4 through AP1 lan2+mesh6g; two20secondTCPdirections,4streams,unpaced','Two20secondTCPdirections,4streams,unpaced,AP2clientAP1server')==old_safe
guard=w/'environment/xr_npu_diagnostic_gates.py'
qa=json.loads((w/'development/ap24/owner-trace/remote-gates-qa.json').read_text());assert qa['passed'] and qa['sourceSHA256']==hashlib.sha256(guard.read_bytes()).hexdigest()
packed=json.loads((out/'packed-files-qa.json').read_text());oldpacked=json.loads((w/'development/ap25/packed-files-qa.json').read_text())
for p,h in oldpacked['matchedFiles'].items():
 if p.startswith(('lib/modules/','etc/init.d/')):assert packed['matchedFiles'][p]==h
(out/'npu-transit-harness.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='AP25-accepted-AP-local-load',tofile='AP26-new-wired-Mesh-transit')))
report={'passed':True,'unchangedFunctions':[n for n in a if n!='snapshot'],'snapshotOnlyAddsInterfaceCounters':True,
 'activationRecoveryAndRequestSubmissionByteIdentical':True,'diagnosticGateSourceUnchanged':True,'AP25KernelDTBootModuleIdentityAlreadyVerified':True,
 'newWorkload':'PC .101 -> AP1 bridge/NPU -> mesh6g -> AP2 .4 TCP endpoint; two20s/P4 directions',
 'harnessSHA256':hashlib.sha256(new.encode()).hexdigest(),'newNetworkTrafficNotYetExecuted':True}
(out/'npu-transit-harness-qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'unchangedSafetyFunctions':len(a)-1}))
