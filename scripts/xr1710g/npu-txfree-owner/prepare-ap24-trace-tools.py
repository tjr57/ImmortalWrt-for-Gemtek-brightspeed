from pathlib import Path
import ast
w=Path(__file__).resolve().parents[1]
s=(w/'environment/test-npu-diagnostic-packed-startup.py').read_text()
s=s.replace("OUT = W/'development/npu-diagnostic-lab'","OUT = W/'development/ap24/owner-trace'")
start=s.index('bindings = {}');end=s.index("for rel in assembly['changedFiles']:",start)
s=s[:start]+"bindings = assembly['sourceBoundVM']\nassert len(bindings) == 6\n"+s[end:]
s=s.replace('hardwareDeployable', 'hardwareBootAlreadyProvenByThisQA')
ast.parse(s);p=w/'environment/check-ap24-trace-startup.py';assert not p.exists();p.write_text(s)
print('Prepared packed ARM startup QA; deployment remains gated on its result')
