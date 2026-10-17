"""Compile candidate against the real ARM kernel API in a private object directory."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib,shutil,os,fcntl
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap31/ppe-target'
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();qa=json.loads((out/'qa.json').read_text())
assert qa['passed'] and qa['candidateSHA256']==sha(out/'after.c')
base=k/'drivers/net/ethernet/airoha';assert sha(base/'airoha_ppe.c')==qa['baseSHA256']
held={str(p.relative_to(r)):sha(p) for p in [r/'.config',k/'.config',k/'vmlinux',k/'Module.symvers',base/'airoha_ppe.c']}
lab=r.parent/'boot-lab/ap31-ppe-target';lab.mkdir(exist_ok=True)
build=lab/datetime.now().strftime('%Y%m%d-%H%M%S');build.mkdir()
shutil.copy2(out/'after.c',build/'airoha_ppe.c')
for p in base.glob('*.h'):shutil.copy2(p,build/p.name)
(build/'Makefile').write_text('obj-m += airoha_ppe.o\n')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cmd=['make','-C',str(k),'ARCH=arm64','CROSS_COMPILE='+str(tc/'bin/aarch64-openwrt-linux-musl-'),
      'M='+str(build),'airoha_ppe.o','-j12','V=1']
 p=subprocess.run(cmd,env=dict(os.environ,STAGING_DIR=str(tc)),capture_output=True,text=True)
(out/'kernel-object-build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr[-2500:]
assert held=={name:sha(r/name) for name in held}
shutil.copy2(build/'airoha_ppe.o',out/'airoha_ppe.o')
dsa=(k/'net/dsa/dsa.c').read_text();start=dsa.index('struct dsa_port *dsa_port_from_netdev(')
dsa_fn=dsa[start:dsa.index('\n}',start)+2]
assert 'if (!netdev || !dsa_user_dev_check(netdev))' in dsa_fn
report={'passed':True,'jobs':12,'objectSHA256':sha(out/'airoha_ppe.o'),'candidateSHA256':qa['candidateSHA256'],
 'kernelAPI':'actual AP30 arm64 kernel headers/config; private translation-unit build',
 'productionKernelImageConfigSourceAndSymbolsUnchanged':True,'heldHashes':held,
 'objectOnlyNotLinkedFirmware':True,'liveDevicesChanged':False,
 'nullTargetClarification':'Current DSA API already checks NULL, and existing L2 context code rejects missing odev later. This is earlier/single-target validation, not a demonstrated NULL crash repair.',
 'actualDSAFunction':dsa_fn,'historicalCrashRootCauseProven':False}
(out/'kernel-object-build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('heldHashes','actualDSAFunction')}))
