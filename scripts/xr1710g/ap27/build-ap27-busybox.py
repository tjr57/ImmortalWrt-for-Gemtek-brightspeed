from pathlib import Path
from datetime import datetime
import subprocess,hashlib,json,fcntl,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');out=Path('/mnt/d/ChatGPT/XR1710G/development/ap27/ping-rxbuf')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
config=sha(r/'.config');prepared=json.loads((out/'prepared.json').read_text());assert prepared['configurationSHA256']==config
lock=Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
log=out/('build-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
with log.open('w') as f:p=subprocess.run(['make','package/utils/busybox/compile','-j12','V=s'],cwd=r,stdout=f,stderr=subprocess.STDOUT)
lock.close();assert p.returncode==0,str(log);assert sha(r/'.config')==config
b=r/'build_dir/target-aarch64_cortex-a53_musl/busybox-default/busybox-1.38.0'
assert sha(b/'networking/ping.c')==sha(out/'patched-ping.c')
source=b/'ipkg-aarch64_cortex-a53/busybox/bin/busybox';assert source.exists()
shutil.copy2(source,out/'busybox')
result={'passed':True,'jobs':12,'sourcePatchSHA256':prepared['patchSHA256'],'binarySHA256':sha(out/'busybox'),'configurationPreserved':True,'packageOnly':True,'productionFirmwareNotChanged':True,'log':str(log)}
(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
