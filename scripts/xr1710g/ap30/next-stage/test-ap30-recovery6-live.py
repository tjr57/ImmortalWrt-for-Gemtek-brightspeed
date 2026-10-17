"""One AP1 NPU-off diagnostic reboot, automatic ordinary recovery, owned cleanup."""
from pathlib import Path
from datetime import datetime
import sys,json,hashlib,importlib.util,re,time,shlex
from xr_two_ap import WORKSPACE,connect,command
spec=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
VERSION='20261010-ap30-d331711d';a.base.VERSION=VERSION;a.base.connect=lambda unit,**kw:connect(unit,via="lan")
base=WORKSPACE/'development/npu-recovery6';out=WORKSPACE/'development/ap30/recovery6-live1';out.mkdir(exist_ok=True)
journal=out/'operation.json';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
items={'/usr/libexec/xr-diag-capture':base/'xr-diag-capture','/usr/libexec/xr-diag-recovery':base/'xr-diag-recovery',
 '/usr/libexec/xr-recovery-once':base/'files/xr-recovery-once','/etc/init.d/xr_diag_recovery':base/'files/xr_diag_recovery'}
link='/etc/rc.d/S08xr_diag_recovery';request='/etc/xr-recovery.once'
def save(name,data):(out/name).write_text(json.dumps(data,indent=2)+'\n')
def read(c,cmd):return command(c,cmd)[0].decode().strip()
def absent(c,path):return command(c,'test ! -e '+shlex.quote(path)+' && test ! -L '+shlex.quote(path),check=False)[2]==0
def boot(c):return read(c,'cat /proc/sys/kernel/random/boot_id')
def clean(c):
 s=read(c,'dmesg');assert not re.search(r'WARNING:|BUG:|kernel BUG|Call [Tt]race:|Oops:|Internal error:|Kernel panic|Unable to handle kernel|KASAN:|TXFREE truncated',s)
 return s
def get_json(c,path):
 data,_,code=command(c,'cat '+shlex.quote(path),check=False)
 return json.loads(data) if code==0 else None
def original(c,state):
 assert a.identity(c,1)['release']['version']==VERSION
 assert a.preservation(c)==state['preservationBefore']
 assert a.file_hashes(c,list(state['preservedFiles']))==state['preservedFiles']
def params(c):
 paths={'wlanNpu':'/sys/module/mt76/parameters/npu_enable','audit':'/sys/module/mt76/parameters/npu_rx_audit',
  'npuChain':'/sys/module/mt76/parameters/npu_txfree_chain_verify','ppe':'/sys/module/airoha_eth/parameters/ppe_bind_enable',
  'bridgePpe':'/sys/module/airoha_eth/parameters/ppe_bridge_bind_enable','puncturing':'/sys/module/mt7996e/parameters/puncturing_enable',
  'stats':'/sys/module/mt7996e/parameters/mcu_stats_enable','airtime':'/sys/module/mt7996e/parameters/mcu_airtime_cumulative_us'}
 result={n:read(c,'cat '+p) for n,p in paths.items()};assert all(v=='N' for v in result.values());return result
def put(c,path,data):
 stdin,stdout,stderr=c.exec_command('umask 077; set -C; cat > '+shlex.quote(path),timeout=60)
 stdin.channel.sendall(data);stdin.channel.shutdown_write();stdout.read();error=stderr.read();assert stdout.channel.recv_exit_status()==0,error
 command(c,'chmod 700 '+shlex.quote(path))

assert len(sys.argv)==2 and sys.argv[1]=='run'
assert not journal.exists(),'One-shot journal exists; inspect state/handle instead of repeating'
build=json.loads((base/'package-build.json').read_text());vm=json.loads((base/'vm/result-latest.json').read_text());arm=json.loads((base/'arm-qa.json').read_text());shell=json.loads((base/'shipped-shell-qa-ap30.json').read_text())
assert all(x['passed'] for x in (build,vm,arm,shell)) and len(vm['cases'])==18
for case in vm['cases']:
 assert case['sourceSHA256']==sha(base/'src/recovery.c') and case['captureSHA256']==sha(base/'src/capture.c')
 assert case['helperSHA256']==sha(base/'files/xr-recovery-once')
for name,h in build['binaries'].items():assert sha(base/name)==h
source=Path(r'\\wsl.localhost\Debian-XR1710G\home\xrdev\projects\xr1710g\openwrt\package\network\config\xr1710g-diag-recovery')
for name,h in build['sourceHashes'].items():
 assert sha(base/name)==h and sha(source/name)==h
assert shell['helperSHA256']==sha(base/'files/xr-recovery-once')
assert arm['programs']['recovery']['sourceSHA256']==sha(base/'src/recovery.c')
assert arm['programs']['capture']['sourceSHA256']==sha(base/'src/capture.c')
completion=json.loads((WORKSPACE/'development/ap30/forwarding-completion.json').read_text())
assert completion['passed'] and completion['bothAP2ThenAP1UpgradedAndHealthy']
def runtime(c,unit):
 expected=completion['finalLive'][str(unit)]['runtimeHashes']
 assert a.file_hashes(c,['/'+p for p in expected])=={'/'+p:h for p,h in expected.items()}
 assert read(c,'sha256sum /etc/rc.common').split()[0]=='dd8ae95c78d10cccf78cb487874f163ace4c1ee14dace05fe28393b19ba639e4'

health={str(u):a.health(u,VERSION) for u in (1,2)};assert all(h['healthy'] for h in health.values())
c2=connect(2,via='lan')
try:ap2_boot=boot(c2);clean(c2);runtime(c2,2);ap2_preservation=a.preservation(c2)
finally:c2.close()
c=connect(1,via='lan')
try:
 clean(c);params(c);runtime(c,1);old=boot(c)
 for p in [*items,link,request,'/root/xr-diag-journal']:assert absent(c,p),p
 assert absent(c,'/etc/xr-kmsg-capture.once')
 assert read(c,'sha256sum /bin/busybox').split()[0]==shell['busyBoxSHA256']
 wd=json.loads(read(c,"ubus call system watchdog '{}'"));assert wd['status']=='running' and wd['timeout']==30 and not wd['magicclose']
 paths=read(c,'sysupgrade -l').splitlines()
 state={'status':'prepared-before-write','at':datetime.now().astimezone().isoformat(),'version':VERSION,
  'bootBefore':old,'AP2BootBefore':ap2_boot,'AP2Preservation':ap2_preservation,'preservationBefore':a.preservation(c),
  'preservedFiles':a.file_hashes(c,paths),'expectedFiles':{p:sha(src) for p,src in items.items()},
  'NpuEnabled':False,'kernelFaultWillBeInjected':False,'VMGatePassed':True,'ordinaryRecoveryDeadlineSeconds':180}
 save('operation.json',state)
 for path,source in items.items():put(c,path,source.read_bytes());assert read(c,'sha256sum '+path).split()[0]==sha(source)
 assert command(c,'/usr/libexec/xr-diag-recovery',check=False)[2]==2
 assert command(c,'/usr/libexec/xr-diag-capture',check=False)[2]==2
 command(c,'/etc/init.d/xr_diag_recovery enable');assert read(c,'readlink '+link)=='../init.d/xr_diag_recovery'
 put(c,request,('xr-recovery-v1 '+old+'\n').encode());command(c,'chmod 600 '+request)
 command(c,'/etc/init.d/xr_diag_recovery boot');assert absent(c,'/root/xr-diag-journal') and not absent(c,request)
 command(c,'sync');original(c,state)
 state['status']='reboot-issued-once';state['rebootAt']=datetime.now().astimezone().isoformat();save('operation.json',state)
 command(c,"sh -c 'sleep 2; sync; reboot' </dev/null >/tmp/xr-recovery-baseline-reboot.log 2>&1 &")
 print('AP1_NPU_OFF_RECOVERY_QUALIFICATION_STARTED_ONCE',flush=True)
finally:c.close()
deadline=time.monotonic()+660;observed=None;recovered=None;last_notice=0
while time.monotonic()<deadline:
 c=None
 try:
  c=connect(1,via='lan');current=boot(c)
  if current==old:
   time.sleep(2);continue
  sampled=time.monotonic();uptime=float(read(c,'cat /proc/uptime').split()[0]);origin=sampled-uptime
  if observed is None:
   record='/root/xr-diag-journal/'+current
   captured=get_json(c,record+'/capture/ready.json');guard=get_json(c,record+'/ready.json');armed=get_json(c,record+'/armed.json')
   assert captured and guard and armed,'Early diagnostic was not observed; inspect persisted journal, do not repeat reboot'
   assert captured['bootID']==guard['bootID']==armed['bootID']==current and guard['collectorPID']==captured['pid']
   assert not captured['gaps'] and not captured['fault'] and not captured['failed'] and not captured['capped'] and captured['firstSeq']==0
   assert absent(c,request) and absent(c,record+'/aborted.json') and absent(c,record+'/capture/fault.json') and absent(c,record+'/capture/closed.json')
   assert guard['deadlineMs']-armed['monotonicMs']<=180000 and guard['deadlineMs']>uptime*1000
   for label,pid in [('guard',guard['pid']),('deadline',guard['deadlinePID']),('capture',guard['collectorPID'])]:
    assert type(pid) is int and pid>1
    cmd=command(c,'cat /proc/'+str(pid)+'/cmdline')[0]
    assert record.encode() in cmd
    proc=read(c,'cat /proc/'+str(pid)+'/stat').rsplit(') ',1)[1].split();assert proc[0]!='Z'
    if label=='deadline':assert int(proc[1])==guard['pid']
   kernel=clean(c);(out/'diagnostic-boot-kernel.txt').write_text(kernel+'\n')
   modules=[float(x) for x in re.findall(r'\[\s*([0-9.]+)\] kmodloader: loading kernel modules from /etc/modules.d/',kernel)]
   assert modules and captured['monotonicMs']<min(modules)*1000 and guard['monotonicMs']<min(modules)*1000
   original(c,state);parameters=params(c)
   observed={'bootID':current,'record':record,'captureReady':captured,'guardReady':guard,'armed':armed,
    'observedUptime':uptime,'kernelBootHostMonotonicEstimate':origin,'moduleLoadTimes':modules,
    'readyBeforeModules':True,'independentDeadlineProcessObserved':True,'parameters':parameters}
   save('observation.json',observed);state['status']='diagnostic-boot-observed';state['diagnosticBoot']=current;save('operation.json',state)
   print(json.dumps({'diagnosticBootObserved':True,'readyBeforeModules':True,'NpuEnabled':False,'secondsRemaining':round(guard['deadlineMs']/1000-uptime)}),flush=True)
  elif current!=observed['bootID']:
   original(c,state);clean(c);parameters=params(c);assert absent(c,request)
   record=observed['record'];assert absent(c,'/root/xr-diag-journal/'+current)
   notes={n:get_json(c,record+'/'+n+'.json') for n in ('armed','ready','aborted','recovery')}
   assert notes['armed']
   for name in ('armed','aborted','recovery'):
    assert notes[name] and notes[name]['bootID']==observed['bootID']
   for name in ('aborted','recovery'):
    assert notes[name]['reason']=='deadline'
   assert 7000<=notes['recovery']['deadlineMs']-notes['recovery']['monotonicMs']<=11000

   assert absent(c,record+'/capture/fault.json')
   closed=get_json(c,record+'/capture/closed.json')
   assert closed and closed['bootID']==observed['bootID']
   assert closed['gaps']==0 and not closed['failed'] and not closed['fault'] and not closed['capped']
   assert closed['firstSeq']==0 and closed['records']==closed['lastSeq']+1
   assert notes['aborted']['monotonicMs']<=closed['monotonicMs']<=notes['recovery']['monotonicMs']
   assert closed['written']==0 and absent(c,record+'/capture/kernel.kmsg')
   save('collector-closed.json',closed)

   expect_origin=observed['kernelBootHostMonotonicEstimate']+notes['recovery']['monotonicMs']/1000
   delta=origin-expect_origin;assert -5<=delta<=60,('unexpected automatic reboot timing',delta)
   recovered={'bootID':current,'priorBootID':observed['bootID'],'version':VERSION,'automaticRecovery':True,
    'newKernelBootRelativeToOrderlyRecoverySeconds':delta,'requestConsumedAndSecondBootIdle':True,'parameters':parameters,
    'metadataPersisted':notes,'configurationRootKeysAndCriticalHashesPreserved':True}
   save('recovered.json',recovered);state['status']='ordinary-recovery-observed';state['ordinaryBoot']=current;save('operation.json',state)
   print(json.dumps({'ordinaryAutomaticRecoveryObserved':True,'NpuEnabled':False,'orderlyRecoveryToNewKernelSeconds':round(delta,2)}),flush=True);break
 except AssertionError:raise
 except Exception as error:
  if time.monotonic()-last_notice>30:print(json.dumps({'waitingForAutomaticRecovery':type(error).__name__}),flush=True);last_notice=time.monotonic()
 finally:
  if c:c.close()
 time.sleep(6)
assert observed and recovered,'Bounded observation incomplete; never repeat reboot automatically'
limit=time.monotonic()+300
while time.monotonic()<limit:
 health={str(u):a.health(u,VERSION) for u in (1,2)}
 if all(x['healthy'] for x in health.values()):break
 print(json.dumps({'waitingForRadioReadiness':{u:h['checks'] for u,h in health.items()}}),flush=True);time.sleep(15)
else:raise RuntimeError('Radio readiness incomplete after automatic recovery')
c=connect(1,via='lan')
try:
 assert boot(c)==recovered['bootID'];original(c,state);clean(c);runtime(c,1)
 for path,h in state['expectedFiles'].items():assert read(c,'sha256sum '+path).split()[0]==h
 assert read(c,'readlink '+link)=='../init.d/xr_diag_recovery';assert absent(c,request)
 command(c,'rm '+link+' '+' '.join(items));command(c,'sync')
 assert all(absent(c,p) for p in [*items,link,request]);original(c,state)
 (out/'ordinary-boot-kernel.txt').write_text(clean(c)+'\n')
finally:c.close()
c=connect(2,via='lan')
try:
 assert boot(c)==ap2_boot and a.preservation(c)==ap2_preservation;clean(c);runtime(c,2)
finally:c.close()
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':VERSION,
 'AP1NpuOffOnly':True,'guardAndCaptureReadyBeforeModules':True,'independentDeadlineVerifiedLive':True,
 'automatic180SecondBoundedRecoveryToOrdinaryBoot':True,'orderlyRecoveryBeforeHardDeadline':True,'completeContinuousCollectorClosureRequiredAndObserved':True,'secondBootRequestAbsentAndIdle':True,
 'allTemporaryExecutablesAndStartupLinkRemoved':True,'configurationRootKeysCriticalHashesPreserved':True,
 'AP2SameBootAndConfiguration':True,'bothHealthy':True,'health':health,
 'liveKernelFaultInjected':False,'liveUBIFSCrashFaultRetentionProven':False,'NpuActivated':False,'phoneTested':False,
 'historicalNpuRootCauseProven':False,'recoveryBuild':build,'shippedShellQA':shell,'remainingLimits':['No real NPU fault or hard lockup induced; hardware watchdog reset itself unqualified',
  'Ordinary no-fault deadline recovery is verified; this does not establish the cause of historical NPU memory corruption']}
save('result.json',report);state['status']='accepted-cleaned';save('operation.json',state);print(json.dumps(report),flush=True)
