"""AP24 AP1 candidate ownership fix: original NPU blob, exact qualified startup, bounded two-direction AP-to-AP TCP load."""
from pathlib import Path
from datetime import datetime
import json,hashlib,importlib.util,re,time,threading,shlex,sys
from xr_two_ap import WORKSPACE,connect as pinned_connect,command
def connect(unit,via=None):return pinned_connect(unit,via="lan")
from xr_npu_diagnostic_gates import DiagnosticEpoch,DiagnosticRejected,kernel_findings
spec=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
VERSION='20261010-ap24-d331711d';a.base.VERSION=VERSION;a.base.connect=connect
base=WORKSPACE/'development/npu-guarded-boot';recovery=WORKSPACE/'development/npu-recovery'
out=WORKSPACE/'development/ap24/npu-ap1-load2';out.mkdir(exist_ok=True);operation=out/'operation.json';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
items={'/usr/libexec/xr-diag-capture':recovery/'xr-diag-capture','/usr/libexec/xr-diag-recovery':recovery/'xr-diag-recovery',
 '/usr/libexec/xr-recovery-once':recovery/'files/xr-recovery-once','/etc/init.d/xr_diag_recovery':recovery/'files/xr_diag_recovery',
 '/usr/libexec/xr-diag-activate':base/'xr-diag-activate-package','/usr/libexec/xr-npu-guarded-once':base/'files/xr-npu-guarded-once',
 '/etc/init.d/xr_guarded_npu':base/'files/xr_guarded_npu',
 '/usr/libexec/xr_npu_addresses.ko':WORKSPACE/'development/npu-address-diag/arm/xr_npu_addresses.ko'}
links=['/etc/rc.d/S08xr_diag_recovery','/etc/rc.d/S08xr_guarded_npu'];requests=['/etc/xr-recovery.once','/etc/xr-npu-guarded.once']
parameter_paths={'wlanNpu':'/sys/module/mt76/parameters/npu_enable','npuAudit':'/sys/module/mt76/parameters/npu_rx_audit',
 'npuChain':'/sys/module/mt76/parameters/npu_txfree_chain_verify','ppe':'/sys/module/airoha_eth/parameters/ppe_bind_enable',
 'ppeBridge':'/sys/module/airoha_eth/parameters/ppe_bridge_bind_enable','puncturing':'/sys/module/mt7996e/parameters/puncturing_enable',
 'mcuStats':'/sys/module/mt7996e/parameters/mcu_stats_enable','airtimeABI':'/sys/module/mt7996e/parameters/mcu_airtime_cumulative_us'}
def save(name,data):(out/name).write_text(json.dumps(data,indent=2)+'\n')
def read(c,cmd):return command(c,cmd)[0].decode().strip()
def boot(c):return read(c,'cat /proc/sys/kernel/random/boot_id')
def absent(c,path):return command(c,'test ! -e '+shlex.quote(path)+' && test ! -L '+shlex.quote(path),check=False)[2]==0
def data_json(c,path):
 data,_,code=command(c,'cat '+shlex.quote(path),check=False)
 return json.loads(data) if code==0 else None
def params(c):return {name:read(c,'cat '+path) for name,path in parameter_paths.items()}
def new_dirs(c):
 data=command(c,'ls -1 /root/xr-diag-journal',check=False)[0].decode().splitlines()
 return {x for x in data if re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',x)}
def put(c,path,data,mode='700'):
 stdin,stdout,stderr=c.exec_command('umask 077; set -C; cat > '+shlex.quote(path),timeout=60)
 stdin.channel.sendall(data);stdin.channel.shutdown_write();stdout.read();assert stdout.channel.recv_exit_status()==0,stderr.read()
 command(c,'chmod '+mode+' '+shlex.quote(path))
def preservation(c):
 assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,list(state['preservedFiles']))==state['preservedFiles']
def token(c):
 paths=read(c,'for p in /sys/kernel/debug/ieee80211/phy*/mt76/xr_token_info; do test ! -f "$p" || printf "%s\\n" "$p"; done').splitlines()
 assert paths and all(re.fullmatch(r'/sys/kernel/debug/ieee80211/phy[0-9]+/mt76/xr_token_info',p) for p in paths)
 return command(c,'cat '+paths[0])[0].decode()
def process_alive(c,pid,record):
 if type(pid) is not int or pid<=1:return False
 raw,_,code=command(c,'cat /proc/'+str(pid)+'/cmdline',check=False)
 if code or record.encode() not in raw:return False
 stat,_,code=command(c,'cat /proc/'+str(pid)+'/stat',check=False)
 return code==0 and stat.decode().rsplit(') ',1)[1].split()[0] not in ('Z','X')
authorization_file=WORKSPACE/'development/npu-diagnostic-ap2/promotion.json'
authorization_sha=sha(authorization_file)
authorization=json.loads(authorization_file.read_text())
assert authorization['ownerRiskAcceptanceOverridesIndependentRecoveryHold']
gate_qa=json.loads((WORKSPACE/'development/ap24/owner-trace/remote-gates-qa.json').read_text())
assert gate_qa['passed'] and gate_qa['authorizationSHA256']==authorization_sha
assert gate_qa['sourceSHA256']==sha(Path(__file__).with_name('xr_npu_diagnostic_gates.py'))
recovery_policy={'ownerAcceptedRemoteLoss':True,'authorizationSHA256':authorization_sha}
for unit in (1,2):assert json.loads((WORKSPACE/f'development/ap24/owner-trace/deployment/ap{unit}-restore/result.json').read_text())['passed']

def snapshot(diag):
 snap={'independentAP2WiredRecovery':False,'remoteRecoveryAuthorizationSHA256':authorization_sha,'startupCaptureVerifiedLive':True}
 for unit in (1,2):
  c=connect(unit)
  try:
   board=a.identity(c,unit);kernel=read(c,'dmesg');current=boot(c);parameters=params(c);tok=token(c)
   station=read(c,'iw dev mesh6g station dump')
   row={'version':board['release']['version'],'role':'ap'+str(unit),'kernelLog':kernel,'bootID':current,
    'parameters':parameters,'npuActive':'npu_active=1' in tok,'tokenMetadata':tok,
    'mesh':{'authorized':bool(re.search(r'authorized:\s+yes',station)),
     'established':bool(re.search(r'mesh plink:\s+ESTAB',station)),
     'forwardingState':int(read(c,'cat /sys/class/net/mesh6g/brport/state'))}}
   for label,ip in [('peerPing','192.168.10.'+('4' if unit==1 else '3')),('gatewayPing','192.168.10.1')]:
    data,error,code=command(c,'ping -I br-lan.1 -i 1 -c 5 -W 1 '+ip,timeout=12,check=False)
    match=re.search(rb'(\d+) packets transmitted, (\d+) packets received',data)
    row[label]={'sent':int(match[1]),'received':int(match[2])} if match and code==0 else {'sent':0,'received':0}
    row[label+'Raw']={'stdout':data.decode(),'stderr':error.decode(),'code':code}
   if unit==1:
    record='/root/xr-diag-journal/'+diag;guard=data_json(c,record+'/ready.json') or {};cap=data_json(c,record+'/capture/ready.json')
    row['ownedRequestConsumed']=all(absent(c,p) for p in requests)
    row['ordinaryBootDeadlineVerified']=True
    row['recoveryGuard']={'bootID':guard.get('bootID'),'supervisorAlive':process_alive(c,guard.get('pid'),record),
     'deadlineAlive':process_alive(c,guard.get('deadlinePID'),record),'collectorAlive':process_alive(c,guard.get('collectorPID'),record),
     'requestConsumed':row['ownedRequestConsumed'],'aborted':not absent(c,record+'/aborted.json'),
     'fault':not absent(c,record+'/capture/fault.json'),'faultPending':not absent(c,record+'/capture/first-fault.kmsg'),
     'collectorClosed':not absent(c,record+'/capture/closed.json'),'deadlineMs':guard.get('deadlineMs'),
     'collectorPID':guard.get('collectorPID'),'captureReady':cap,'observedMonotonicMs':int(float(read(c,'cat /proc/uptime').split()[0])*1000)}
   if unit==2:
    row['wiredCarriers']=read(c,'for d in lan2 lan3 lan4 wan; do printf "%s=" "$d"; cat /sys/class/net/$d/carrier || exit 1; done')
   snap[str(unit)]=row
  finally:c.close()
 return snap

assert json.loads((WORKSPACE/'development/ap24/deployment/final-result.json').read_text())['passed']
assert len(sys.argv)==2 and sys.argv[1]=='run' and not operation.exists(),'Inspect one-shot journal; do not restart this epoch'
assert json.loads((WORKSPACE/'development/ap24/npu-ap1-load1/result.json').read_text())['ordinaryRecoveryAndCleanupPassed']
for directory,count in ((base,11),(recovery,11)):
 vm=json.loads((directory/'vm/result-latest.json').read_text());assert vm['passed'] and len(vm['cases'])==count
 assert json.loads((directory/'package-build.json').read_text())['passed']
prior=json.loads((base/'live-epoch-2/result.json').read_text())
assert prior['kernelFaultObserved'] and prior['ordinaryRecoveryAndCleanupPassed']
assert json.loads((recovery/'package-build.json').read_text())['sourceHashes']['src/recovery.c']==sha(recovery/'src/recovery.c')
for case in json.loads((base/'vm/result-latest.json').read_text())['cases']:
 assert case['guardSHA256']==sha(recovery/'src/recovery.c')
rec_build=json.loads((recovery/'package-build.json').read_text());act_build=json.loads((base/'package-build.json').read_text())
for directory,build in ((recovery,rec_build),(base,act_build)):
 for name,digest in build['sourceHashes'].items():assert sha(directory/name)==digest
assert rec_build['sourceHashes']['src/recovery.c']==sha(recovery/'src/recovery.c')
assert act_build['sourceHashes']['src/activate.c']==sha(base/'src/activate.c')
assert act_build['binarySHA256']==sha(items['/usr/libexec/xr-diag-activate'])
for name,h in rec_build['binaries'].items():assert sha(recovery/name)==h
assert json.loads((recovery/'live-baseline/result.json').read_text())['automatic180SecondRecoveryToOrdinaryBoot']
observer=WORKSPACE/'development/npu-address-diag'
obs_vm=json.loads((observer/'vm/result-latest.json').read_text());obs_arm=json.loads((observer/'arm/result-latest.json').read_text())
assert obs_vm['passed'] and len(obs_vm['cases'])==12 and obs_arm['passed']
assert obs_vm['observerSourceSHA256']==obs_arm['observerSourceSHA256']==sha(observer/'src/xr_npu_addresses.c')
assert obs_arm['moduleSHA256']==sha(items['/usr/libexec/xr_npu_addresses.ko'])
assert json.loads((observer/'live-baseline/result.json').read_text())['observerRemoved']
for case in json.loads((base/'vm/result-latest.json').read_text())['cases']:
 assert case['actualObserverIncluded'] and case['addressObserverSourceSHA256']==obs_vm['observerSourceSHA256']
for unit in (1,2):
 assert a.health(unit,VERSION)['healthy']
 c=connect(unit)
 try:
  assert read(c,'sha256sum /lib/firmware/airoha/en7581_MT7996_npu_rv32.bin').split()[0]=='e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
  qa=json.loads((WORKSPACE/'development/ap24/packed-files-qa.json').read_text())['matchedFiles']
  for name in ('mt76.ko','mt7996e.ko','mac80211.ko','cfg80211.ko'):
   path='lib/modules/6.18.54/'+name
   assert read(c,'sha256sum /'+path).split()[0]==qa[path]
 finally:c.close()
c2=connect(2)
try:ap2_before={'bootID':boot(c2),'preservation':a.preservation(c2)}
finally:c2.close()
c=connect(1)
try:
 assert not kernel_findings(read(c,'dmesg')) and all(v=='N' for v in params(c).values());old=boot(c)
 assert json.loads(read(c,'xr1710g-ap-role'))['role']=='ap1'
 for path in [*items,*links,*requests,'/etc/xr1710g-npu-audit.once','/etc/modules.d/00-xr1710g-npu-audit','/sys/module/xr_npu_addresses']:assert absent(c,path),path
 watchdog=json.loads(read(c,"ubus call system watchdog '{}'"));assert watchdog['status']=='running' and watchdog['timeout']==30 and not watchdog['magicclose']
 paths=read(c,'sysupgrade -l').splitlines()
 packed=json.loads((WORKSPACE/'development/ap24/packed-files-qa.json').read_text())['matchedFiles']
 module_hashes={'/'+p:h for p,h in packed.items() if p.startswith('lib/modules/')}
 assert a.file_hashes(c,list(module_hashes))==module_hashes
 state={'at':datetime.now().astimezone().isoformat(),'status':'prepared-before-write','bootBefore':old,
  'version':VERSION,'AP2Before':ap2_before,'previousJournals':sorted(new_dirs(c)),
  'preservationBefore':a.preservation(c),'preservedFiles':a.file_hashes(c,paths),
  'expectedFiles':{p:sha(src) for p,src in items.items()},'deadlineSeconds':180,'NpuChainAndAuditAndPpeOff':True,
  'VMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12},'ownerAcceptedNoIndependentRecovery':True,'originalNpuFirmwareUnchanged':True,'candidateDmaOwnershipFixInstalled':True,'noPhoneTest':True,'plannedTraffic':'Two8secondTCPdirections,2streams,100MbpsPerStream,AP2clientAP1server'}
 save('operation.json',state)
 for p,src in items.items():put(c,p,src.read_bytes());assert read(c,'sha256sum '+p).split()[0]==sha(src)
 # Invalid CLI tests only; never invoke the actor without its startup request.
 assert command(c,'/usr/libexec/xr-diag-activate invalid',check=False)[2]==2
 for name in ('xr_diag_recovery','xr_guarded_npu'):command(c,'/etc/init.d/'+name+' enable')
 for p in links:assert read(c,'readlink '+p)=='../init.d/'+p.split('S08',1)[1]
 for p,prefix in zip(requests,('xr-recovery-v1','xr-npu-guarded-v1')):put(c,p,(prefix+' '+old+'\n').encode(),'600')
 for name in ('xr_diag_recovery','xr_guarded_npu'):command(c,'/etc/init.d/'+name+' boot')
 assert new_dirs(c)==set(state['previousJournals']) and all(not absent(c,p) for p in requests)
 command(c,'sync');preservation(c)
 state['status']='reboot-issued-once';state['rebootAt']=datetime.now().astimezone().isoformat();save('operation.json',state)
 command(c,"sh -c 'sleep 2; sync; reboot' </dev/null >/tmp/xr-guarded-npu-start.log 2>&1 &")
 print('AP1_GUARDED_NPU_EPOCH_SUBMITTED_ONCE',flush=True)
finally:c.close()

fault_event=threading.Event();stop_event=threading.Event();monitor=None;diag=None;epoch=None;traffic=[];recovered=None;last_notice=0
active_samples=[];last_sample=0
def monitor_fault(record):
 c=None
 try:
  c=connect(1)
  while not stop_event.is_set():
   if not absent(c,record+'/capture/first-fault.kmsg') or not absent(c,record+'/capture/fault.json'):
    fault_event.set()
    try:(out/'first-fault-token-metadata.txt').write_text(token(c));(out/'first-fault-live-kernel.txt').write_text(read(c,'dmesg'))
    except Exception as error:save('fault-monitor-read-error.json',{'error':type(error).__name__})
    return
   stop_event.wait(.4)
 except Exception as error:save('fault-monitor-end.json',{'error':type(error).__name__})
 finally:
  if c:c.close()

limit=time.monotonic()+660
while time.monotonic()<limit:
 c=None
 try:
  c=connect(1);current=boot(c)
  if current==old:continue
  added=new_dirs(c)-set(state['previousJournals']);assert len(added)==1,('unexpected diagnostic journals',sorted(added));diag=next(iter(added));record='/root/xr-diag-journal/'+diag
  if current!=diag:
   assert all(v=='N' for v in params(c).values()) and all(absent(c,p) for p in requests);preservation(c)
   recovered=current;break
  if epoch is not None:
   if time.monotonic()-last_sample>=25:
    active_samples.append({'bootID':current,'uptime':read(c,'cat /proc/uptime'),'tokenMetadata':token(c),'parameters':params(c)})
    save('active-samples.json',active_samples);last_sample=time.monotonic()
    print(json.dumps({'diagnosticBoot':diag,'activeScalarSamples':len(active_samples),'waitingForIndependentDeadline':True}),flush=True)
   continue
  activation=data_json(c,record+'/module-enabled.json');kernel=read(c,'dmesg')
  if kernel_findings(kernel) or not absent(c,record+'/capture/first-fault.kmsg'):
   fault_event.set();(out/'startup-fault-kernel.txt').write_text(kernel)
   try:(out/'startup-fault-token-metadata.txt').write_text(token(c))
   except Exception:pass
   print('STARTUP_FAULT_NO_TRAFFIC_WAITING_FOR_RECOVERY',flush=True);continue
  if not activation:
   save('activation-not-confirmed.json',{'bootID':diag,'parameters':params(c),'failure':data_json(c,record+'/activation-failed.json')})
   continue
  assert activation['bootID']==diag
  assert params(c)['wlanNpu']=='Y' and 'npu_active=1' in token(c)
  save('activation-observed.json',{'at':datetime.now().astimezone().isoformat(),'bootID':diag,'activation':activation,'tokenMetadata':token(c)})
  epoch=DiagnosticEpoch({'1':VERSION,'2':VERSION},diag,old,recovery_policy=recovery_policy)
  monitor=threading.Thread(target=monitor_fault,args=(record,),daemon=True);monitor.start()
  print('AP1_NPU_ACTIVE_CAPTURE_AND_RECOVERY_PRESENT',flush=True)
  c.close();c=None
  try:
   for index,reverse in enumerate((False,True)):
    before=snapshot(diag);save('before-'+str(index)+'.json',before)
    if fault_event.is_set():epoch.reject('asynchronous first fault observed')
    guard=before['1']['recoveryGuard'];remaining=guard['deadlineMs']-guard['observedMonotonicMs']
    if remaining<65000:
     traffic.append({'reverse':reverse,'skipped':'insufficient remaining deadline'});break
    assert set(before['2']['wiredCarriers'].splitlines())=={d+'=0' for d in ('lan2','lan3','lan4','wan')},'AP2 wired state changed'
    epoch.before_traffic(before)
    server='/tmp/xr-ap24-load-'+diag[:8]+'-'+str(index)+'.json';exitfile=server+'.exit'
    c1=connect(1)
    try:
     sockets=read(c1,'cat /proc/net/tcp /proc/net/tcp6').upper()
     assert not re.search(r':14C7\s+\S+\s+0A\s',sockets),'Test port is already listening'
     assert absent(c1,server) and absent(c1,exitfile)
     command(c1,"sh -c 'timeout 18 iperf3 -s -1 -B 192.168.10.3 -p 5319 -J >"+server+" 2>&1; printf \"%s\\n\" \"$?\" >"+exitfile+"' </dev/null >/dev/null 2>&1 &")
    finally:c1.close()
    time.sleep(.5);c2=connect(2)
    try:data,error,client_code=command(c2,'timeout 15 iperf3 -c 192.168.10.3 -B 192.168.10.4 -p 5319 -t 8 -P 2 -b 100M -J'+(' -R' if reverse else ''),timeout=25,check=False)
    finally:c2.close()
    (out/('client-'+str(index)+'.json')).write_bytes(data);(out/('client-'+str(index)+'.stderr')).write_bytes(error)
    c1=connect(1)
    try:
     for attempt in range(10):
      if not absent(c1,exitfile):break
      time.sleep(.2)
     server_data=command(c1,'cat '+server)[0];server_code=int(read(c1,'cat '+exitfile));(out/('server-'+str(index)+'.json')).write_bytes(server_data)
     command(c1,'rm '+server+' '+exitfile)
    finally:c1.close()
    after=snapshot(diag);save('after-'+str(index)+'.json',after)
    if fault_event.is_set():epoch.reject('asynchronous first fault invalidates transfer')
    case=epoch.qualify(after,json.loads(data),json.loads(server_data),client_code,server_code,duration=8,reverse=reverse)
    case.update(reverse=reverse,tcpPacingMbpsPerStream=100);traffic.append(case);save('traffic.json',traffic);print(json.dumps({'transfer':case}),flush=True)
  except Exception as error:
   if epoch:
    epoch.aborted=True
    for case in epoch.cases:case['qualified']=False
   traffic.append({'qualified':False,'error':type(error).__name__,'reason':str(error)[:180]});save('traffic.json',traffic)
   print(json.dumps({'trafficStopped':type(error).__name__}),flush=True)
  # Leave recovery to the independent process. It preserves fault tail or
  # expires normally; no second host reboot and no persistent module options.
 except AssertionError:raise
 except Exception as error:
  if time.monotonic()-last_notice>30:print(json.dumps({'waitingForRecovery':type(error).__name__}),flush=True);last_notice=time.monotonic()
 finally:
  if c:c.close()
  time.sleep(5)
stop_event.set()
if monitor:monitor.join(timeout=20)
assert recovered and diag,'Recovery not observed within bound; inspect live handle and paths, never repeat activation'
c=connect(1)
try:
 assert boot(c)==recovered;preservation(c);kernel=read(c,'dmesg');assert not kernel_findings(kernel);(out/'ordinary-kernel.txt').write_text(kernel)
 record='/root/xr-diag-journal/'+diag;saved={}
 for name in ('armed.json','ready.json','activation-requested.json','activation-failed.json','module-enabled.json','aborted.json','recovery.json','capture/started.json','capture/ready.json','capture/fault.json','capture/closed.json'):
  value=data_json(c,record+'/'+name)
  if value is not None:saved[name]=value;save(name.replace('/','-'),value)
 capture,_,capture_code=command(c,'cat '+record+'/capture/kernel.kmsg',check=False)
 if capture_code==0:(out/'capture-kernel.kmsg').write_bytes(capture)
 fault,_,code=command(c,'cat '+record+'/capture/first-fault.kmsg',check=False)
 if code==0:(out/'first-fault.kmsg').write_bytes(fault);fault_event.set()
 metadata,_,metadata_code=command(c,'cat '+record+'/fault-token-metadata.txt',check=False)
 if metadata_code==0:(out/'fault-token-metadata.txt').write_bytes(metadata)
 addresses,_,addresses_code=command(c,'cat '+record+'/fault-npu-addresses.txt',check=False)
 if addresses_code==0:(out/'fault-npu-addresses.txt').write_bytes(addresses)
 assert absent(c,'/sys/module/xr_npu_addresses') and absent(c,'/sys/kernel/debug/xr_npu_addresses')
 closed=saved.get('capture/closed.json',{})
 capture_complete=(closed.get('bootID')==diag and type(closed.get('records')) is int and
  type(closed.get('lastSeq')) is int and closed.get('firstSeq')==0 and
  closed['records']==closed['lastSeq']+1 and closed.get('gaps')==0 and
  all(closed.get(key) is False for key in ('fault','failed','capped')))
 if closed.get('fault') is True:fault_event.set()
 if fault_event.is_set() or not capture_complete or saved.get('aborted.json',{}).get('reason') not in (None,'deadline'):
  if epoch:
   for case in epoch.cases:case['qualified']=False;case['kernelEpochClean']=False
 save('traffic.json',traffic)
 assert all(absent(c,p) for p in requests) and all(v=='N' for v in params(c).values())
 for p,h in state['expectedFiles'].items():assert read(c,'sha256sum '+p).split()[0]==h
 command(c,'rm '+' '.join([*links,*items]));command(c,'sync');preservation(c)
 assert all(absent(c,p) for p in [*links,*items,*requests]);save('recovered.json',{'bootID':recovered,'diagnosticBoot':diag,'parametersOff':True,'temporaryToolsRemoved':True})
finally:c.close()
until=time.monotonic()+300
while time.monotonic()<until:
 health={str(u):a.health(u,VERSION) for u in (1,2)}
 if all(x['healthy'] for x in health.values()):break
 print(json.dumps({'waitingForOrdinaryRadios':{u:h['checks'] for u,h in health.items()}}),flush=True);time.sleep(15)
else:raise RuntimeError('Ordinary radio recovery incomplete')
c=connect(2)
try:assert boot(c)==ap2_before['bootID'] and a.preservation(c)==ap2_before['preservation'] and all(v=='N' for v in params(c).values())
finally:c.close()
report={'at':datetime.now().astimezone().isoformat(),'operationCompletedAndRecovered':True,'version':VERSION,
 'captureContinuousAndComplete':capture_complete,
 'bothBoundedTransfersQualified':capture_complete and len(traffic)==2 and all(x.get('qualified') is True for x in traffic),
 'NpuBootParameterEnabled':bool(saved.get('module-enabled.json')),
 'NpuDriverActiveObserved':(out/'activation-observed.json').exists(),
 'AP24OwnershipFixTrial':True,'originalNpuFirmwareUnchanged':True,'NpuDriverActiveRecordedAtFault':b'npu_active=1' in metadata,'metadataReadCompleted':b'snapshot_status=complete' in metadata,'kernelFaultObserved':fault_event.is_set(),
 'historicalNpuRootCauseProven':False,'NpuHardwareQualificationPassed':False,
 'addressReadCompleted':b'snapshot_status=complete' in addresses,'addressObserverRemovedAfterOrdinaryBoot':True,
 'traffic':traffic,'ordinaryRecoveryAndCleanupPassed':True,'bothHealthy':True,'health':health,
 'AP2SameBootAndNpuOff':True,'allConfigurationRootKeysAndCriticalHashesPreserved':True,'phoneTested':False,
 'mainRouterSwitchWindowsNetworkOriginalDebianChanged':False,'rawNandConfigKeysPCAPBackupsCreated':False}
save('result.json',report);state['status']='completed-recovered-cleaned';save('operation.json',state);print(json.dumps(report),flush=True)
