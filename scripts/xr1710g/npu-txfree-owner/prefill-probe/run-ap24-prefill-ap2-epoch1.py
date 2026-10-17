"""One AP2 NPU boot with recovery5/activation3 and qualified AP2 role helpers.

Owner explicitly accepts Mesh-only remote loss. No traffic generator, no AP1
mutation, no persistent NPU option. Never rerun a submitted epoch.
"""
from pathlib import Path
from datetime import datetime
import hashlib,importlib.util,json,re,shlex,time,sys
from xr_two_ap import WORKSPACE as w,connect,command

spec=importlib.util.spec_from_file_location('checks',Path(__file__).with_name('ap22-upgrade-common.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
VERSION='20261010-ap24-d331711d';a.base.VERSION=VERSION
a.base.connect=lambda unit,via=None:connect(unit,via='lan')
base=w/'development/npu-ap2-debugfs';out=w/'development/ap24/prefill-probe/ap2-epoch1';out.mkdir(exist_ok=True)
operation=out/'operation.json';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
readjson=lambda p:json.loads(p.read_text())
items={'/usr/libexec/xr-recovery-once':base/'recovery/files/xr-recovery-once',
       '/usr/libexec/xr-npu-guarded-once':base/'activation/files/xr-npu-guarded-once'}
requests={'/etc/xr-recovery.once':'xr-recovery-v1','/etc/xr-npu-guarded.once':'xr-npu-guarded-v1'}
def save(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def read(c,cmd):return command(c,cmd)[0].decode().strip()
def boot(c):return read(c,'cat /proc/sys/kernel/random/boot_id')
def absent(c,path):return command(c,'test ! -e '+shlex.quote(path)+' && test ! -L '+shlex.quote(path),check=False)[2]==0
def journals(c):return set(x for x in command(c,'ls -1 /root/xr-diag-journal',check=False)[0].decode().splitlines() if re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',x))
def put(c,path,data,mode):
    temp=path+'.ap2-diag-new'
    assert absent(c,temp)
    stdin,stdout,stderr=c.exec_command('umask 077; set -C; cat > '+shlex.quote(temp),timeout=60)
    stdin.channel.sendall(data);stdin.channel.shutdown_write();stdout.read();error=stderr.read()
    assert stdout.channel.recv_exit_status()==0,error
    command(c,'chmod '+mode+' '+shlex.quote(temp)+' && mv '+shlex.quote(temp)+' '+shlex.quote(path))
    assert read(c,'sha256sum '+shlex.quote(path)).split()[0]==hashlib.sha256(data).hexdigest()

assert len(sys.argv)==2 and sys.argv[1]=='run' and not operation.exists()
assert readjson(w/'development/ap24/prefill-probe/deployment/ap2-trace/result.json')['passed']
vm=readjson(base/'activation/vm/result-latest.json')
assert vm['passed'] and {x['case'] for x in vm['cases']}=={'success','fault','producer-wrong-code'}
for case in vm['cases']:
    assert case['sourceSHA256']==sha(base/'activation/src/activate.c')
    assert case['guardSHA256']==sha(base/'recovery/src/recovery.c')
    assert case['helperSHA256']==sha(base/'activation/files/xr-npu-guarded-once')
for role,count in (('activation',23),('recovery',12)):
    qa=readjson(base/role/'shipped-shell-qa.json');assert qa['passed'] and len(qa['checks'])==count
    assert qa['helperSHA256']==sha(items['/usr/libexec/'+('xr-npu-guarded-once' if role=='activation' else 'xr-recovery-once')])
assert all(a.health(u,VERSION)['healthy'] for u in (1,2))
c1=connect(1,via='lan')
try:peer={'bootID':boot(c1),'preservation':a.preservation(c1)}
finally:c1.close()
c=connect(2,via='lan')
try:
    assert a.identity(c,2)['release']['version']==VERSION
    assert read(c,'cat /sys/module/mt76/parameters/npu_enable')=='N'
    assert all(absent(c,p) for p in requests)
    assert absent(c,'/sys/module/xr_npu_producer') and absent(c,'/sys/module/xr_npu_addresses')
    assert not re.search(r'WARNING:|BUG:|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated',read(c,'dmesg'))
    watchdog=json.loads(read(c,"ubus call system watchdog '{}'"))
    assert watchdog['status']=='running' and watchdog['timeout']==30 and not watchdog['magicclose']
    old=boot(c);paths=read(c,'sysupgrade -l').splitlines()
    shipped=readjson(w/'development/ap24/prefill-probe/result.json')['changedFiles']
    required={p:entry['sha256'] for p,entry in shipped.items() if 'sha256' in entry}
    assert a.file_hashes(c,['/'+p for p in required])=={'/'+p:h for p,h in required.items()}
    state={'at':datetime.now().astimezone().isoformat(),'status':'prepared','unit':2,'bootBefore':old,
           'previousJournals':sorted(journals(c)),'preservationBefore':a.preservation(c),'preservedFiles':a.file_hashes(c,paths),
           'AP1Before':peer,'deadlineSeconds':180,'AP2HelperAndEarlyDebugfsMountQualified':True,'helperHashes':{p:sha(s) for p,s in items.items()},
           'ownerAcceptedNoIndependentRecovery':True,'noTrafficGenerator':True,'snapshotPayloadsForbidden':True}
    save('operation.json',state)
    for path,source in items.items():put(c,path,source.read_bytes(),'755')
    for path,prefix in requests.items():put(c,path,(prefix+' '+old+'\n').encode(),'600')
    for service in ('xr_diag_recovery','xr_guarded_npu'):
        assert read(c,'readlink /etc/rc.d/S08'+service)=='../init.d/'+service
        command(c,'/etc/init.d/'+service+' boot')
    assert journals(c)==set(state['previousJournals']) and all(not absent(c,p) for p in requests)
    assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,paths)==state['preservedFiles']
    command(c,'sync');state['status']='reboot-submitted-once';save('operation.json',state)
    command(c,"sh -c 'sleep 2; sync; reboot' </dev/null >/tmp/xr-ap2-producer-epoch.log 2>&1 &")
    print('AP2_PRODUCER_DIAGNOSTIC_EPOCH_SUBMITTED_ONCE',flush=True)
finally:c.close()
time.sleep(12)
deadline=time.monotonic()+660;diagnostic=None;returned=None;last_notice=0
while time.monotonic()<deadline:
    c=None
    try:
        c=connect(2,via='lan');current=boot(c)
        if current==old:
            time.sleep(3);continue
        added=journals(c)-set(state['previousJournals'])
        assert len(added)==1,('Expected one diagnostic journal',sorted(added))
        diagnostic=next(iter(added));record='/root/xr-diag-journal/'+diagnostic
        if current!=diagnostic:
            assert read(c,'cat /sys/module/mt76/parameters/npu_enable')=='N'
            assert all(absent(c,p) for p in requests)
            returned=current;break
        # Only scalar/log observations; no traffic or state changes in active boot.
        if not (out/'active-observation.json').exists():
            (out/'active-kernel.txt').write_bytes(command(c,'dmesg')[0])
            before_boot=boot(c);before_ms=int(float(read(c,'cat /proc/uptime').split()[0])*1000)
            data,error,code=command(c,'timeout 3 cat /sys/kernel/debug/xr_npu_producer/snapshot',timeout=6,check=False)
            after_ms=int(float(read(c,'cat /proc/uptime').split()[0])*1000);after_boot=boot(c)
            observation={'bootBefore':before_boot,'bootAfter':after_boot,'monotonicMsBefore':before_ms,'monotonicMsAfter':after_ms,
                         'readCode':code,'npuEnable':read(c,'cat /sys/module/mt76/parameters/npu_enable')}
            (out/'active-producer.txt').write_bytes(data);(out/'active-producer.stderr').write_bytes(error)
            save('active-observation.json',observation)
            from xr_npu_producer_trace import parse_live_snapshot
            parsed=parse_live_snapshot(data,observation)
            save('live-producer-parsed.json',parsed)
            print(json.dumps({'producerRows':len(parsed['rows']),'poolMismatches':sum(not x['poolPointerMatchesDescriptor'] for x in parsed['rows']),
                              'shortFrames':sum(x['sourceShorterThanAnnounced'] for x in parsed['rows'])}),flush=True)
        if time.monotonic()-last_notice>25:
            scalars=command(c,'for p in /sys/kernel/debug/ieee80211/phy*/mt76/xr_token_info; do test ! -f "$p" || cat "$p"; done')[0]
            (out/'latest-active-token.txt').write_bytes(scalars)
        if time.monotonic()-last_notice>25:
            print(json.dumps({'diagnosticBoot':diagnostic,'waitingForIndependentRecovery':True}),flush=True);last_notice=time.monotonic()
    except AssertionError:raise
    except Exception as e:
        if time.monotonic()-last_notice>25:
            print(json.dumps({'awaitingRecovery':type(e).__name__}),flush=True);last_notice=time.monotonic()
    finally:
        if c:c.close()
    time.sleep(5)
assert returned and diagnostic,'No ordinary boot return; do not re-arm'
c=connect(2,via='lan')
try:
    record='/root/xr-diag-journal/'+diagnostic
    saved={}
    for name in ('armed.json','ready.json','activation-requested.json','module-enabled.json','activation-failed.json',
                 'aborted.json','recovery.json','capture/ready.json','capture/fault.json','capture/closed.json'):
        data,error,code=command(c,'cat '+record+'/'+name,check=False)
        if code==0:
            saved[name]=json.loads(data);(out/name.replace('/','-')).write_bytes(data)
    for name in ('fault-token-metadata.txt','fault-npu-addresses.txt','fault-npu-producer.txt',
                 'capture/first-fault.kmsg','capture/kernel.kmsg'):
        data,error,code=command(c,'cat '+record+'/'+name,check=False)
        if code==0:(out/name.replace('/','-')).write_bytes(data)
    assert a.preservation(c)==state['preservationBefore'] and a.file_hashes(c,list(state['preservedFiles']))==state['preservedFiles']
    kernel=command(c,'dmesg')[0];(out/'ordinary-kernel.txt').write_bytes(kernel)
    assert not re.search(rb'WARNING:|BUG:|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated',kernel)
    # Restore only the two owned helpers from exact shipped ROM files. Requests already consumed; no kmod override remains.
    for path in items:
        assert read(c,'sha256sum '+path).split()[0]==state['helperHashes'][path]
        overlay='/overlay/upper'+path
        assert read(c,'sha256sum '+overlay).split()[0]==state['helperHashes'][path]
        # Copy the ROM helper rather than removing a live overlay inode directly.
        command(c,'cp /rom'+path+' '+path)
        assert read(c,'sha256sum '+path).split()[0]==shipped[path.lstrip('/')]['sha256']
    assert all(absent(c,p) for p in requests)
    assert absent(c,'/sys/module/xr_npu_producer') and absent(c,'/sys/module/xr_npu_addresses')
    command(c,'sync')
finally:c.close()
radio_deadline=time.monotonic()+240
while time.monotonic()<radio_deadline:
    health=a.health(2,VERSION)
    save('ordinary-radio-readiness.json',health)
    if health['healthy']:break
    print(json.dumps({'waitingForRadios':health['checks']}),flush=True);time.sleep(12)
assert health['healthy']
c1=connect(1,via='lan')
try:assert boot(c1)==peer['bootID'] and a.preservation(c1)==peer['preservation']
finally:c1.close()
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'unit':2,'diagnosticBootID':diagnostic,'ordinaryBootID':returned,
        'activationObserved':'module-enabled.json' in saved,'faultObserved':'capture/fault.json' in saved,
        'activationFailure':saved.get('activation-failed.json'),'ordinaryRecoveryAndCleanupPassed':True,
        'preservedFileCount':len(state['preservedFiles']),'AP1SameBootAndConfiguration':True,'health':health,
        'historicalRootCauseFixed':False,'saved':saved}
save('result.json',report);state['status']='completed-recovered';save('operation.json',state)
print(json.dumps(report),flush=True)
