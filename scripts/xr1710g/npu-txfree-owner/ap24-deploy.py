"""One-shot AP24 keep-config upgrade; exact packed files, then an ordinary reboot."""
from pathlib import Path
from datetime import datetime
import importlib.util,json,re,sys,time,hashlib
from xr_two_ap import WORKSPACE as w,connect as pinned_connect,command
def connect(unit,via=None):return pinned_connect(unit,via='lan')
spec=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
VERSION='20261010-ap24-d331711d';BASELINE='20261010-ap23-d331711d';a.base.VERSION=VERSION;a.base.connect=connect
SHA='411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0'
ORIGINAL_NPU='e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
unit=int(sys.argv[1]);mode=sys.argv[2];assert unit in (1,2) and mode in ('upgrade','inspect','reboot')
out=w/'development/ap24/deployment'/f'ap{unit}-upgrade';out.mkdir(parents=True,exist_ok=True)
remote='/tmp/xr-ap24-verified.itb'
packed=json.loads((w/'development/ap24/packed-files-qa.json').read_text())['matchedFiles']
markers=['/etc/xr-npu-guarded.once','/etc/xr-recovery.once','/etc/xr-kmsg-capture.once','/etc/xr1710g-npu-audit.once']
def save(name,data):(out/name).write_text(json.dumps(data,indent=2)+'\n')
def read(c,cmd):return command(c,cmd)[0].decode().strip()
def boot(c):return read(c,'cat /proc/sys/kernel/random/boot_id')
def absent(c,path):return command(c,'test ! -e '+path+' && test ! -L '+path,check=False)[2]==0
def clean(c):
 data=command(c,'dmesg')[0];assert not re.search(rb'WARNING:|BUG:|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated',data);return data
def verify_return(before,label):
 limit=time.monotonic()+480;last_notice=0
 while time.monotonic()<limit:
  c=None
  try:
   c=connect(unit);current=boot(c)
   if current==before:raise RuntimeError('Waiting for new boot')
   assert a.identity(c,unit)['release']['version']==VERSION
   state=json.loads((out/'preflight.json').read_text())
   assert a.preservation(c)==state['preservationBefore']
   assert a.file_hashes(c,list(state['preservedFiles']))==state['preservedFiles']
   expected={'/rom/'+p:h for p,h in packed.items()};assert a.file_hashes(c,list(expected))==expected
   live={'/'+p:h for p,h in packed.items() if p.startswith(('lib/modules/','etc/init.d/dropbear','usr/libexec/xr-kmsg-'))}
   assert a.file_hashes(c,list(live))==live
   assert read(c,'sha256sum /lib/firmware/airoha/en7581_MT7996_npu_rv32.bin').split()[0]==ORIGINAL_NPU
   assert absent(c,'/etc/xr1710g-diagnostic.json') and all(absent(c,p) for p in markers)
   assert all(absent(c,'/sys/module/'+p) for p in ('xr_npu_producer','xr_npu_addresses'))
   (out/(label+'-kernel.txt')).write_bytes(clean(c))
   ssh=json.loads(read(c,"ubus call service list '{\"name\":\"dropbear\"}'"))['dropbear']['instances']
   assert ssh and all(x.get('running') and x.get('netdev')==['br-lan.1'] for x in ssh.values())
   report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':VERSION,'beforeBootID':before,'afterBootID':current,
    'preservedFileCount':len(state['preservedFiles']),'configurationRootKeysAndCriticalHashesPreserved':True,
    'ROMMatches':len(expected),'liveMatches':len(live),'originalUninstrumentedNpuFirmware':True,'SSHAutorecoveredWithoutRPCRestart':True}
   save(label+'-returned.json',report);print(json.dumps(report),flush=True);return current
  except AssertionError:raise
  except Exception as e:
   if time.monotonic()-last_notice>25:print(json.dumps({'unit':unit,'stage':label,'waiting':type(e).__name__}),flush=True);last_notice=time.monotonic()
  finally:
   if c:c.close()
  time.sleep(6)
 raise RuntimeError('No SSH return; inspect only, never repeat flash blindly')
def radios(label):
 limit=time.monotonic()+300
 while time.monotonic()<limit:
  h=a.health(unit,VERSION);save(label+'-health.json',h)
  if h['healthy']:return h
  print(json.dumps({'unit':unit,'radioReadiness':h['checks']}),flush=True);time.sleep(12)
 raise RuntimeError('Radio readiness did not complete')
if mode=='upgrade':
 assert not (out/'scheduled.json').exists(),'Already scheduled; inspect only'
 for u in (1,2):assert a.health(u,VERSION if u==2 and unit==1 else BASELINE)['healthy']
 if unit==1:assert json.loads((out.parent/'ap2-upgrade/result.json').read_text())['passed']
 gate=json.loads((w/'development/ap24/boot-lab/result.json').read_text());assert gate['vmPrecheckPassed'] and gate['imageSHA256']==SHA
 image=next((w/'builds/20261010-ap24-d331711d-development').glob('*-squashfs-sysupgrade.itb')).read_bytes();assert hashlib.sha256(image).hexdigest()==SHA
 peer=connect(3-unit)
 try:peer_before={'bootID':boot(peer),'preservation':a.preservation(peer)};clean(peer)
 finally:peer.close()
 c=connect(unit)
 try:
  assert a.identity(c,unit)['release']['version']==BASELINE;before=boot(c);clean(c)
  assert json.loads(read(c,'cat /etc/xr1710g-diagnostic.json'))['id']=='ap23-npu-producer-lab1'
  assert all(absent(c,p) for p in markers)
  paths=read(c,'sysupgrade -l').splitlines();assert '/etc/shadow' in paths and '/etc/dropbear/dropbear_ed25519_host_key' in paths
  assert not any(p.startswith(('/lib/modules/','/lib/firmware/','/etc/init.d/','/usr/libexec/','/etc/xr-','/etc/xr1710g-diagnostic')) for p in paths)
  state={'unit':unit,'imageSHA256':SHA,'preservationBefore':a.preservation(c),'preservedFiles':a.file_hashes(c,paths),'bootBefore':before,'peerBefore':peer_before}
  save('preflight.json',state)
  stdin,stdout,stderr=c.exec_command('umask 077; cat > '+remote+'; sha256sum '+remote,timeout=90)
  stdin.channel.sendall(image);stdin.channel.shutdown_write();data,error=stdout.read(),stderr.read()
  assert stdout.channel.recv_exit_status()==0 and data.decode().split()[0]==SHA
  data,error,code=command(c,'sysupgrade -T '+remote,check=False);(out/'sysupgrade-test.txt').write_bytes(data+error);assert code==0
  assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,paths)==state['preservedFiles']
  save('scheduled.json',{'at':datetime.now().astimezone().isoformat(),'unit':unit,'keepConfiguration':True,'imageSHA256':SHA,'bootBefore':before})
  command(c,"sh -c 'sleep 3; exec /sbin/sysupgrade /tmp/xr-ap24-verified.itb' </dev/null >/tmp/xr-ap24-upgrade.log 2>&1 &")
  print(f'AP{unit}_AP24_UPGRADE_SUBMITTED_ONCE',flush=True)
 finally:c.close()
 time.sleep(12)
if mode in ('upgrade','inspect'):
 state=json.loads((out/'preflight.json').read_text());assert (out/'scheduled.json').exists()
 verify_return(state['bootBefore'],'upgrade');radios('upgrade');save('upgrade-accepted.json',{'passed':True,'version':VERSION,'imageSHA256':SHA})
else:
 assert json.loads((out/'upgrade-accepted.json').read_text())['passed'] and not (out/'normal-reboot.json').exists()
 assert a.health(unit,VERSION)['healthy'];c=connect(unit)
 try:
  clean(c);before=boot(c);save('normal-reboot.json',{'beforeBootID':before,'oneShot':True,'at':datetime.now().astimezone().isoformat()})
  command(c,"sh -c 'sleep 2; sync; reboot' </dev/null >/tmp/xr-ap24-reboot.log 2>&1 &");print(f'AP{unit}_ORDINARY_REBOOT_SUBMITTED_ONCE',flush=True)
 finally:c.close()
 time.sleep(12);verify_return(before,'normal-reboot');health=radios('normal-reboot')
 peer=connect(3-unit);state=json.loads((out/'preflight.json').read_text())
 try:assert boot(peer)==state['peerBefore']['bootID'] and a.preservation(peer)==state['peerBefore']['preservation'];clean(peer)
 finally:peer.close()
 peer_health=a.health(3-unit,VERSION if unit==1 else BASELINE);assert peer_health['healthy']
 save('result.json',{'passed':True,'at':datetime.now().astimezone().isoformat(),'version':VERSION,'unit':unit,'imageSHA256':SHA,
  'normalRebootSSHAutorecovered':True,'peerSameBootAndConfig':True,'keepConfiguration':True,'health':health,'peerHealth':peer_health,'NpuEnabled':False,'phoneTested':False})
 print(f'AP{unit}_AP24_UPGRADE_AND_ORDINARY_REBOOT_ACCEPTED',flush=True)
