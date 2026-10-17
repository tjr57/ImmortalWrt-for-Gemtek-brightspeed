from pathlib import Path
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap25'
qa=Path('/home/xrdev/artifacts/xr1710g/qa/latest-result.json');assert json.loads(qa.read_text())['passed'];shutil.copy2(qa,out/'defaults-qa.json')
d=r/'scripts/xr1710g/ap25';d.mkdir(exist_ok=True)
for name in ['prepare-ap25-guard.py','test-ap25-guard.py','prepare-ap25-build.py','run-ap25-build.py','check-ap25-build.py','ap25-deploy.py','snapshot-ap25-baseline.py','stage-ap25-release.py']:
 shutil.copy2(w/'environment'/name,d/name)
shutil.copy2(out/'guard-before.sh',d/'guard-before.sh')
p=r/'AGENTS.md';s=p.read_text();assert '<!-- ap25-current:start -->' not in s
notice='''<!-- ap25-current:start -->
## AP25 users BSS gateway debounce (2026-10-10)

- AP2 AP24 logs showed ping-triggered Tizer down/up cycles. Guard now requires
  three consecutive soft ICMP failures; an open gate survives the first good
  retry. Closed gates still require three successes. Holds, pending UCI edits,
  changed context and structural management faults retain immediate handling.
- Actual whole shell/ARM UCI/jsonfilter109ticks passed. Old guard negative
  control closes on its first miss. Network commands are fixtures, not RF tests.
- Built make world-j12, ABI and14defaults cases pass. AP25 SHA
  4ccc14e251b6175c7d3fa71567a52204cc6a7480aa5c4f8db1928ce6a9ea7e9a.
  Entire kernel/DT/modules and boot/SSH/Mesh services byte-identical toAP24;
  onlyguard,preset,version/package metadata differ. APKscripts contentsidentical.
- Latest exact deployment evidence: development/ap25/deployment/ap2|ap1.
  Each scheduled.json is one-shot; inspect only after submission. AP2 first,
  healthy return beforeAP1. No duplicate flash, no phone/main/switch/PC changes.
- NPU remains defaultoff. Historical TXFREE startup cause fixed/proven; separate
  Maple Oops still unresolved. Passiveobserver qualified but noactualfaultcapture.
  AfterAP25 continue observer integration into a bounded original-firmware trial.
<!-- ap25-current:end -->

'''
pos=s.index('<!-- ap24-maple');p.write_text(s[:pos]+notice+s[pos:])
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/ap25'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print('AP25 evidence and tools staged; ready for immutable export')
