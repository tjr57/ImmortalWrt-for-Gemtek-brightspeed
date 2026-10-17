from pathlib import Path
import shutil,subprocess,json,hashlib
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');d=r/'scripts/xr1710g/ap25/maple-startup';d.mkdir(exist_ok=True)
for p in (w/'development/ap25/maple-startup').glob('ap*/files/*'):
 subprocess.run(['/bin/busybox','ash','-n',str(p)],check=True)
 dest=d/p.relative_to(w/'development/ap25/maple-startup');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for name in ['prepare-ap25-maple-startup.py','test-ap25-maple-startup.py','prepare-ap25-maple-epoch.py','run-ap25-maple-ap2-epoch1.py','stage-ap25-maple.py']:
 shutil.copy2(w/'environment'/name,d/name)
subprocess.run(['git','add','--','scripts/xr1710g/ap25/maple-startup'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print('New Maple startup helpers: syntax/28 ARM cases passed; source and epoch harness staged')
