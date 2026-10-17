"""Frozen AP24 plus previously qualified producer instrumentation and recovery.

Only a private diagnostic FIT is assembled. Production sources/images are not
changed, and no router is contacted. Root preserves squashfs metadata only.
"""
from pathlib import Path
from datetime import datetime
import os,stat,shutil,json,hashlib,subprocess,struct,zlib,fcntl,importlib.util
W=Path('/mnt/d/ChatGPT/XR1710G');R=Path('/home/xrdev/projects/xr1710g/openwrt')
OUT=W/'development/ap24/owner-trace';OUT.mkdir(exist_ok=True)
ID='ap24-npu-owner-trace1';STAMP=datetime.now().strftime('%Y%m%d-%H%M%S')
LAB=Path('/home/xrdev/projects/xr1710g/boot-lab')/(ID+'-'+STAMP)
HOST=R/'staging_dir/host/bin';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
j=lambda p:json.loads(Path(p).read_text())
spec=importlib.util.spec_from_file_location('fithelpers',W/'environment/build-npu-diagnostic-lab.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
assert os.geteuid()==0 and not (OUT/'result.json').exists()
lock=Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
base=next((W/'builds/20261010-ap24-d331711d-development').glob('*-squashfs-sysupgrade.itb'))
BASE='411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0'
assert sha(base)==BASE
assert j(W/'development/ap24/boot-lab/result.json')['imageSHA256']==BASE
assert j(W/'development/ap24/ownership-compiled-qa.json')['passed']
prior=j(W/'development/npu-diagnostic-lab/result.json');old=Path(prior['artifact'])
assert sha(old)==prior['artifactSHA256']=='dfea625f373ba0fe5eac253b7c8f9535db26da5db344580d0ba019845350f76c'
assert j(W/'development/npu-ap1-debugfs/live-epoch-1/result.json')['ordinaryRecoveryAndCleanupPassed']
assert j(W/'development/npu-ap2-debugfs/live-epoch-2/result.json')['ordinaryRecoveryAndCleanupPassed']
assert j(W/'development/ap24/npu-ap1-epoch1/analysis.json')['faultObserved'] is False
protected={str(p):sha(p) for p in (base,old,R/'.config',R/'xr1710g-ap.config',R/'target/linux/airoha/an7581/firmware/airoha/en7581_MT7996_npu_rv32.bin')}
# Old ordinary build/module state differs intentionally in AP24. Kernel ABI
# contracts are unchanged, and the new module has its own source-bound VM gate.
for path,h in prior['productionInputsUnchanged'].items():
 if '/linux-6.18.54/' in path:assert sha(path)==h;protected[path]=h
bindings={}
for name,count,key in [('npu-recovery5',18,'src/recovery.c'),('npu-activation3',19,'src/activate.c')]:
 p=W/'development'/name;pkg=j(p/'package-build.json');vm=j(p/'vm/result-latest.json')
 assert pkg['passed'] and vm['passed'] and len(vm['cases'])==count
 for rel,h in pkg['sourceHashes'].items():assert sha(p/rel)==h
 for case in vm['cases']:
  assert case['sourceSHA256']==pkg['sourceHashes'][key]
  assert case['producerReaderSHA256']==sha(W/'development/npu-producer-reader/src/xr_npu_producer.c')
 bindings[name]={'VMReportSHA256':sha(p/'vm/result-latest.json'),'cases':count,'nativeSourceSHA256':pkg['sourceHashes'][key]}
for unit in (1,2):
 p=W/f'development/npu-ap{unit}-debugfs';vm=j(p/'activation/vm/result-latest.json');arm=j(p/'activation/shipped-shell-qa.json')
 assert vm['passed'] and len(vm['cases'])==3 and arm['passed'] and len(arm['checks'])==23
 for case in vm['cases']:
  assert case['sourceSHA256']==sha(p/'activation/src/activate.c')==sha(W/'development/npu-activation3/src/activate.c')
  assert case['guardSHA256']==sha(p/'recovery/src/recovery.c')==sha(W/'development/npu-recovery5/src/recovery.c')
  assert case['helperSHA256']==sha(p/'activation/files/xr-npu-guarded-once')==arm['helperSHA256']
 bindings[f'AP{unit}earlyDebugfs']={'VMReportSHA256':sha(p/'activation/vm/result-latest.json'),'realKernelCases':3,'ARMChecks':23,'helperSHA256':arm['helperSHA256']}
for folder in ('npu-producer-reader','npu-address-diag'):
 p=W/'development'/folder;vm=j(p/'vm/result-latest.json');arm=j(p/'arm/result-latest.json')
 assert vm['passed'] and arm['passed'];bindings[folder]={'VMReportSHA256':sha(p/'vm/result-latest.json'),'ARMReportSHA256':sha(p/'arm/result-latest.json')}
LAB.mkdir();log=(OUT/'assembly.log').open('w')
def run(args,**kw):
 result=subprocess.run([str(x) for x in args],stdout=log,stderr=subprocess.STDOUT,**kw);log.flush();assert result.returncode==0,args
fit=f.FDT(base.read_bytes());squash=LAB/'base.squashfs';squash.write_bytes(f.raw_payload(fit,'/images/rootfs-1'))
root=LAB/'root';run([HOST/'unsquashfs4','-no-progress','-processors','12','-d',root,squash]);before=f.inventory(root)
oldsq=LAB/'old-diag.squashfs';oldsq.write_bytes(f.raw_payload(f.FDT(old.read_bytes()),'/images/rootfs-1'))
oldroot=LAB/'old';run([HOST/'unsquashfs4','-no-progress','-processors','12','-d',oldroot,oldsq])
# Every reused file is tied to the immutable previously tested FIT, including
# exact compiled actors/readers and unchanged RISC-V hook. No package rebuild.
for rel,entry in prior['changedFiles'].items():
 if 'sha256' in entry:assert sha(oldroot/rel)==entry['sha256']
 else:assert os.readlink(oldroot/rel)==entry['target']
installed={}
for rel,entry in prior['changedFiles'].items():
 if rel in ('etc/banner','etc/xr1710g-diagnostic.json'):continue
 src,dst=oldroot/rel,root/rel
 dst.parent.mkdir(parents=True,exist_ok=True)
 if src.is_symlink():
  assert not dst.exists() and not dst.is_symlink();dst.symlink_to(os.readlink(src))
 else:
  if dst.exists():assert rel=='lib/firmware/airoha/en7581_MT7996_npu_rv32.bin'
  shutil.copy2(src,dst);os.chown(dst,0,0);installed[rel]=sha(dst)
helper=W/'development/npu-ap1-debugfs/activation/files/xr-npu-guarded-once'
shutil.copyfile(helper,root/'usr/libexec/xr-npu-guarded-once');installed['usr/libexec/xr-npu-guarded-once']=sha(helper)
marker={'schema':1,'id':ID,'baseImageSHA256':BASE,'candidateFirmwareSHA256':installed['lib/firmware/airoha/en7581_MT7996_npu_rv32.bin'],
 'defaultMt76NpuActivation':False,'ownerAcceptedRemoteLoss':True,'historicalRootProven':False,
 'purpose':'Observe fixed host-driver ownership with the same producer hook used before the fix','diagnosticPayloadsOutsideApkDatabase':True}
(root/'etc/xr1710g-diagnostic.json').write_text(json.dumps(marker,indent=2)+'\n')
with (root/'etc/banner').open('a') as b:b.write('\nDiagnostic: '+ID+'; opt-in NPU trial, original AP24 retained locally.\n')
after=f.inventory(root);changed={p:after.get(p) for p in set(before)|set(after) if before.get(p)!=after.get(p)}
assert set(changed)==set(prior['changedFiles'])
for path in ('etc/xr-npu-guarded.once','etc/xr-recovery.once','etc/xr-kmsg-capture.once','root/xr-diag-journal'):assert path not in after
assert all(before[p]==after[p] for p in before if p.startswith(('lib/modules/','lib/apk/','etc/config/','etc/openwrt_')))
packed=j(W/'development/ap24/packed-files-qa.json')['matchedFiles']
assert all(sha(root/p)==h for p,h in packed.items())
new_sq=LAB/'root.squashfs';epoch=str(struct.unpack_from('<I',squash.read_bytes(),8)[0])
run([HOST/'mksquashfs4',root,new_sq,'-noappend','-no-progress','-processors','12','-comp','xz','-b','256k','-no-xattrs','-Xpreset','9','-Xe','-Xlc','0','-Xlp','2','-Xpb','2','-mkfs-time',epoch])
roundtrip=LAB/'roundtrip';run([HOST/'unsquashfs4','-no-progress','-processors','12','-d',roundtrip,new_sq]);assert f.inventory(roundtrip)==after
data=new_sq.read_bytes();(LAB/'root.squashfs.pagesync').write_bytes(data+bytes((-len(data))%4096))
kernel,dtb=LAB/'kernel.gz',LAB/'board.dtb';kernel.write_bytes(f.raw_payload(fit,'/images/kernel-1'));dtb.write_bytes(f.raw_payload(fit,'/images/fdt-1'))
its=LAB/'image.its';artifact=OUT/(ID+'-sysupgrade.itb')
run([R/'scripts/mkits.sh','-D','gemtek_xr1710g','-o',its,'-k',kernel,'-C',fit.string('/images/kernel-1','compression'),'-d',dtb,'-r',new_sq,'-a',hex(fit.uint('/images/kernel-1','load')),'-e',hex(fit.uint('/images/kernel-1','entry')),'-c','config-1','-A','arm64','-v','6.18.54'])
env=dict(os.environ,SOURCE_DATE_EPOCH=epoch);env['PATH']=str(HOST)+os.pathsep+env['PATH']
run([HOST/'mkimage','-E','-B','0x1000','-p','0x1000','-f',its,artifact],env=env)
new=f.FDT(artifact.read_bytes());payloads={}
for name in ('kernel-1','fdt-1','rootfs-1'):
 payload=f.raw_payload(new,'/images/'+name);payloads[name]=hashlib.sha256(payload).hexdigest()
 for suf in ('hash-1','hash-2'):
  node='/images/'+name+'/'+suf;algo=new.string(node,'algo');value=struct.pack('>I',zlib.crc32(payload)) if algo=='crc32' else hashlib.new(algo,payload).digest();assert new.nodes[node]['value']==value
 if name!='rootfs-1':assert payload==f.raw_payload(fit,'/images/'+name)
assert new.nodes['/configurations/config-1']==fit.nodes['/configurations/config-1']
run([HOST/'fwtool','-i',OUT/'base-metadata.json',base]);metadata=j(OUT/'base-metadata.json');assert metadata['supported_devices']==['gemtek,xr1710g'] and metadata['compat_version']=='1.0'
metadata['xr_diagnostic']={'id':ID,'baseImageSHA256':BASE,'targetFirst':'ap2','ownerAcceptedLossOfRemoteAccess':True,'rootCauseProven':False}
(OUT/'metadata.json').write_text(json.dumps(metadata,separators=(',',':'))+'\n');raw=artifact.read_bytes()
run([HOST/'fwtool','-I',OUT/'metadata.json',artifact]);run([HOST/'fwtool','-i',OUT/'metadata-roundtrip.json',artifact]);assert j(OUT/'metadata-roundtrip.json')==metadata
assert subprocess.check_output([HOST/'fwtool','-i','/dev/null','-T',artifact])==raw
assert all(sha(p)==h for p,h in protected.items())
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'id':ID,'baseImageSHA256':BASE,
 'artifact':str(artifact),'artifactSHA256':sha(artifact),'artifactBytes':artifact.stat().st_size,
 'changedFiles':changed,'sourceBoundVM':bindings,'productionInputsUnchanged':protected,
 'productionKernelAndDtbByteIdentical':True,'productionModulesByteIdentical':True,'AP24PackedFilesMatched':len(packed),
 'fullMakeWorldRun':False,'reason':'Reuses exact previously compiled and guest-qualified binary payloads; AP24 already built -j12',
 'rootfsFilesVerified':len(after),'sourceRoot':str(root),'roundTripRoot':str(roundtrip),'FITPayloadHashes':payloads,
 'squashfsRoundTripPassed':True,'startupRequestsAbsent':True,'upgradeMetadataIncluded':True,
 'ownerAcceptedRemoteLoss':True,'NpuEnabledByDefault':False,'historicalRootProven':False,
 'remaining':['actual packed startup QA','AP2 first deployment then AP1','post-fix producer ownership samples','restore uninstrumented AP24']}
(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('passed','artifactSHA256','artifactBytes','AP24PackedFilesMatched','rootfsFilesVerified')}))
