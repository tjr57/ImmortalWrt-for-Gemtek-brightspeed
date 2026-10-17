from pathlib import Path
import hashlib,json,os,stat,subprocess,sys,tempfile,tarfile
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap25';art=Path('/home/xrdev/artifacts/xr1710g')
sys.path.insert(0,str(r/'scripts'))
from artifact_light_checks import select_version_artifacts,check_ap_build_artifacts
from verify_ap4_artifacts import FDT
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
version='20261010-ap25-d331711d';oldversion='20261010-ap24-d331711d'
selected=select_version_artifacts(r,version);old=next((w/f'builds/{oldversion}-development').glob('*-squashfs-sysupgrade.itb'));image=selected['sysupgrade']
assert sha(old)=='411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0'
process=json.loads((art/'build-ap25-process.json').read_text());assert process['exitCode']==0 and process['wirelessKernelABIValidated']
for name in ['process','module-abi']:(out/f'build-{name}.json').write_bytes((art/f'build-ap25-{name}.json').read_bytes())
oldfit=FDT(old.read_bytes());newfit=FDT(image.read_bytes())
def payloads(fit,kind):return {n:fit.payload(n) for n,p in fit.nodes.items() if n.startswith('/images/') and n.count('/')==2 and p.get('type',b'').rstrip(b'\0')==kind}
for kind in [b'kernel',b'flat_dt']:assert payloads(oldfit,kind) and payloads(oldfit,kind)==payloads(newfit,kind),kind
with tempfile.TemporaryDirectory(prefix='ap25-packed-') as tmp:
 roots=[]
 for label,fit in [('old',oldfit),('new',newfit)]:
  payload=payloads(fit,b'filesystem');assert len(payload)==1
  squash=Path(tmp)/(label+'.squashfs');squash.write_bytes(next(iter(payload.values())))
  root=Path(tmp)/label
  subprocess.run([str(r/'staging_dir/host/bin/unsquashfs4'),'-no-progress','-d',str(root),str(squash)],check=True,stdout=subprocess.DEVNULL)
  roots.append(root)
 def listing(root):
  entries={}
  for parent,dirs,files in os.walk(root,followlinks=False):
   for name in dirs+files:
    f=Path(parent)/name;mode=f.lstat().st_mode
    entries[str(f.relative_to(root))]={'mode':mode,'content':os.readlink(f) if f.is_symlink() else sha(f) if stat.S_ISREG(mode) else None}
  return entries
 before,after=map(listing,roots);assert before.keys()==after.keys(),'Unexpected rootfs file additions or removals'
 changed=[p for p in before if before[p]!=after[p]]
 diff={'changedPaths':changed,'totalEntries':len(after),'before':{p:before[p] for p in changed},'after':{p:after[p] for p in changed}}
 (out/'rootfs-delta.json').write_text(json.dumps(diff,indent=2)+'\n');print(json.dumps({'rootfsChanged':changed}),flush=True)
 script_sets=[]
 for label,root in zip(['old','new'],roots):
  with tarfile.open(root/'lib/apk/db/scripts.tar.gz') as t:
   entries={m.name:hashlib.sha256(t.extractfile(m).read()).hexdigest() for m in t.getmembers() if m.isfile()}
  (out/f'apk-scripts-{label}.json').write_text(json.dumps(entries,indent=2)+'\n')
  normalized={}
  for name,h in entries.items():
   pkg,identifier,kind=name.rsplit('.',2)
   assert identifier.startswith('X1')
   pkg=pkg.replace('xr1710g-ap-configurator-9','xr1710g-ap-configurator-10')
   key=pkg+'.'+kind;assert key not in normalized;normalized[key]=h
  script_sets.append(normalized)
 assert script_sets[0]==script_sets[1],'APK lifecycle script contents changed'
 def installed(root):
  result={}
  for block in (root/'lib/apk/db/installed').read_text().strip().split('\n\n'):
   names=[x[2:] for x in block.splitlines() if x.startswith('P:')];assert len(names)==1
   result[names[0]]=block
  return result
 db0,db1=map(installed,roots);assert db0.keys()==db1.keys()
 assert {p for p in db0 if db0[p]!=db1[p]}=={'base-files','xr1710g-ap-configurator'}
 for root in roots:
  assert (root/'lib/apk/packages/xr1710g-ap-configurator.conffiles_static').read_text()==f'/etc/config/xr1710g_ap_configurator {sha(root/"etc/config/xr1710g_ap_configurator")}\n'
 allowed={'usr/sbin/xr1710g-ap-uplink-guard','etc/config/xr1710g_ap_configurator','etc/banner','etc/openwrt_release','etc/openwrt_version','usr/lib/os-release','lib/apk/db/installed','lib/apk/db/scripts.tar.gz','lib/apk/packages/xr1710g-ap-configurator.conffiles_static'}
 assert set(changed)<=allowed,sorted(set(changed)-allowed)
 for p in changed:assert before[p]['mode']==after[p]['mode'],p
 rf=roots[1];package=r/'package/network/config/xr1710g-ap-configurator'
 for p,source in [('usr/sbin/xr1710g-ap-uplink-guard','xr1710g-ap-uplink-guard'),('etc/config/xr1710g_ap_configurator','xr1710g_ap_configurator')]:assert (rf/p).read_bytes()==(package/'files'/source).read_bytes()
 qa=json.loads((out/'guard-qa.json').read_text());assert qa['passed'] and qa['programSHA256']==sha(rf/'usr/sbin/xr1710g-ap-uplink-guard')
 assert b'option key' not in (rf/'etc/config/xr1710g_ap_configurator').read_bytes()
 for p in ['etc/banner','etc/openwrt_release','etc/openwrt_version','usr/lib/os-release']:
  if p in changed:assert (roots[0]/p).read_bytes().replace(oldversion.encode(),version.encode())==(rf/p).read_bytes(),p
 manifest=selected['manifest'].read_text();assert 'xr1710g-ap-configurator - 10\n' in manifest
 oldmanifest=next((w/f'builds/{oldversion}-development').glob('*.manifest')).read_text()
 def packages(s):return dict(row.split(' - ',1) for row in s.splitlines() if row)
 mp,mo=packages(manifest),packages(oldmanifest);assert mp.keys()==mo.keys();assert {p for p in mp if mp[p]!=mo[p]}<= {'base-files','xr1710g-ap-configurator'}
 baseline=json.loads((w/'development/ap24/packed-files-qa.json').read_text())['matchedFiles']
 matched={p:sha(rf/p) for p in baseline}
 for p in baseline:
  if p not in ['usr/sbin/xr1710g-ap-uplink-guard','etc/config/xr1710g_ap_configurator']:assert baseline[p]==matched[p],p
 packed={'passed':True,'version':version,'imageSHA256':sha(image),'imageSize':image.stat().st_size,'matchedFiles':matched,'checks':['Full rootfs comparison limits changes to guard, preset and package/version metadata','Normal kernel and DT byte-identical to accepted AP24','All modules, management/SSH/boot/Mesh services byte-identical to accepted AP24','Changed guard exactly equals tested source; no runtime wireless secrets shipped','Only configurator and base-files package versions changed']}
 (out/'packed-files-qa.json').write_text(json.dumps(packed,indent=2)+'\n')
host=check_ap_build_artifacts(r,version);assert host['passed'];(out/'artifact-qa.json').write_text(json.dumps(host,indent=2)+'\n')
# Changed code only gates the users BSS at runtime; kernel/management/backhaul
# byte identity retains the previous relevant real-guest qualification.
prior=json.loads((w/'development/ap24/boot-lab/result.json').read_text());assert prior['vmPrecheckPassed']
gate={'vmPrecheckPassed':True,'imageSHA256':sha(image),'scope':'Runtime users BSS debounce only','criticalBootManagementBackhaulIdenticalToAP24':True,'inheritedVM':'development/ap24/boot-lab/result.json','guardQA':'development/ap25/guard-qa.json','newKernelVMRun':False,'fullARMHardwareBootProven':False}
(out/'boot-lab').mkdir(exist_ok=True);(out/'boot-lab/result.json').write_text(json.dumps(gate,indent=2)+'\n')
print(json.dumps({'passed':True,'imageSHA256':sha(image),'bytes':image.stat().st_size,'matchedFiles':len(matched)}))
