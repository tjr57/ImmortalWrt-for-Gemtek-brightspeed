"""Prepare a fresh software-path control after the bounded NPU experiment."""
from pathlib import Path
import ast
w=Path('D:/ChatGPT/XR1710G')
s=(w/'environment/run-ap30-transit.py').read_text()
s=s.replace('development/ap30/forwarding/loaded-transit1','development/ap30/forwarding/software-after-npu2')
s=s.replace('PORT, DURATION, STREAMS = 5330, 20, 4','PORT, DURATION, STREAMS = 5333, 20, 4')
anchor="assert not OUT.exists(), 'Baseline already submitted; inspect existing evidence.'"
assert anchor in s
s=s.replace(anchor,"""prior=json.loads((WORKSPACE/'development/ap30/forwarding/npu-transit2/result.json').read_text())
assert prior['operationCompletedAndRecovered'] and prior['ordinaryRecoveryAndCleanupPassed'] and prior['bothHealthy']
assert not prior['kernelFaultObserved']
"""+anchor)
ast.parse(s);p=w/'environment/run-ap30-software-after-npu.py';assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
s=(w/'environment/analyze-ap30-transit.py').read_text().replace('development/ap30/forwarding/loaded-transit1','development/ap30/forwarding/software-after-npu2')
p=w/'environment/analyze-ap30-software-after-npu.py';assert not p.exists();p.write_text(s,encoding='utf-8',newline='\n')
print('Prepared fresh software comparison; hardware experiment must finish first.')
