"""Record current one-shot states so interrupted work is inspected, never repeated."""
from pathlib import Path
from datetime import datetime
import json,re,shutil,subprocess
W=Path('/mnt/d/ChatGPT/XR1710G');R=Path('/home/xrdev/projects/xr1710g/openwrt');O=W/'development/ap24/prefill-probe'
j=lambda p:json.loads(p.read_text());states={}
for unit in (1,2):
 for phase in ('trace','restore'):
  p=O/f'deployment/ap{unit}-{phase}';states[f'ap{unit}-{phase}']={f:j(p/(f+'.json')) for f in ('scheduled','returned','result') if (p/(f+'.json')).exists()}
 p=O/f'ap{unit}-epoch1';states[f'ap{unit}-epoch']={f:j(p/(f+'.json')) for f in ('operation','result','analysis') if (p/(f+'.json')).exists()}
report={'at':datetime.now().astimezone().isoformat(),'experiment':'AP24 single startup prefill intervention','states':states,
 'artifactSHA256':j(O/'result.json')['artifactSHA256'],'defaultNpuOff':True,'productionSourceUnchanged':True,
 'remaining':'Finish submitted diagnostic epochs, restore original AP24 AP2 then AP1, final health and causal analysis','oneShotNeverRerun':True}
(O/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
p=R/'AGENTS.md';s=p.read_text();s=re.sub(r'<!-- ap24-prefill-current:start -->.*?<!-- ap24-prefill-current:end -->\n?', '',s,flags=re.S)
notice='''<!-- ap24-prefill-current:start -->
## AP24 startup-only prefill causal experiment (2026-10-10)

- Authoritative live progress: development/ap24/prefill-probe/progress.json,
 plus individual deployment scheduled/returned/result and apN-epoch1/operation.
 Never repeat submitted one-shot upgrades/epochs. Inspect/resume their results.
- Private image a67b7f2ca995a242808b5aeaae731764cd417aa4dfc2b815dd61853f70e9b1dd
 changes only mt76 startup queue initialization from AP24 production semantics:
 restore exact old prefill only at startup; all AP24 runtime fill/reset/cleanup/
 poll guards unchanged. Two metadata log lines; no payload/token capture.
- New exact-function real KASAN VM variants pass; imports/exports/ABI identical,
 38 other packed production files unchanged, 14 packed ARM startup checks pass.
 Source and frozen AP24 unchanged; original producer b48 hook/recovery reused.
- Deploy AP2, bounded epoch, AP1, bounded epoch; restore original411299ad AP2
 then AP1. Tools ap24-prefill-deploy.py UNIT trace|restore upgrade|inspect,
 run-ap24-prefill-apN-epoch1.py run. Owner remote-loss authorization persists.
- Startup DMA enabled before NPU descriptor init; MT7996 configures prefetch4.
 This alone does not prove actual PCIe/cache timing. This experiment isolates
 startup prefill from the later generic host operations fixed in AP24.
 No phone/main router/switch/PC network changes. Goal remains active pending
 actual results; separate Maple Oops must not be conflated with TXFREE.
<!-- ap24-prefill-current:end -->
'''
pos=s.index('<!-- ap24-followup-final:start -->');p.write_text(s[:pos]+notice+'\n'+s[pos:])
dest=R/'scripts/xr1710g/npu-txfree-owner/prefill-probe';dest.mkdir(exist_ok=True)
for path in (W/'environment').glob('*ap24*prefill*.py'):shutil.copy2(path,dest/path.name)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-txfree-owner/prefill-probe'],cwd=R,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=R,check=True)
print(json.dumps({'recorded':True,'at':report['at']}))
