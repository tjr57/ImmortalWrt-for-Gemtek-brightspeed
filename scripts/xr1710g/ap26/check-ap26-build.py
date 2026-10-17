from pathlib import Path
import hashlib,json,os,stat,subprocess,sys,tempfile,tarfile,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap26';art=Path('/home/xrdev/artifacts/xr1710g')
sys.path.insert(0,str(r/'scripts'))
from artifact_light_checks import select_version_artifacts,check_ap_build_artifacts
from verify_ap4_artifacts import FDT
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
version='20261010-ap26-d331711d';oldversion='20261010-ap25-d331711d'
selected=select_version_artifacts(r,version);old=next((w/f'builds/{oldversion}-development').glob('*-squashfs-sysupgrade.itb'));image=selected['sysupgrade']
assert sha(old)=='4ccc14e251b6175c7d3fa71567a52204cc6a7480aa5c4f8db1928ce6a9ea7e9a'
process=json.loads((art/'build-ap26-process.json').read_text());assert process['exitCode']==0 and process['wirelessKernelABIValidated']
for name in ['process','module-abi']:(out/f'build-{name}.json').write_bytes((art/f'build-ap26-{name}.json').read_bytes())
oldfit=FDT(old.read_bytes());newfit=FDT(image.read_bytes())
def payloads(fit,kind):return {n:fit.payload(n) for n,p in fit.nodes.items() if n.startswith('/images/') and n.count('/')==2 and p.get('type',b'').rstrip(b'\0')==kind}
for kind in [b'kernel',b'flat_dt']:assert payloads(oldfit,kind) and payloads(oldfit,kind)==payloads(newfit,kind)
with tempfile.TemporaryDirectory(prefix='ap26-packed-') as tmp:
 roots=[]
 for label,fit in [('old',oldfit),('new',newfit)]:
  payload=payloads(fit,b'filesystem');assert len(payload)==1
  squash=Path(tmp)/(label+'.squashfs');squash.write_bytes(next(iter(payload.values())))
  root=Path(tmp)/label;subprocess.run([str(r/'staging_dir/host/bin/unsquashfs4'),'-no-progress','-d',str(root),str(squash)],check=True,stdout=subprocess.DEVNULL);roots.append(root)
 def listing(root):
  entries={}
  for parent,dirs,files in os.walk(root,followlinks=False):
   for name in dirs+files:
    f=Path(parent)/name;mode=f.lstat().st_mode
    entries[str(f.relative_to(root))]={'mode':mode,'content':os.readlink(f) if f.is_symlink() else sha(f) if stat.S_ISREG(mode) else None}
  return entries
 before,after=map(listing,roots);assert before.keys()==after.keys()
 changed=[p for p in before if before[p]!=after[p]]
 (out/'rootfs-delta.json').write_text(json.dumps({'changedPaths':changed,'totalEntries':len(after),'before':{p:before[p] for p in changed},'after':{p:after[p] for p in changed}},indent=2)+'\n')
 print(json.dumps({'changedPaths':changed}),flush=True)
 allowed={'usr/libexec/rpcd/luci.airoha_npu','www/luci-static/resources/view/airoha_npu/status.js','usr/lib/lua/luci/i18n/luci-app-airoha-npu.zh-cn.lmo',
          'etc/banner','etc/openwrt_release','etc/openwrt_version','usr/lib/os-release','lib/apk/db/installed','lib/apk/db/scripts.tar.gz'}
 assert set(changed)<=allowed, sorted(set(changed)-allowed)
 for p in changed:assert before[p]['mode']==after[p]['mode']
 scripts=[]
 for label,root in zip(['old','new'],roots):
  with tarfile.open(root/'lib/apk/db/scripts.tar.gz') as t:entries={m.name:hashlib.sha256(t.extractfile(m).read()).hexdigest() for m in t.getmembers() if m.isfile()}
  (out/f'apk-scripts-{label}.json').write_text(json.dumps(entries,indent=2)+'\n')
  normalized={}
  for name,h in entries.items():
   pkg,identifier,kind=name.rsplit('.',2);assert identifier.startswith('X1')
   pkg=pkg.replace('luci-app-airoha-npu-2.0.0-r6','luci-app-airoha-npu-2.0.0-r7').replace('luci-app-airoha-npu-2.0.0-6','luci-app-airoha-npu-2.0.0-7')
   key=pkg+'.'+kind;assert key not in normalized;normalized[key]=h
  scripts.append(normalized)
 assert scripts[0]==scripts[1], 'Unexpected APK lifecycle script changes'
 def installed(root):
  result={}
  for block in (root/'lib/apk/db/installed').read_text().strip().split('\n\n'):
   names=[x[2:] for x in block.splitlines() if x.startswith('P:')];assert len(names)==1;result[names[0]]=block
  return result
 db0,db1=map(installed,roots);assert db0.keys()==db1.keys()
 packages_changed={p for p in db0 if db0[p]!=db1[p]}
 assert packages_changed<= {'base-files','luci-app-airoha-npu','luci-i18n-airoha-npu-zh-cn'},packages_changed
 rf=roots[1];app=r/'feeds/app_airoha/luci-app-airoha-npu'
 paths={'usr/libexec/rpcd/luci.airoha_npu':('root/usr/libexec/rpcd/luci.airoha_npu','rpc-qa.json','programSHA256'),
        'www/luci-static/resources/view/airoha_npu/status.js':('htdocs/luci-static/resources/view/airoha_npu/status.js','ui-qa.json','sourceSHA256')}
 for dest,(src,qa,key) in paths.items():
  proof=json.loads((out/qa).read_text());assert proof['passed'] and proof[key]==sha(app/src)
  if dest.endswith('.js'):
   minifiers=list(r.glob('staging_dir/*/bin/jsmin'));assert len(minifiers)==1
   minimized=subprocess.run([str(minifiers[0])],input=(app/src).read_bytes(),capture_output=True,check=True).stdout
   assert minimized==(rf/dest).read_bytes()
   packed_ui=json.loads((out/'ui-packed-qa.json').read_text());assert packed_ui['passed'] and packed_ui['sourceSHA256']==sha(rf/dest)
  else:assert (rf/dest).read_bytes()==(app/src).read_bytes()
 for p in ['etc/banner','etc/openwrt_release','etc/openwrt_version','usr/lib/os-release']:
  assert (roots[0]/p).read_bytes().replace(oldversion.encode(),version.encode())==(rf/p).read_bytes()
 baseline=json.loads((w/'development/ap25/packed-files-qa.json').read_text())['matchedFiles']
 matched={p:sha(rf/p) for p in baseline}
 for p in baseline:
  if p not in paths and p!='usr/lib/lua/luci/i18n/luci-app-airoha-npu.zh-cn.lmo':assert baseline[p]==matched[p],p
 for p in paths:matched[p]=sha(rf/p)
 lmo='usr/lib/lua/luci/i18n/luci-app-airoha-npu.zh-cn.lmo';matched[lmo]=sha(rf/lmo)
 packed={'passed':True,'version':version,'imageSHA256':sha(image),'imageSize':image.stat().st_size,'matchedFiles':matched,
 'checks':['Full rootfs delta limited to NPU RPC/UI/Chinese catalog and package/version metadata','Kernel and DT byte-identical to accepted AP25','Boot, SSH, Mesh, drivers, user BSS guard and configuration defaults unchanged','Packed RPC equals tested source; packed UI equals host jsmin output and its actual functions pass seven modes','APK lifecycle contents unchanged','Only base-files/NPU app/Chinese catalog package records changed']}
 (out/'packed-files-qa.json').write_text(json.dumps(packed,indent=2)+'\n')
host=check_ap_build_artifacts(r,version);assert host['passed'];(out/'artifact-qa.json').write_text(json.dumps(host,indent=2)+'\n')
prior=json.loads((w/'development/ap25/boot-lab/result.json').read_text());assert prior['vmPrecheckPassed']
gate={'vmPrecheckPassed':True,'imageSHA256':sha(image),'criticalBootManagementBackhaulIdenticalToAP25':True,
 'inheritedVM':'development/ap25/boot-lab/result.json','scope':'Runtime NPU RPC and UI only','newKernelVMRun':False,'fullARMHardwareBootProven':False}
(out/'boot-lab').mkdir(exist_ok=True);(out/'boot-lab/result.json').write_text(json.dumps(gate,indent=2)+'\n')
qa=art/'qa/latest-result.json';assert json.loads(qa.read_text())['passed'];shutil.copy2(qa,out/'defaults-qa.json')
print(json.dumps({'passed':True,'imageSHA256':sha(image),'bytes':image.stat().st_size,'matchedFiles':len(matched)}))
