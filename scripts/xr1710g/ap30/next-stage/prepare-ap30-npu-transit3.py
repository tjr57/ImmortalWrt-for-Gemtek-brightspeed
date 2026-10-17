"""Prepare a fresh epoch after fixing guard-file lifetime accounting."""
from pathlib import Path
import ast
w=Path('D:/ChatGPT/XR1710G');s=(w/'environment/run-ap30-npu-transit2.py').read_text()
def change(old,new):
 global s
 assert old in s,old
 s=s.replace(old,new)
change('development/ap30/forwarding/npu-transit2','development/ap30/forwarding/npu-transit3')
change('from ap27_forwarding_observer import ready,sample_pair,Probes','from ap27_forwarding_observer import ready,sample_pair,Probes\nfrom xr_npu_closure import collector_closed_cleanly')
change("assert json.loads((WORKSPACE/'development/ap30/forwarding-completion.json').read_text())['passed']", """assert json.loads((WORKSPACE/'development/ap30/forwarding-completion.json').read_text())['passed']
closure_qa=json.loads((WORKSPACE/'development/ap30/npu-closure/qa.json').read_text())
assert closure_qa['passed'] and closure_qa['sourceSHA256']==sha(Path(__file__).with_name('xr_npu_closure.py'))
assert closure_qa['originalEpochVerdictChanged'] is False
assert json.loads((WORKSPACE/'development/ap30/forwarding/software-after-npu2/analysis.json').read_text())['passed']
previous=json.loads((WORKSPACE/'development/ap30/forwarding/npu-transit2/result.json').read_text())
assert previous['ordinaryRecoveryAndCleanupPassed'] and previous['bothHealthy']
assert not previous['boundedBidirectionalTransfersQualified']
""")
change("'parameters':parameters,'npuActive':'npu_active=1' in tok,'tokenMetadata':tok,", """'parameters':parameters,'npuActive':'npu_active=1' in tok,'tokenMetadata':tok,
    'meshStation':station,'cpuCounters':read(c,'cat /proc/stat'),'softirqCounters':read(c,'cat /proc/softirqs'),""")
anchor="  assert activation['bootID']==diag"
change(anchor,anchor+'''
  guard_live=data_json(c,record+'/ready.json')
  assert guard_live and guard_live['bootID']==diag
  guard_file=out/'guard-ready-live.json'
  if guard_file.exists():assert json.loads(guard_file.read_text())==guard_live
  else:save('guard-ready-live.json',guard_live)
''')
start=s.index(' capture_complete=(closed.get(')
end=s.index("\n if closed.get('fault') is True:",start)
s=s[:start]+''' guard_file=out/'guard-ready-live.json'
 guard_live=json.loads(guard_file.read_text()) if guard_file.exists() else None
 capture_complete=collector_closed_cleanly(saved,diag,guard_live)
 save('closure-verification.json',{'passed':capture_complete,'liveGuardCapturedBeforeRecovery':guard_live is not None,
  'retiredReadyFileRequiredAfterRecovery':False,'sourceSHA256':sha(Path(__file__).with_name('xr_npu_closure.py'))})
'''+s[end:]
change('5332','5334');change(':14D4',':14D6')
ast.parse(s);p=w/'environment/run-ap30-npu-transit3.py';assert not p.exists()
p.write_text(s,encoding='utf-8',newline='\n')
print('New epoch3 prepared with captured live guard identity; not submitted.')
