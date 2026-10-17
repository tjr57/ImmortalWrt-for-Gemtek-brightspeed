"""Complete source staging; keep raw console output in its original evidence path."""
from pathlib import Path
import hashlib,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
p=r/'scripts/xr1710g/ap32/bridge-transaction/vm-20261011-012557.log'
original=w/'development/ap32/bridge-transaction/vm-20261011-012557.log'
assert p.read_bytes()==original.read_bytes()
p.unlink()
for name in ['record-ap32-source.py','finalize-ap32-source-archive.py']:
 shutil.copy2(w/'environment'/name,r/'scripts/xr1710g/ap32'/name)
subprocess.run(['git','add','--','scripts/xr1710g/ap32'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print('Source archive checked; original raw VM log preserved '+hashlib.sha256(original.read_bytes()).hexdigest())
