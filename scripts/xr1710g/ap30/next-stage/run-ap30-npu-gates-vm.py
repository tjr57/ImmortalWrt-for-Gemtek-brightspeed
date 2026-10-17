"""Actual module loader + production activation/recovery; fake mt76 only in VM."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib,shutil,gzip,re,sys
w=Path('/mnt/d/ChatGPT/XR1710G');src=w/'development/npu-guarded-boot';recovery=w/'development/npu-recovery6'
r=Path('/home/xrdev/projects/xr1710g/openwrt');lab=r.parent/'boot-lab/npu-guarded-boot';k=lab.parent/'npu-addresses/linux-6.18.54'
host=r/'staging_dir/host';ship=r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
qa=json.loads((src/'function-qa.json').read_text());assert qa['passed'] and qa['sourceSHA256']==sha(src/'src/activate.c')
fixture=json.loads((src/'fixture-build.json').read_text());assert fixture['passed']
cases=sys.argv[1:] or ['success','bad-guard-pid','capture-gap','wrong-boot','already-loaded','parameter-reset','no-guard','fault','observer-missing','observer-invalid','observer-unloaded']
assert set(cases)<={'success','bad-guard-pid','capture-gap','wrong-boot','already-loaded','parameter-reset','no-guard','fault','observer-missing','observer-invalid','observer-unloaded'}
obs=w/'development/npu-address-diag'
obs_qa=json.loads((obs/'vm/result-latest.json').read_text());assert obs_qa['passed'] and obs_qa['kernelSHA256']==sha(k/'arch/x86/boot/bzImage')
assert obs_qa['observerSourceSHA256']==sha(obs/'src/xr_npu_addresses.c')
obs_builds=[p.parent for p in (lab.parent/'npu-addresses').glob('*/module/xr_npu_addresses.ko') if sha(p)==obs_qa['guestModuleSHA256']]
assert obs_builds;obs_build=sorted(obs_builds)[-1]
assert sha(obs_build/'xr_npu_fixture.c')==obs_qa['fixtureSourceSHA256']
out=w/'development/ap30/npu-gates/activation-vm';out.mkdir(exist_ok=True);stamp=datetime.now().strftime('%Y%m%d-%H%M%S');results=[]
release=(k/'include/config/kernel.release').read_text().strip()
for case in cases:
 root=lab/(stamp+'-'+case);root.mkdir()
 for d in ('bin','sbin','dev','proc','sys','tmp/sysinfo','etc/init.d','etc/rc.d','etc/modules.d','lib/functions','usr/sbin','usr/libexec','root','state','lib/modules/'+release):(root/d).mkdir(parents=True,exist_ok=True)
 shutil.copy2('/bin/busybox',root/'bin/busybox')
 for name in ('sh','mount','cat','sleep','grep','kill','mkdir','ls','wc','rm','sync','ln','basename','readlink','chmod','cp','sed','touch','insmod','timeout','rmmod','poweroff','reboot'):(root/'bin'/name).symlink_to('busybox')
 for name in ('etc/rc.common','lib/functions.sh','lib/functions/service.sh'):shutil.copy2(ship/name,root/name)
 for directory,a,b in [(recovery,'files/xr-recovery-once','usr/libexec/xr-recovery-once'),(recovery,'files/xr_diag_recovery','etc/init.d/xr_diag_recovery'),
  (src,'files/xr-npu-guarded-once','usr/libexec/xr-npu-guarded-once'),(src,'files/xr_guarded_npu','etc/init.d/xr_guarded_npu')]:
  shutil.copy2(directory/a,root/b);(root/b).chmod(0o755)
 for source,binary,extra in [(recovery/'src/recovery.c','usr/libexec/xr-diag-recovery',[]),
  (recovery/'src/capture.c','usr/libexec/xr-diag-capture',[]),
  (src/'src/activate.c','usr/libexec/xr-diag-activate',['-I'+str(host/'include'),str(host/'lib/libjson-c.a')])]:
  subprocess.run(['gcc','-static','-O2','-Wall','-Wextra','-Werror',str(source),*extra,'-o',str(root/binary)],check=True)
 shutil.copy2(lab/'kmodloader',root/'sbin/kmodloader');(root/'sbin/modprobe').symlink_to('kmodloader')
 variant=case if case in ('fault','parameter-reset') else 'normal'
 for name in ('mt76.ko','xr_dependency.ko'):shutil.copy2(lab/('module-'+variant)/name,root/'lib/modules'/release/name)
 for name in ('modules.builtin','modules.builtin.modinfo'):(root/'lib/modules'/release/name).touch()
 (root/'etc/modules.d/10-mt76').write_text('mt76 npu_enable=0 npu_rx_audit=0 npu_txfree_chain_verify=0\n')
 (root/'usr/sbin/xr1710g-ap-role').write_text('#!/bin/sh\nprintf \'{"role":"ap1"}\\n\'\n');(root/'usr/sbin/xr1710g-ap-role').chmod(0o755)
 (root/'tmp/sysinfo/board_name').write_text('gemtek,xr1710g\n')
 shutil.copy2(obs_build/'xr_npu_fixture.ko',root/'bin/xr_npu_fixture.ko')
 if case!='observer-missing':
  shutil.copy2(obs_build/'xr_npu_addresses.ko',root/'usr/libexec/xr_npu_addresses.ko')
  if case=='observer-invalid':(root/'usr/libexec/xr_npu_addresses.ko').write_bytes(b'invalid module fixture\n')
 init=r'''#!/bin/sh
export PATH=/bin:/sbin:/usr/sbin:/usr/libexec
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t debugfs debugfs /sys/kernel/debug
mark() { printf '<3>%s\n' "$*" >/dev/kmsg; }
fail() { mark "XR_ACTIVATION_FAIL: $*"; sync; poweroff -f; }
mount -t ext4 /dev/vda /state || fail disk
mkdir -p /state/root
if [ ! -e /state/initialized ]; then
 mkdir -p /state/etc
 cp -a /etc/. /state/etc/ || fail copy_etc
 touch /state/initialized
fi
mount --bind /state/etc /etc
mount --bind /state/root /root
boot=$(cat /proc/sys/kernel/random/boot_id)
if [ -e /state/first-boot ]; then
 [ ! -e /etc/xr-recovery.once ] && [ ! -e /etc/xr-npu-guarded.once ] || fail request_survived
 [ "$(cat /state/first-boot)" != "$boot" ] || fail same_epoch
 /bin/sh /etc/rc.common /etc/init.d/xr_diag_recovery boot || fail ordinary_guard
 /bin/sh /etc/rc.common /etc/init.d/xr_guarded_npu boot || fail ordinary_npu
 /sbin/kmodloader /etc/modules.d/ || fail default_loader
 [ "$(cat /sys/module/mt76/parameters/npu_enable)" = N ] || fail persistent_NPU_override
 [ ! -e "/root/xr-diag-journal/$boot" ] || fail repeated_diagnostic
 [ ! -e /sys/module/xr_npu_addresses ] || fail repeated_observer
 mark XR_ORDINARY_SECOND_BOOT_NPU_OFF
 sync; poweroff -f
fi
echo 0 >/proc/sys/kernel/panic_on_oops
insmod /bin/xr_npu_fixture.ko || fail address_fixture
printf '%s\n' "$boot" >/state/first-boot
printf 'xr-npu-guarded-v1 00000000-0000-0000-0000-000000000000\n' >/etc/xr-npu-guarded.once
chmod 600 /etc/xr-npu-guarded.once
if [ CASE != no-guard ]; then
 printf 'xr-recovery-v1 00000000-0000-0000-0000-000000000000\n' >/etc/xr-recovery.once
 chmod 600 /etc/xr-recovery.once
fi
/bin/sh /etc/rc.common /etc/init.d/xr_diag_recovery enable || fail guard_link
/bin/sh /etc/rc.common /etc/init.d/xr_guarded_npu enable || fail npu_link
set -- /etc/rc.d/S08*
[ "$1" = /etc/rc.d/S08xr_diag_recovery ] && [ "$2" = /etc/rc.d/S08xr_guarded_npu ] || fail init_order
sync
record=/root/xr-diag-journal/$boot
if [ CASE != no-guard ]; then
 /bin/sh /etc/rc.common /etc/init.d/xr_diag_recovery boot || fail guard_start
 [ -f "$record/ready.json" ] || fail guard_not_ready
fi
case CASE in
success)
 # Negative control: actual ubox modprobe ignores these CLI parameters.
 /sbin/modprobe mt76 npu_enable=1 || fail modprobe_control
 [ "$(cat /sys/module/mt76/parameters/npu_enable)" = N ] || fail modprobe_assumption
 rmmod mt76 || fail fixture_unload
 mark XR_MODPROBE_ARGUMENT_NEGATIVE_CONTROL
 ;;
bad-guard-pid) sed -i 's/"collectorPID":[0-9]*/"collectorPID":999999/' "$record/ready.json" ;;
capture-gap) sed -i 's/"gaps":0/"gaps":1/' "$record/capture/ready.json" ;;
wrong-boot) sed -i 's/"bootID":"[^"]*"/"bootID":"00000000-0000-0000-0000-000000000000"/' "$record/ready.json" ;;
already-loaded) /sbin/kmodloader /etc/modules.d/ ;;
esac
mark XR_GUARDED_ACTIVATION_CALL
activate() {
 if [ CASE = observer-unloaded ]; then
  rm /etc/xr-npu-guarded.once || return 1
  /usr/libexec/xr-diag-activate
 else
  /bin/sh /etc/rc.common /etc/init.d/xr_guarded_npu boot
 fi
}
if activate; then
 [ CASE = success ] || fail unexpected_acceptance
 [ "$(cat /sys/module/mt76/parameters/npu_enable)" = Y ] || fail missing_NPU_parameter
 [ -f "$record/module-enabled.json" ] || fail missing_module_record
 [ ! -e /etc/xr-npu-guarded.once ] || fail activation_request_not_consumed
 [ -d /sys/module/xr_dependency ] || fail dependency_not_loaded
 [ -d /sys/module/xr_npu_addresses ] || fail observer_not_loaded
 cat /sys/kernel/debug/xr_npu_addresses/snapshot >/state/observer-success.txt || fail observer_endpoint
 mark XR_VOLATILE_NPU_PARAMETER_ACCEPTED
else
 [ CASE != success ] || fail valid_activation_rejected
 if [ CASE != fault ]; then
  [ ! -f /sys/module/mt76/parameters/npu_enable ] || [ "$(cat /sys/module/mt76/parameters/npu_enable)" = N ] || fail bad_parameter_left_active
 fi
 mark XR_INVALID_ACTIVATION_REJECTED
fi
[ ! -e /etc/xr-npu-guarded.once ] || fail failed_request_not_consumed
set -- /tmp/xr-npu-modules.*
[ ! -e "$1" ] || fail volatile_options_not_removed
mark XR_VOLATILE_MODULE_OPTIONS_REMOVED
if [ CASE = no-guard ]; then
 sync; reboot -f
elif [ CASE != fault ]; then
 touch "$record/abort"
fi
sleep 30
fail guard_did_not_recover
'''.replace('CASE',case)
 (root/'init').write_text(init);(root/'init').chmod(0o755)
 paths=['.']+[str(p.relative_to(root)) for p in sorted(root.rglob('*'))]
 p=subprocess.run(['cpio','--null','-o','--format=newc','--owner=0:0'],cwd=root,input=('\0'.join(paths)+'\0').encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
 initrd=lab/(stamp+'-'+case+'.cpio.gz')
 with gzip.open(initrd,'wb') as f:f.write(p.stdout)
 disk=lab/(stamp+'-'+case+'.raw')
 with disk.open('xb') as f:f.truncate(64*1024*1024)
 subprocess.run(['/usr/sbin/mke2fs','-q','-t','ext4','-F','-E','lazy_itable_init=0,lazy_journal_init=0',str(disk)],check=True)
 accel='kvm' if Path('/dev/kvm').exists() else 'tcg'
 cpu='host' if accel=='kvm' else 'qemu64'
 cmd=['sudo','-n','timeout','55','qemu-system-x86_64','-accel',accel,'-cpu',cpu,'-smp','2','-m','1024','-nodefaults','-display','none','-serial','stdio','-monitor','none','-no-reboot','-run-with','user=xrdev',
  '-drive','file='+str(disk)+',format=raw,if=virtio,cache=none','-kernel',str(k/'arch/x86/boot/bzImage'),'-initrd',str(initrd),'-append','console=ttyS0 rdinit=/init panic=1 panic_on_oops=0 panic_on_warn=0']
 logs=[];codes=[]
 for epoch in (1,2):
  log=out/(stamp+'-'+case+'-boot'+str(epoch)+'.log')
  with log.open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
  logs.append(log.read_text(errors='replace'));codes.append(p.returncode)
 def disk_read(path):return subprocess.run(['/usr/sbin/debugfs','-R','cat '+path,str(disk)],capture_output=True).stdout
 boot=disk_read('/first-boot').decode().strip();journal='/root/xr-diag-journal/'+boot+'/';saved={}
 for name in ('activation-requested.json','activation-failed.json','module-enabled.json','aborted.json','recovery.json','capture/fault.json','capture/closed.json'):
  data=disk_read(journal+name)
  if data:
   (out/(stamp+'-'+case+'-'+name.replace('/','-'))).write_bytes(data)
   try:saved[name]=json.loads(data)
   except ValueError:saved[name]=None
 faults=disk_read(journal+'capture/first-fault.kmsg')
 if faults:(out/(stamp+'-'+case+'-first-fault.kmsg')).write_bytes(faults)
 unexpected=re.findall(r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|possible circular locking|sleeping function called from invalid context).*$',logs[0]+logs[1],re.M)
 markers=['XR_GUARDED_ACTIVATION_CALL','XR_VOLATILE_MODULE_OPTIONS_REMOVED']
 markers+=['XR_VOLATILE_NPU_PARAMETER_ACCEPTED','XR_MODPROBE_ARGUMENT_NEGATIVE_CONTROL'] if case=='success' else ['XR_INVALID_ACTIVATION_REJECTED']
 passed=codes==[0,0] and not unexpected and all('XR_ACTIVATION_FAIL:' not in s for s in logs) and all(m in logs[0] for m in markers) and 'XR_ORDINARY_SECOND_BOOT_NPU_OFF' in logs[1]
 addresses=disk_read(journal+'fault-npu-addresses.txt')
 if addresses:(out/(stamp+'-'+case+'-fault-npu-addresses.txt')).write_bytes(addresses)
 if case=='success':passed=passed and bool(saved.get('module-enabled.json')) and b'cpu_rx0_dma_base' in disk_read('/observer-success.txt')
 if case=='fault':passed=passed and b'XR_ACTIVATION_CONTROLLED_FAULT' in faults and (saved.get('capture/closed.json') or {}).get('fault') is True and (saved.get('aborted.json') or {}).get('reason')=='kernel-fault'
 if case=='fault':passed=passed and b'cpu_rx0_dma_base offset=0x30d180 first=0x8030d180' in addresses and b'snapshot_status=complete' in addresses
 if case not in ('success','fault','no-guard','observer-missing','observer-invalid'):passed=passed and bool(saved.get('activation-failed.json')) and not saved.get('module-enabled.json')
 if case in ('observer-missing','observer-invalid'):passed=passed and not saved.get('module-enabled.json') and not saved.get('activation-requested.json')
 if case=='observer-unloaded':passed=passed and saved.get('activation-failed.json',{}).get('reason')=='address-observer-not-loaded'
 if case=='success':
  closed=saved.get('capture/closed.json') or {}
  recover=saved.get('recovery.json') or {}
  passed=passed and closed.get('firstSeq')==0 and closed.get('records',0)>0
  passed=passed and closed.get('records')==closed.get('lastSeq',-2)+1
  passed=passed and closed.get('gaps')==0 and all(closed.get(x) is False for x in ('fault','failed','capped'))
  passed=passed and closed.get('monotonicMs',2**63)<=recover.get('monotonicMs',0)
 result={'passed':bool(passed),'case':case,'at':datetime.now().astimezone().isoformat(),'codes':codes,'saved':saved,'unexpectedFaults':unexpected,
  'sourceSHA256':sha(src/'src/activate.c'),'helperSHA256':sha(src/'files/xr-npu-guarded-once'),'initSHA256':sha(src/'files/xr_guarded_npu'),
  'guardSHA256':sha(recovery/'src/recovery.c'),'captureSHA256':sha(recovery/'src/capture.c'),'kmodloaderSourceSHA256':fixture['kmodloaderSourceSHA256'],
  'kernelSHA256':fixture['kernelSHA256'],'durationAdapterUsed':False,'secondBootNpuParameterOff':bool(passed),'noHostNetworkOrExistingDisks':True,
  'acceleration':accel,'cpuModel':cpu,'addressObserverSourceSHA256':obs_qa['observerSourceSHA256'],'actualObserverIncluded':True,
  'limits':['Real loader and module parameters, but fake mt76/dependency modules; no NPU hardware emulation','x86 ext4 guest; board and role identity fixtures']}
 (out/(stamp+'-'+case+'-result.json')).write_text(json.dumps(result,indent=2)+'\n');results.append(result)
 print(json.dumps({'case':case,'passed':bool(passed),'codes':codes,'failureReason':(saved.get('activation-failed.json') or {}).get('reason')}),flush=True)
 if not passed:break
report={'passed':len(results)==len(cases) and all(x['passed'] for x in results),'cases':results,'at':datetime.now().astimezone().isoformat()}
(out/(stamp+'-result.json')).write_text(json.dumps(report,indent=2)+'\n');(out/'result-latest.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if report['passed'] else 1)
