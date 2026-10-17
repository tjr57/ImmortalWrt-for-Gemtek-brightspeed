"""Compile every changed AP33 kernel translation unit without editing production."""
from pathlib import Path
from datetime import datetime
import fcntl,hashlib,json,os,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out=w/'development/ap33/bridge-policy';prep=json.loads((out/'prepared.json').read_text())
tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for path,h in prep['sources'].items():
 assert sha(k/path)==h['before'] and sha(out/Path(path).name)==h['after'],path
held={str(p):sha(p) for p in [r/'.config',k/'.config',k/'Module.symvers',k/'vmlinux',*[k/p for p in prep['sources']]]}
lab=r.parent/'boot-lab/ap33-bridge-objects'/datetime.now().strftime('%Y%m%d-%H%M%S');lab.mkdir(parents=True)
objects={}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for path in prep['sources']:
  if not path.endswith('.c'):continue
  name=Path(path).stem;origin=(k/path).parent;build=lab/name;build.mkdir()
  for p in origin.glob('*.h'):shutil.copy2(p,build/p.name)
  for n in [name+'.c','if_bridge.h']:shutil.copy2(out/n,build/n)
  includes='-include $(src)/if_bridge.h'
  if name.startswith('br_'):includes+=' -include $(src)/br_private.h'
  (build/'Makefile').write_text('obj-m += '+name+'.o\nccflags-y += '+includes+'\n')
  p=subprocess.run(['make','-C',str(k),'ARCH=arm64','CROSS_COMPILE='+str(tc/'bin/aarch64-openwrt-linux-musl-'),
   'M='+str(build),name+'.o','-j12','V=1'],capture_output=True,text=True,env=dict(os.environ,STAGING_DIR=str(tc)))
  (out/(name+'-'+lab.name+'-build.log')).write_text(p.stdout+p.stderr)
  assert p.returncode==0,p.stderr[-4000:]
  objects[name]=sha(build/(name+'.o'))
assert held=={p:sha(Path(p)) for p in held}
report={'passed':True,'jobs':12,'objects':objects,'sources':prep['sources'],'productionStateUnchanged':True,'heldHashes':held,'fullImageOrHardwareQualified':False}
(out/'kernel-object-build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'objects':list(objects),'jobs':12}))
