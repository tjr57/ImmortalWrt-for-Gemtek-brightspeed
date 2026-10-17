"""Bind one-shot deployment/epoch tools to a distinct private experiment."""
from pathlib import Path
W=Path(__file__).resolve().parents[1];E=W/'environment'
def write(name,s):
 p=E/name;assert not p.exists();p.write_text(s)
s=(E/'check-ap24-trace-startup.py').read_text().replace('development/ap24/owner-trace','development/ap24/prefill-probe')
s=s.replace('assert len(bindings) == 6', "assert len(bindings) == 7 and 'singleStartupPrefill' in bindings")
write('check-ap24-prefill-startup.py',s)
s=(E/'ap24-trace-deploy.py').read_text().replace('development/ap24/owner-trace','development/ap24/prefill-probe')
s=s.replace("remote=f'/tmp/xr-ap24-{variant}-verified.itb'", "remote=f'/tmp/xr-ap24-prefill-{variant}-verified.itb'")
s=s.replace("assert json.loads((w/'development/ap24/boot-lab/result.json').read_text())['vmPrecheckPassed']", "assert json.loads((w/'development/ap24/boot-lab/result.json').read_text())['vmPrecheckPassed']\nassert json.loads((base/'vm/vm-result-latest.json').read_text())['passed']\nassert json.loads((base/'module-build.json').read_text())['moduleSHA256']==lab['changedFiles']['lib/modules/6.18.54/mt76.ko']['sha256']")
write('ap24-prefill-deploy.py',s)
for unit in (1,2):
 s=(E/f'run-ap24-trace-ap{unit}-epoch1.py').read_text().replace('development/ap24/owner-trace','development/ap24/prefill-probe')
 # Capture boot metadata containing the single startup intervention. On a
 # fast failure the independent kernel collector persists these same lines.
 s=s.replace("if not (out/'active-observation.json').exists():", "if not (out/'active-observation.json').exists():\n            (out/'active-kernel.txt').write_bytes(command(c,'dmesg')[0])")
 write(f'run-ap24-prefill-ap{unit}-epoch1.py',s)
print('Private diagnostic tools prepared; no device operations')
