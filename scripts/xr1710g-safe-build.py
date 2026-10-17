#!/usr/bin/env python3
"""Serialize AP builds, rebuild external WLAN modules after kernel contract changes."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,fcntl,hashlib,json,re,subprocess,sys,shutil

def timestamp():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def module_config_digest(path):
 # OpenWrt builds normal and initramfs kernels in one run. Their root-image
 # settings and textual ordering differ without changing module contracts.
 settings={}
 for line in path.read_text().splitlines():
  enabled=re.fullmatch(r'(CONFIG_[A-Z0-9_]+)=(.*)',line)
  disabled=re.fullmatch(r'# (CONFIG_[A-Z0-9_]+) is not set',line)
  if enabled:key,value=enabled.groups()
  elif disabled:key,value=disabled[1],'n'
  else:continue
  if key=='CONFIG_BLK_DEV_INITRD' or key.startswith(('CONFIG_INITRAMFS_','CONFIG_RD_')):continue
  settings[key]=value
 return hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
def active_kernel_tree(root):
 details=(root/'target/linux/generic/kernel-6.18').read_text()
 match=re.search(r'^LINUX_VERSION-6\.18\s*=\s*(\.\d+)\s*$',details,re.M)
 if not match:raise ValueError('Cannot resolve configured 6.18 kernel')
 kernel=root/('build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18'+match[1])
 if not (kernel/'.config').is_file():raise ValueError('Configured kernel tree missing: '+str(kernel))
 return kernel

def main():
 parser=argparse.ArgumentParser();parser.add_argument('name');parser.add_argument('--verbose',action='store_true');parser.add_argument('--root',type=Path,required=True);parser.add_argument('--artifacts',type=Path,required=True);args=parser.parse_args()
 assert re.fullmatch(r'ap[0-9]+',args.name)
 root=args.root.resolve();artifacts=args.artifacts.resolve();assert (root/'target/linux/airoha/an7581').is_dir() and artifacts.is_dir()
 version=re.search(r'^CONFIG_VERSION_NUMBER="([^"]+)"$',(root/'.config').read_text(),re.M);assert version and '-'+args.name+'-' in version[1]
 lock=(artifacts/'build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 result={'startedAt':timestamp(),'command':['make','world','-j16'],'jobs':16,'version':version[1],'source':str(root),'steps':[],'exitCode':1}
 state_path=artifacts/'ap-kernel-contract.json'
 previous=json.loads(state_path.read_text()) if state_path.exists() else None
 try:
  with (artifacts/f'build-{args.name}.log').open('w') as log:
   def run(command):
    if args.verbose and command[0]=='make':command=command+['V=s']
    code=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT).returncode
    result['steps'].append({'command':command,'exitCode':code});assert code==0,command
   # Finalize the actual kernel config before external package stamp checks.
   run(['make','target/linux/compile','-j16'])
   k=active_kernel_tree(root);result['selectedKernel']=str(k)
   inputs=[k/'Module.symvers',k/'include/linux/netdevice.h',k/'include/linux/skbuff.h',k/'include/linux/ieee80211.h']
   # The NPU/WLAN ABI lives in airoha_offload.h (its name has no "npu").
   # Changes to core layout shift the ops table used by external mt76.
   offload_header=k/'include/linux/soc/airoha/airoha_offload.h'
   assert offload_header.is_file()
   inputs.append(offload_header)
   inputs+=list((k/'include').glob('**/*airoha*npu*.h'))
   contract={str(p.relative_to(k)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
   contract['kernelModuleConfig']=module_config_digest(k/'.config')
   contract['kernelRelease']=k.name.removeprefix('linux-')
   digest=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest();result['kernelContractSHA256']=digest
   rebuild=previous is None or previous.get('contractSHA256')!=digest;result['externalWlanRebuildRequired']=rebuild
   if rebuild:
    # Package targets remove only generated package objects, never source/feeds.
    run(['make','package/kernel/mt76/clean'])
    run(['make','package/kernel/mac80211/clean'])
   run(['make','world','-j16'])
   assert module_config_digest(k/'.config')==contract['kernelModuleConfig'],'Kernel module config changed after external rebuild decision'
   proof=artifacts/f'build-{args.name}-module-abi.json'
   run([sys.executable,str(root/'scripts/xr1710g-module-abi.py'),'--root',str(root),'--report',str(proof)])
   validated=json.loads(proof.read_text());assert validated['passed'];result['wirelessKernelABIValidated']=True
   # Failed builds never publish a reusable contract marker.
   temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps({'version':version[1],'contractSHA256':digest,'inputs':contract,'validatedAt':timestamp()},indent=2)+'\n');temp.replace(state_path)
   result['exitCode']=0
 except Exception as error:
  result['failureType']=type(error).__name__;result['failure']=str(error)
 finally:
  result['completedAt']=timestamp()
  serialized=json.dumps(result,indent=2)+'\n'
  history=artifacts/f'build-{args.name}-history';history.mkdir(exist_ok=True)
  identity=re.sub(r'[^0-9T]','',result['startedAt'])
  record=history/(identity+'-process.json');assert not record.exists();record.write_text(serialized)
  logfile=artifacts/f'build-{args.name}.log'
  if logfile.exists():shutil.copy2(logfile,history/(identity+'.log'))
  (artifacts/f'build-{args.name}-process.json').write_text(serialized);print(json.dumps(result),flush=True)
 return result['exitCode']
if __name__=='__main__':raise SystemExit(main())
