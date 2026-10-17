from pathlib import Path
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap28'
packed=json.loads((out/'packed-files-qa.json').read_text());assert packed['passed']
p=w/'environment/ap28-deploy.py';assert not p.exists()
s=(w/'environment/ap27-deploy.py').read_text().replace('ap27','ap28').replace('AP27','AP28').replace('20261010-ap26-d331711d','20261010-ap27-d331711d')
s=s.replace("(root/'ping-rxbuf/live-queue-qa.json')", "(root.parent/'ap27/ping-rxbuf/live-queue-qa.json')")
p.write_text(s);assert "BASELINE='20261010-ap27-d331711d'" in s
dest=r/'scripts/xr1710g/ap28'
for n in ['check-ap28-build.py','prepare-ap28-deployment.py','ap28-deploy.py']:shutil.copy2(w/'environment'/n,dest/n)
p=r/'AGENTS.md';s=p.read_text();s=s.replace('  compile and nativeASan/UBSan/ARM tests pass; full build running. Not flashed.',f"  compile and nativeASan/UBSan/ARM tests pass; full-j12 build/ABI/packed\n  checks pass. Image {packed['imageSHA256']}.\n  Not flashed. Fresh one-shot state: development/ap28/deployment/apN.\n  Preserve config and accept AP2 before AP1; never repeat submitted flashes.")
p.write_text(s)
subprocess.run(['git','add','--','AGENTS.md','xr1710g-ap.config','scripts/xr1710g/ap27','scripts/xr1710g/ap28','package/kernel/mac80211/Makefile','package/kernel/mac80211/patches/subsys/9999e-XR-Mesh-early-RX-drop-metadata.patch'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
subprocess.run(['python3',str(w/'environment/record-ap-build.py'),'--version','20261010-ap28-d331711d','--destination-name','20261010-ap28-d331711d-development','--artifact-report',str(out/'artifact-qa.json'),'--defaults-qa',str(out/'defaults-qa.json'),'--build-log','build-ap28.log'],check=True)
