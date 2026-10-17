"""Compile the private AP31 VLAN candidate against actual ARM kernel headers."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib,shutil,os,fcntl,argparse
parser=argparse.ArgumentParser();parser.add_argument('--candidate',choices=['ppe-vlan','ppe-revocation'],default='ppe-vlan');args=parser.parse_args()
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap31'/args.candidate
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl';base=k/'drivers/net/ethernet/airoha'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
qa=json.loads((out/'qa.json').read_text());candidate_sha=qa.get('candidateSHA256',qa.get('sourceSHA256'));assert qa['passed'] and candidate_sha==sha(out/'airoha_ppe.c')
for n in ('airoha_ppe.c','airoha_eth.h'):assert sha(base/n)==sha(out/('before-'+n))
held={str(p.relative_to(r)):sha(p) for p in [r/'.config',k/'.config',k/'vmlinux',k/'Module.symvers',base/'airoha_ppe.c',base/'airoha_eth.h']}
lab=r.parent/'boot-lab'/('ap31-'+args.candidate);lab.mkdir(exist_ok=True)
build=lab/datetime.now().strftime('%Y%m%d-%H%M%S');build.mkdir()
for p in base.glob('*.h'):shutil.copy2(p,build/p.name)
for n in ('airoha_ppe.c','airoha_eth.h'):shutil.copy2(out/n,build/n)
(build/'Makefile').write_text('obj-m += airoha_ppe.o\n')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cmd=['make','-C',str(k),'ARCH=arm64','CROSS_COMPILE='+str(tc/'bin/aarch64-openwrt-linux-musl-'),'M='+str(build),'airoha_ppe.o','-j12','V=1']
 p=subprocess.run(cmd,env=dict(os.environ,STAGING_DIR=str(tc)),capture_output=True,text=True)
(out/'kernel-object-build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr[-3500:]
assert held=={name:sha(r/name) for name in held}
shutil.copy2(build/'airoha_ppe.o',out/'airoha_ppe.o')
report={'passed':True,'jobs':12,'candidateSHA256':candidate_sha,'objectSHA256':sha(out/'airoha_ppe.o'),'actualArmKernelAPIs':True,'privateTranslationUnitOnly':True,'productionStateUnchanged':True,'heldHashes':held,'fullImageOrHardwareQualified':False}
(out/'kernel-object-build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({n:v for n,v in report.items() if n!='heldHashes'}))
