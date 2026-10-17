"""One-shot AP27 keep-config upgrade. AP2 must be accepted before AP1."""
from pathlib import Path
from datetime import datetime
import importlib.util,json,re,sys,time,hashlib
from xr_two_ap import WORKSPACE as w,connect as pinned,command
def connect(unit,**kw):return pinned(unit,via='lan')
s=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
VERSION='20261010-ap27-d331711d';BASELINE='20261010-ap26-d331711d';a.base.VERSION=VERSION;a.base.connect=connect
unit=int(sys.argv[1]);mode=sys.argv[2];assert unit in [1,2] and mode in ['upgrade','inspect']
root=w/'development/ap27';out=root/'deployment'/f'ap{unit}';out.mkdir(parents=True,exist_ok=True)
packed=json.loads((root/'packed-files-qa.json').read_text());SHA=packed['imageSHA256'];files=packed['matchedFiles'];remote='/tmp/xr-ap27-verified.itb'
markers=['/etc/xr-npu-guarded.once','/etc/xr-recovery.once','/etc/xr-kmsg-capture.once','/etc/xr1710g-npu-audit.once','/etc/xr1710g-diagnostic.json']
def read(c,text):return command(c,text)[0].decode().strip()
def boot(c):return read(c,'cat /proc/sys/kernel/random/boot_id')
def save(name,value):(out/name).write_text(json.dumps(value,indent=2)+'\n')
def clean(c):
 data=command(c,'dmesg')[0];assert not re.search(rb'WARNING:|BUG:|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated',data);return data
def absent(c,path):return command(c,'test ! -e '+path+' && test ! -L '+path,check=False)[2]==0
def healthy(u,v):
 h=a.health(u,v);assert h['healthy'],h['checks'];return h
def current_checks(c,state):
 assert a.identity(c,unit)['release']['version']==VERSION
 assert a.preservation(c)==state['preservationBefore']
 assert a.file_hashes(c,list(state['preservedFiles']))==state['preservedFiles']
 rom={'/rom/'+p:h for p,h in files.items()};assert a.file_hashes(c,list(rom))==rom
 live={'/'+p:h for p,h in files.items() if p.startswith(('bin/','lib/modules/','etc/init.d/','usr/','www/'))};assert a.file_hashes(c,list(live))==live
 assert read(c,'sha256sum /lib/firmware/airoha/en7581_MT7996_npu_rv32.bin').split()[0]=='e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
 assert read(c,'cat /sys/module/mac80211/parameters/mesh_rx_drop_audit')=='N'
 assert read(c,'cat /sys/module/mac80211/parameters/mesh_rx_drop_events').startswith('schema=1 enabled=0 total=0 retained=0')
 assert all(absent(c,p) for p in markers)
 assert all(absent(c,'/sys/module/'+p) for p in ['xr_npu_producer','xr_npu_addresses','xr_maple_observer'])
 ssh=json.loads(read(c,"ubus call service list '{\"name\":\"dropbear\"}'"))['dropbear']['instances']
 assert ssh and all(x.get('running') and x.get('netdev')==['br-lan.1'] for x in ssh.values())
 return {'ROMMatches':len(rom),'liveMatches':len(live),'preservedFiles':len(state['preservedFiles'])}
if mode=='upgrade':
 assert not (out/'scheduled.json').exists(),'Already submitted: inspect only'
 if unit==1:assert json.loads((out.parent/'ap2/result.json').read_text())['passed']
 for u in [1,2]:healthy(u,VERSION if u==2 and unit==1 else BASELINE)
 gate=json.loads((root/'boot-lab/result.json').read_text());assert gate['preflashChecksPassed'] and gate['imageSHA256']==SHA
 assert json.loads((root/'ping-rxbuf/live-queue-qa.json').read_text())['passed'] and json.loads((root/'mesh-rx-audit/qa/result.json').read_text())['passed']
 image=next((w/f'builds/{VERSION}-development').glob('*gemtek_xr1710g-squashfs-sysupgrade.itb')).read_bytes();assert hashlib.sha256(image).hexdigest()==SHA
 peer=connect(3-unit)
 try:peer_before={'bootID':boot(peer),'preservation':a.preservation(peer)};clean(peer)
 finally:peer.close()
 c=connect(unit)
 try:
  assert a.identity(c,unit)['release']['version']==BASELINE;before=boot(c);clean(c);assert all(absent(c,p) for p in markers)
  paths=read(c,'sysupgrade -l').splitlines();assert '/etc/shadow' in paths and '/etc/dropbear/dropbear_ed25519_host_key' in paths
  assert not any(p.startswith(('/lib/modules/','/lib/firmware/','/etc/init.d/','/usr/','/etc/xr-','/etc/xr1710g-diagnostic')) for p in paths)
  state={'unit':unit,'imageSHA256':SHA,'preservationBefore':a.preservation(c),'preservedFiles':a.file_hashes(c,paths),'bootBefore':before,'peerBefore':peer_before}
  save('preflight.json',state)
  stdin,stdout,stderr=c.exec_command('umask 077; cat > '+remote+'; sha256sum '+remote,timeout=90)
  stdin.channel.sendall(image);stdin.channel.shutdown_write();data,error=stdout.read(),stderr.read();assert stdout.channel.recv_exit_status()==0 and data.decode().split()[0]==SHA
  data,error,code=command(c,'sysupgrade -T '+remote,check=False);(out/'sysupgrade-test.txt').write_bytes(data+error);assert code==0
  assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,paths)==state['preservedFiles']
  save('scheduled.json',{'at':datetime.now().astimezone().isoformat(),'unit':unit,'imageSHA256':SHA,'bootBefore':before,'keepConfiguration':True})
  command(c,"sh -c 'sleep 3; exec /sbin/sysupgrade /tmp/xr-ap27-verified.itb' </dev/null >/tmp/xr-ap27-upgrade.log 2>&1 &")
  print(f'AP{unit}_AP27_UPGRADE_SUBMITTED_ONCE',flush=True)
 finally:c.close()
 time.sleep(12)
state=json.loads((out/'preflight.json').read_text());assert (out/'scheduled.json').exists()
limit=time.monotonic()+480;notice=0;verified=None
while time.monotonic()<limit:
 c=None
 try:
  c=connect(unit);after=boot(c)
  if after==state['bootBefore']:raise RuntimeError('Waiting for new boot')
  verified=current_checks(c,state);(out/'returned-kernel.txt').write_bytes(clean(c))
  save('returned.json',{'passed':True,'bootID':after,**verified});print(f'AP{unit}_AP27_SSH_AND_FILES_VERIFIED',flush=True);break
 except AssertionError:raise
 except Exception as e:
  if time.monotonic()-notice>25:print(json.dumps({'unit':unit,'waiting':type(e).__name__}),flush=True);notice=time.monotonic()
 finally:
  if c:c.close()
 time.sleep(6)
assert verified,'No confirmed return: do not repeat flash'
limit=time.monotonic()+300;last=None
while time.monotonic()<limit:
 h=a.health(unit,VERSION);save('health.json',h)
 if h['healthy']:break
 failures=[k for k,v in h['checks'].items() if not v]
 if failures!=last:print(json.dumps({'unit':unit,'waitingFor':failures}),flush=True);last=failures
 time.sleep(12)
assert h['healthy'],'Radio/Mesh readiness incomplete'
c=connect(unit)
try:
 guard=json.loads(read(c,'/usr/sbin/xr1710g-ap-uplink-guard status'))
 assert guard['failure_threshold']==3 and guard['recovery_successes']==3 and guard['desired']=='open' and guard['gate_autostart']=='open'
 assert guard['reason']=='gateway-reachable';assert boot(c)==after
 policy=json.loads(read(c,"ubus call luci.airoha_npu getDeviceMode '{}'"))
 assert policy['ppe_binding_enabled'] is False and policy['ppe_bridge_binding_enabled'] is False
 assert policy['ppe_bridge_policy_latched'] is True and policy['bridge_offload_block_reason']=='ppe_boot_policy_disabled'
 save('ppe-policy-live.json',policy)
 (out/'accepted-kernel.txt').write_bytes(clean(c));current_checks(c,state)
finally:c.close()
peer=connect(3-unit)
try:assert boot(peer)==state['peerBefore']['bootID'] and a.preservation(peer)==state['peerBefore']['preservation'];clean(peer)
finally:peer.close()
peer_health=healthy(3-unit,VERSION if unit==1 else BASELINE)
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':VERSION,'imageSHA256':SHA,'unit':unit,'bootID':after,'peerSameBootAndConfiguration':True,'configurationPreserved':True,**verified,'health':h,'peerHealth':peer_health,'guard':guard,'NpuEnabled':False,'phoneTested':False}
save('result.json',report);print(json.dumps({'passed':True,'unit':unit,'bootID':after,'version':VERSION,**verified}),flush=True)
