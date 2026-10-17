from pathlib import Path
from datetime import datetime
import subprocess,hashlib,json,fcntl,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');out=Path('/mnt/d/ChatGPT/XR1710G/development/ap30/eht-header');out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();qa=json.loads((out/'qa/result.json').read_text());assert qa['passed']
config=sha(r/'.config');lock=Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
log=out/('build-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
with log.open('w') as f:p=subprocess.run(['make','package/kernel/mt76/compile','-j12','V=s'],cwd=r,stdout=f,stderr=subprocess.STDOUT)
lock.close();assert p.returncode==0,str(log);assert sha(r/'.config')==config
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791'
assert sha(b/'mt76.h')==qa['headerSHA256'];assert sha(b/'mac80211.c')==qa['pnSourceSHA256']
modules={}
for n in ['mt76.ko','mt76-connac-lib.ko','mt7996/mt7996e.ko']:
 p=out/Path(n).name;shutil.copy2(b/n,p);modules[p.name]=sha(p)
result={'passed':True,'jobs':12,'moduleHashes':modules,'configurationPreserved':True,'packageOnly':True,'log':str(log)}
(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
