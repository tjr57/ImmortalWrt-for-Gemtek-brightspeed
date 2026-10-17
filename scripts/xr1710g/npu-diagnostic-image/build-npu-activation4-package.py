"""Promote the VM-qualified early-debugfs correction into optional package release4."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib,fcntl,shutil
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
base=w/'development/npu-ap1-debugfs';src=base/'activation';out=w/'development/npu-activation4'
out.mkdir(exist_ok=True);assert not (out/'package-build.json').exists()
dest=r/'package/network/config/xr1710g-npu-diagnostic'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
vm=json.loads((src/'vm/result-latest.json').read_text());assert vm['passed'] and len(vm['cases'])==3
for c in vm['cases']:
    assert c['sourceSHA256']==sha(src/'src/activate.c') and c['helperSHA256']==sha(src/'files/xr-npu-guarded-once')
    assert c['guardSHA256']==sha(base/'recovery/src/recovery.c') and c['captureSHA256']==sha(base/'recovery/src/capture.c')
shell=json.loads((src/'shipped-shell-qa.json').read_text())
assert shell['passed'] and len(shell['checks'])==23 and shell['helperSHA256']==sha(src/'files/xr-npu-guarded-once')
assert sha(dest/'src/activate.c')==sha(src/'src/activate.c')
assert sha(dest/'files/xr_guarded_npu')==sha(src/'files/xr_guarded_npu')
assert sha(dest/'files/xr-npu-guarded-once')==sha(w/'development/npu-activation3/files/xr-npu-guarded-once')
shutil.copytree(src/'files',out/'files');shutil.copytree(src/'src',out/'src')
make=(dest/'Makefile').read_text();assert make.count('PKG_RELEASE:=3')==1
make=make.replace('PKG_RELEASE:=3','PKG_RELEASE:=4');(out/'Makefile').write_text(make)
config=sha(r/'.config');image=next((w/'builds/20261010-ap23-d331711d-development').glob('*-squashfs-sysupgrade.itb'));before=sha(image)
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for name in ('Makefile','files/xr-npu-guarded-once'):shutil.copy2(out/name,dest/name)
    log=out/('package-build-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    with log.open('w') as f:
        p=subprocess.run(['make','package/network/config/xr1710g-npu-diagnostic/compile','-j12','V=s','CONFIG_PACKAGE_xr1710g-npu-diagnostic=m','CONFIG_PACKAGE_xr1710g-diag-recovery=m'],cwd=r,stdout=f,stderr=subprocess.STDOUT)
assert p.returncode==0,str(log)
assert sha(r/'.config')==config and sha(image)==before
pkgroot=r/'build_dir/target-aarch64_cortex-a53_musl/xr1710g-npu-diagnostic/ipkg-aarch64_cortex-a53/xr1710g-npu-diagnostic'
# APK packaging uses the same package staging tree on this checkout.
roots=list((r/'build_dir/target-aarch64_cortex-a53_musl/xr1710g-npu-diagnostic').glob('ipkg-*/xr1710g-npu-diagnostic'))
assert len(roots)==1
assert sha(roots[0]/'usr/libexec/xr-npu-guarded-once')==sha(src/'files/xr-npu-guarded-once')
subprocess.run(['git','add','--',str(dest.relative_to(r))],cwd=r,check=True)
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'release':4,'jobs':12,'packageOnly':True,
        'helperSHA256':sha(src/'files/xr-npu-guarded-once'),'activationCUnchanged':True,
        'ARMChecks':23,'realKernelRebootPairChecks':3,'configurationUnchanged':True,'frozenAP23Unchanged':True,
        'firmwareRebuilt':False,'liveRomStillRelease3':True,'liveTrialUsesQualifiedTemporaryHelper':True,'log':str(log)}
(out/'package-build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
