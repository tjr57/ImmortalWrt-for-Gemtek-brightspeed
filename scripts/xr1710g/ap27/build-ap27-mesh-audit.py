from pathlib import Path
from datetime import datetime
import subprocess,hashlib,json,fcntl,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');out=Path('/mnt/d/ChatGPT/XR1710G/development/ap27/mesh-rx-audit')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
config=sha(r/'.config');lock=Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
log=out/('build-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
with log.open('w') as f:p=subprocess.run(['make','package/kernel/mac80211/compile','-j12','V=s'],cwd=r,stdout=f,stderr=subprocess.STDOUT)
lock.close();assert p.returncode==0,str(log);assert sha(r/'.config')==config
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mac80211-regular/backports-7.2/net/mac80211'
assert sha(b/'rx.c')==sha(out/'patched-rx.c');assert sha(b/'xr-mesh-rx-audit.h')==sha(out.parent/'mesh-rx-audit.h')
shutil.copy2(b/'mac80211.ko',out/'mac80211.ko')
result={'passed':True,'jobs':12,'moduleSHA256':sha(out/'mac80211.ko'),'configurationPreserved':True,'packageOnly':True,'productionFirmwareNotChanged':True,'log':str(log)}
(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
