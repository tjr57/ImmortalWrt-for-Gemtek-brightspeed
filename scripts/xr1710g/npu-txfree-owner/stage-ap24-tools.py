from pathlib import Path
import shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
d=r/'scripts/xr1710g/npu-txfree-owner';d.mkdir(exist_ok=True)
names=['prepare-ap24-build.py','check-ap24-build.py','ap24-deploy.py','prepare-ap24-live-checks.py','verify-ap24-deployment.py','run-ap24-npu-ap1-epoch1.py','analyze-ap24-npu-trial.py','record-ap24-progress.py','stage-ap24-tools.py']
for n in names:shutil.copyfile(w/'environment'/n,d/n)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-txfree-owner'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print('AP24 reproduction/deployment/evidence tools staged; frozen image export unchanged')
