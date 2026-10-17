"""Add the observed management-PN-then-EHT-data ordering to existing fixtures."""
from pathlib import Path
import subprocess,hashlib,json,os
r=Path('/home/xrdev/projects/xr1710g/openwrt');base=Path('/mnt/d/ChatGPT/XR1710G/development/ap30');out=base/'eht-header/live-pattern';out.mkdir(exist_ok=True)
prior=json.loads((base/'eht-header/qa/result.json').read_text());assert prior['passed']
source=(base/'eht-header/qa/test.c').read_text();anchor=' for(int he=0;he<2;he++)'
assert source.count(anchor)==1
extra=r'''
 /* Live record: previous accepted seq0 (non-QoS management), current QoS
  * data seq908, delta-1. Populate the correct TID counters independently. */
 for(int tid=0;tid<16;tid++){
  struct mt76_wcid old={.rx_check_pn=true},fixed=old;
  for(int i=0;i<17;i++){pn(old.rx_key_pn[i],99);pn(fixed.rx_key_pn[i],99);}
  packet(&x,a,&old,0x40d0,0,101,false);packet(&y,b,&fixed,0x40d0,0,101,false);
  old_check(&x,true);new_check(&y,true);
  assert(!(x.cb->flag&RX_FLAG_ONLY_MONITOR)&&!(y.cb->flag&RX_FLAG_ONLY_MONITOR));
  packet(&x,a,&old,0x4388,tid,100,true);packet(&y,b,&fixed,0x4388,tid,100,true);
  ((struct ieee80211_hdr *)x.mac_header)->seq_ctrl=908<<4;((struct ieee80211_hdr *)y.mac_header)->seq_ctrl=908<<4;
  old_check(&x,true);new_check(&y,true);
  assert(x.cb->flag&RX_FLAG_ONLY_MONITOR);assert(!(y.cb->flag&RX_FLAG_ONLY_MONITOR));
  assert(value(fixed.rx_key_pn[16])==101&&value(fixed.rx_key_pn[tid])==100);
  packet(&y,b,&fixed,0x40d0,0,101,false);new_check(&y,true);assert(y.cb->flag&RX_FLAG_ONLY_MONITOR);
  cases++;
 }
'''
source=source.replace(anchor,extra+anchor).replace('240 cross-TID false-replay negative controls;', '240 cross-TID plus16 observed management-before-EHT-data negative controls;')
(out/'test.c').write_text(source)
args=['-std=gnu11','-O1','-g','-Wall','-Wextra',str(out/'test.c')];cc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc'
commands=[['gcc',*args,'-fsanitize=address,undefined','-o',str(out/'native')],[str(out/'native')],[str(cc),*args,'-static','-o',str(out/'arm')],['qemu-aarch64',str(out/'arm')]];logs=[]
for cmd in commands:
 p=subprocess.run(cmd,capture_output=True,text=True,env=dict(os.environ,STAGING_DIR=str(r/'staging_dir')));logs.append({'command':cmd,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert p.returncode==0,p.stdout+p.stderr
(out/'result.json').write_text(json.dumps({'passed':True,'unchangedCandidateHeaderSHA256':prior['headerSHA256'],'cases':512,'additionalManagementThenDataCases':16,'sourceSHA256':hashlib.sha256((out/'test.c').read_bytes()).hexdigest(),'tests':logs,'limits':'Models observed scalar ordering with generated frame headers, not captured radio payload'},indent=2)+'\n');print(logs[-1]['stdout'])
