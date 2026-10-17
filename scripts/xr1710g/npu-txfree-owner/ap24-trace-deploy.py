"""One-shot diagnostic/production transitions, preserving config and peer boot."""
from pathlib import Path
from datetime import datetime
import importlib.util,json,hashlib,re,time,sys
from xr_two_ap import WORKSPACE as w,connect as pinned,command
def connect(unit,via=None):return pinned(unit,via='lan')
spec=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
VERSION='20261010-ap24-d331711d';a.base.VERSION=VERSION;a.base.connect=connect
assert len(sys.argv)==4;unit=int(sys.argv[1]);variant=sys.argv[2];mode=sys.argv[3]
assert unit in (1,2) and variant in ('trace','restore') and mode in ('upgrade','inspect')
base=w/'development/ap24/owner-trace';lab=json.loads((base/'result.json').read_text())
out=base/'deployment'/f'ap{unit}-{variant}';out.mkdir(parents=True,exist_ok=True)
original='e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
candidate='b48d5e6e4725adfc3560b25aeb9aa00a01134e2a0b9ae84ac2313fe5c32bc298'
packed=json.loads((w/'development/ap24/packed-files-qa.json').read_text())['matchedFiles'].copy()
if variant=='trace':
 image=base/Path(lab['artifact']).name;SHA=lab['artifactSHA256'];expected_fw=candidate
 for p,entry in lab['changedFiles'].items():
  if 'sha256' in entry:packed[p]=entry['sha256']
else:
 image=next((w/'builds/20261010-ap24-d331711d-development').glob('*-squashfs-sysupgrade.itb'))
 SHA='411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0';expected_fw=original
remote=f'/tmp/xr-ap24-{variant}-verified.itb'
markers=['/etc/xr-npu-guarded.once','/etc/xr-recovery.once','/etc/xr-kmsg-capture.once','/etc/xr1710g-npu-audit.once']
def save(n,v):(out/n).write_text(json.dumps(v,indent=2)+'\n')
def read(c,s):return command(c,s)[0].decode().strip()
def boot(c):return read(c,'cat /proc/sys/kernel/random/boot_id')
def absent(c,p):return command(c,'test ! -e '+p+' && test ! -L '+p,check=False)[2]==0
def clean(c):
 data=command(c,'dmesg')[0];assert not re.search(rb'WARNING:|BUG:|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated',data);return data
assert hashlib.sha256(image.read_bytes()).hexdigest()==SHA
startup=json.loads((base/'packed-startup.json').read_text());assert startup['passed'] and len(startup['checks'])==14 and startup['artifactSHA256']==lab['artifactSHA256']
assert json.loads((w/'development/ap24/boot-lab/result.json').read_text())['vmPrecheckPassed']
if mode=='upgrade':
 assert not (out/'scheduled.json').exists(),'Already scheduled; inspect only'
 assert all(a.health(u,VERSION)['healthy'] for u in (1,2))
 if variant=='trace' and unit==1:
  assert json.loads((base/'deployment/ap2-trace/result.json').read_text())['passed']
  assert json.loads((base/'ap2-epoch1/result.json').read_text())['ordinaryRecoveryAndCleanupPassed']
 if variant=='restore':
  assert json.loads((base/'ap1-epoch1/result.json').read_text())['ordinaryRecoveryAndCleanupPassed']
  if unit==1:assert json.loads((base/'deployment/ap2-restore/result.json').read_text())['passed']
 peer=connect(3-unit)
 try:peer_before={'bootID':boot(peer),'preservation':a.preservation(peer)};clean(peer)
 finally:peer.close()
 c=connect(unit)
 try:
  assert a.identity(c,unit)['release']['version']==VERSION;before=boot(c);clean(c)
  if variant=='trace':assert absent(c,'/etc/xr1710g-diagnostic.json')
  else:assert json.loads(read(c,'cat /etc/xr1710g-diagnostic.json'))['id']==lab['id']
  assert read(c,'sha256sum /lib/firmware/airoha/en7581_MT7996_npu_rv32.bin').split()[0]==(original if variant=='trace' else candidate)
  assert all(absent(c,p) for p in markers) and all(absent(c,'/sys/module/'+n) for n in ('xr_npu_producer','xr_npu_addresses'))
  paths=read(c,'sysupgrade -l').splitlines();assert '/etc/shadow' in paths and '/etc/dropbear/dropbear_ed25519_host_key' in paths
  assert not any(p.startswith(('/lib/modules/','/lib/firmware/','/etc/init.d/','/usr/libexec/','/etc/xr-','/etc/xr1710g-diagnostic')) for p in paths)
  state={'unit':unit,'variant':variant,'bootBefore':before,'imageSHA256':SHA,'preservationBefore':a.preservation(c),'preservedFiles':a.file_hashes(c,paths),'peerBefore':peer_before}
  save('preflight.json',state)
  stdin,stdout,stderr=c.exec_command('umask 077; cat > '+remote+'; sha256sum '+remote,timeout=90)
  stdin.channel.sendall(image.read_bytes());stdin.channel.shutdown_write();data,error=stdout.read(),stderr.read();assert stdout.channel.recv_exit_status()==0 and data.decode().split()[0]==SHA
  data,error,code=command(c,'sysupgrade -T '+remote,check=False);(out/'sysupgrade-test.txt').write_bytes(data+error);assert code==0
  assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,paths)==state['preservedFiles']
  save('scheduled.json',{'at':datetime.now().astimezone().isoformat(),'unit':unit,'variant':variant,'imageSHA256':SHA,'keepConfiguration':True})
  command(c,"sh -c 'sleep 3; exec /sbin/sysupgrade "+remote+"' </dev/null >/tmp/xr-ap24-trace-transition.log 2>&1 &")
  print(f'AP{unit}_{variant.upper()}_UPGRADE_SUBMITTED_ONCE',flush=True)
 finally:c.close()
 time.sleep(12)
state=json.loads((out/'preflight.json').read_text());assert (out/'scheduled.json').exists()
limit=time.monotonic()+480;returned=None;last_notice=0
while time.monotonic()<limit:
 c=None
 try:
  c=connect(unit);current=boot(c)
  if current==state['bootBefore']:raise RuntimeError('Old boot')
  assert a.identity(c,unit)['release']['version']==VERSION
  assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,list(state['preservedFiles']))==state['preservedFiles']
  expected={'/rom/'+p:h for p,h in packed.items()};assert a.file_hashes(c,list(expected))==expected
  live={'/'+p:h for p,h in packed.items() if p.startswith(('lib/modules/','usr/libexec/xr-','usr/libexec/xr_','etc/init.d/dropbear'))};assert a.file_hashes(c,list(live))==live
  assert read(c,'sha256sum /lib/firmware/airoha/en7581_MT7996_npu_rv32.bin').split()[0]==expected_fw
  if variant=='trace':assert json.loads(read(c,'cat /etc/xr1710g-diagnostic.json'))['id']==lab['id']
  else:assert absent(c,'/etc/xr1710g-diagnostic.json')
  assert all(absent(c,p) for p in markers) and all(absent(c,'/sys/module/'+n) for n in ('xr_npu_producer','xr_npu_addresses'))
  (out/'returned-kernel.txt').write_bytes(clean(c))
  returned={'bootID':current,'preservedFileCount':len(state['preservedFiles']),'ROMMatched':len(expected),'liveMatched':len(live),'firmwareSHA256':expected_fw}
  save('returned.json',returned);print(json.dumps({'unit':unit,'variant':variant,'returned':returned}),flush=True);break
 except AssertionError:raise
 except Exception as e:
  if time.monotonic()-last_notice>25:print(json.dumps({'unit':unit,'variant':variant,'waiting':type(e).__name__}),flush=True);last_notice=time.monotonic()
 finally:
  if c:c.close()
 time.sleep(6)
assert returned,'No automatic return; never repeat blindly'
limit=time.monotonic()+300
while time.monotonic()<limit:
 health={str(u):a.health(u,VERSION) for u in (1,2)};save('health.json',health)
 if all(x['healthy'] for x in health.values()):break
 print(json.dumps({'radioReadiness':{u:h['healthy'] for u,h in health.items()}}),flush=True);time.sleep(12)
assert all(x['healthy'] for x in health.values())
peer=connect(3-unit)
try:assert boot(peer)==state['peerBefore']['bootID'] and a.preservation(peer)==state['peerBefore']['preservation'];clean(peer)
finally:peer.close()
save('result.json',{'passed':True,'at':datetime.now().astimezone().isoformat(),'unit':unit,'variant':variant,'imageSHA256':SHA,'returned':returned,'bothHealthy':True,'peerBootAndConfigUnchanged':True,'NpuEnabled':False,'health':health})
print(f'AP{unit}_{variant.upper()}_TRANSITION_ACCEPTED',flush=True)
