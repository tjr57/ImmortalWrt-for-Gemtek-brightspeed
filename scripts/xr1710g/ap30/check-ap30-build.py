from pathlib import Path
import hashlib,json,os,stat,subprocess,sys,tempfile,tarfile,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap30';art=Path('/home/xrdev/artifacts/xr1710g')
sys.path.insert(0,str(r/'scripts'))
from artifact_light_checks import select_version_artifacts,check_ap_build_artifacts
from verify_ap4_artifacts import FDT
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
version='20261010-ap30-d331711d';oldversion='20261010-ap29-d331711d'
selected=select_version_artifacts(r,version);image=selected['sysupgrade'];old=next((w/f'builds/{oldversion}-development').glob('*-squashfs-sysupgrade.itb'))
assert sha(old)=='5cfb7ac8f7b30359bc9be84bfc115f5ab7336ae9568c5d0afe45be1ee918871f'
process=json.loads((art/'build-ap30-process.json').read_text());assert process['exitCode']==0 and process['wirelessKernelABIValidated']
for n in ['process','module-abi']:(out/f'build-{n}.json').write_bytes((art/f'build-ap30-{n}.json').read_bytes())
def payloads(fit,kind):return {n:fit.payload(n) for n,p in fit.nodes.items() if n.startswith('/images/') and n.count('/')==2 and p.get('type',b'').rstrip(b'\0')==kind}
oldfit=FDT(old.read_bytes());newfit=FDT(image.read_bytes())
for kind in [b'kernel',b'flat_dt']:assert payloads(oldfit,kind) and payloads(oldfit,kind)==payloads(newfit,kind)
with tempfile.TemporaryDirectory(prefix='ap30-packed-') as tmp:
    roots=[]
    for label,fit in [('old',oldfit),('new',newfit)]:
        p=payloads(fit,b'filesystem');assert len(p)==1;sq=Path(tmp)/(label+'.squashfs');sq.write_bytes(next(iter(p.values())))
        root=Path(tmp)/label;subprocess.run([str(r/'staging_dir/host/bin/unsquashfs4'),'-no-progress','-d',str(root),str(sq)],check=True,stdout=subprocess.DEVNULL);roots.append(root)
    def listing(root):
        result={}
        for parent,dirs,files in os.walk(root,followlinks=False):
            for name in dirs+files:
                p=Path(parent)/name;mode=p.lstat().st_mode
                result[str(p.relative_to(root))]={'mode':mode,'content':os.readlink(p) if p.is_symlink() else sha(p) if stat.S_ISREG(mode) else None}
        return result
    before,after=map(listing,roots);assert before.keys()==after.keys(),{'added':sorted(after.keys()-before.keys()),'removed':sorted(before.keys()-after.keys())}
    changed=[p for p in before if before[p]!=after[p]]
    (out/'rootfs-delta.json').write_text(json.dumps({'changedPaths':changed,'totalEntries':len(after),'before':{p:before[p] for p in changed},'after':{p:after[p] for p in changed}},indent=2)+'\n');print(json.dumps({'changedPaths':changed}),flush=True)
    allowed={'lib/modules/6.18.54/mt76.ko','lib/modules/6.18.54/mt76-connac-lib.ko','lib/modules/6.18.54/mt7996e.ko','etc/banner','etc/openwrt_release','etc/openwrt_version','usr/lib/os-release','lib/apk/db/installed','lib/apk/db/scripts.tar.gz'}
    assert set(changed)<=allowed,sorted(set(changed)-allowed)
    for p in changed:assert before[p]['mode']==after[p]['mode']
    rf=roots[1]
    assert sha(rf/'bin/busybox')==json.loads((w/'development/ap27/ping-rxbuf/live-queue-qa.json').read_text())['binarySHA256']
    modules=json.loads((out/'eht-header/build.json').read_text())['moduleHashes'];verified={}
    for name,h in modules.items():
        raw=out/'eht-header'/name;assert sha(raw)==h
        stripped=Path(tmp)/('verified-'+name);shutil.copy2(raw,stripped)
        cross=str(r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-')
        subprocess.run(['sh',str(r/'scripts/strip-kmod.sh'),str(stripped)],env=dict(os.environ,CROSS=cross,NO_RENAME='1'),check=True)
        assert stripped.read_bytes()==(rf/'lib/modules/6.18.54'/name).read_bytes();verified[name]=sha(stripped)
    (out/'eht-header/packed-module-qa.json').write_text(json.dumps({'passed':True,'sourceModuleHashes':modules,'packedModuleHashes':verified},indent=2)+'\n')
    scripts=[]
    for root in roots:
        with tarfile.open(root/'lib/apk/db/scripts.tar.gz') as t:entries={m.name:hashlib.sha256(t.extractfile(m).read()).hexdigest() for m in t.getmembers() if m.isfile()}
        norm={}
        for name,h in entries.items():
            pkg,ident,kind=name.rsplit('.',2);assert ident.startswith('X1')
            # mt76 package revision only; lifecycle script bodies must match.
            if pkg.startswith(('kmod-mt76-', 'kmod-mt7996-', 'kmod-mt7996e-')):
                import re
                pkg=re.sub(r'-r?(15|16)$','',pkg)
            assert pkg+'.'+kind not in norm
            norm[pkg+'.'+kind]=h
        scripts.append(norm)
    if scripts[0]!=scripts[1]:
        (out/'apk-script-difference.json').write_text(json.dumps({'oldOnly':{k:v for k,v in scripts[0].items() if scripts[1].get(k)!=v},'newOnly':{k:v for k,v in scripts[1].items() if scripts[0].get(k)!=v}},indent=2)+'\n')
    assert scripts[0]==scripts[1],'APK lifecycle scripts changed'
    for p in ['etc/banner','etc/openwrt_release','etc/openwrt_version','usr/lib/os-release']:
        assert (roots[0]/p).read_bytes().replace(oldversion.encode(),version.encode())==(rf/p).read_bytes()
    baseline=json.loads((w/'development/ap29/packed-files-qa.json').read_text())['matchedFiles']
    matched={p:sha(rf/p) for p in baseline};matched['bin/busybox']=sha(rf/'bin/busybox')
    for p in baseline:
        if p not in {'lib/modules/6.18.54/'+n for n in modules}:assert matched[p]==baseline[p],p
    assert sha(rf/'bin/busybox')==json.loads((w/'development/ap27/busybox-arm-smoke.json').read_text())['candidateSHA256']
    packed={'passed':True,'version':version,'imageSHA256':sha(image),'imageSize':image.stat().st_size,'matchedFiles':matched,'checks':['Kernel and DT byte-identical to AP29','Full rootfs delta limited to affected mt76 modules and package/version metadata','Unchanged startup/SSH/Mesh scripts, firmware blob and mac80211 and configuration defaults','Packed BusyBox equals controlled live-tested candidate; packed driver modules equal qualified modules','BusyBox byte-identical to AP29 ARM/live-qualified binary','APK lifecycle contents unchanged']}
    (out/'packed-files-qa.json').write_text(json.dumps(packed,indent=2)+'\n')
host=check_ap_build_artifacts(r,version);assert host['passed'];(out/'artifact-qa.json').write_text(json.dumps(host,indent=2)+'\n')
p=subprocess.run(['python3',str(r/'scripts/test-xr1710g-ap-defaults.py')],capture_output=True,text=True,check=True);qa=json.loads(p.stdout);assert qa['passed'] and len(qa['checks'])==14
(out/'defaults-qa.json').write_text(json.dumps(qa,indent=2)+'\n')
(out/'boot-lab').mkdir(exist_ok=True)
gate={'preflashChecksPassed':True,'imageSHA256':sha(image),'kernelDTStartupManagementScriptsIdenticalToAP29':True,'newKernelVMRun':False,'fullARMHardwareBootProven':False,'homeModeAuthorized':True,'scope':'EHT saved MAC header fix;496 exact-source negative/positive regression cases;BusyBox and mac80211 unchanged; native sanitizer/ARM/ABI/packed image checks passed.'}
(out/'boot-lab/result.json').write_text(json.dumps(gate,indent=2)+'\n');print(json.dumps({'passed':True,'imageSHA256':sha(image),'bytes':image.stat().st_size,'matchedFiles':len(matched)}))
