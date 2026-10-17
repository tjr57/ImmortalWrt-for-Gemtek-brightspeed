"""Own AP28 Mesh diagnostic: bounded headers, RX reasons, no traffic payloads."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib,json,re,time
from xr_two_ap import WORKSPACE,connect,command
from ap27_forwarding_observer import ready,sample_pair
out=WORKSPACE/'development/ap28/forwarding/software-mesh-reasons1';assert not out.exists();out.mkdir(parents=True)
save=lambda n,v:(out/n).write_text(json.dumps(v,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files={'/tmp/xr-ap28-ping-receive-observer.so':WORKSPACE/'development/ap27/tools/ping-receive-observer.so','/tmp/xr-ap28-clock':WORKSPACE/'development/ap27/tools/clock-pair'}
for path,p in files.items():
    proof='ping-observer-build.json' if p.suffix=='.so' else 'clock-pair-build.json'
    assert sha(p)==json.loads((p.parent/proof).read_text())['binarySHA256']
deadline=time.monotonic()+120;settled=None
while time.monotonic()<deadline:
    initial=sample_pair();good=all(ready(r,int(u)) for u,r in initial.items())
    if good:
        if settled is None:settled=time.monotonic()
        if time.monotonic()-settled>=8:break
    else:settled=None
    time.sleep(3)
assert good and settled is not None and time.monotonic()-settled>=8,'Steady topology not confirmed'
save('before.json',initial)
clients={};owned=[];enabled=[];rounds=[];captures={};pool=ThreadPoolExecutor(max_workers=12)
param='/sys/module/mac80211/parameters/mesh_rx_drop_audit'
counter_script='''printf 'CLOCK '; /tmp/xr-ap28-clock
cat /proc/uptime
cat /sys/module/mac80211/parameters/mesh_rx_drop_events
ethtool -S mesh6g
iw dev mesh6g station dump
iw dev mesh6g mpath dump
for p in /sys/kernel/debug/ieee80211/phy0/netdev:mesh6g/mesh_stats/*; do printf '%s=' "$p"; cat "$p"; done
'''
def counters(unit):return command(clients[unit],counter_script)[0].decode()
def capture(unit,iface):
    c=connect(unit,via='lan');f='icmp and host 192.168.10.3 and host 192.168.10.4'
    if iface=='mesh6g':f='('+f+') or (vlan and '+f+')'
    try:return command(c,f"timeout 105 tcpdump -p -l -nn -e -tt -s 96 -i {iface} '{f}'",timeout=115,check=False)
    finally:c.close()
try:
    for unit in [1,2]:
        c=clients[unit]=connect(unit,via='lan')
        assert command(c,'cat /etc/openwrt_version')[0].strip()==b'20261010-ap28-d331711d'
        assert command(c,'cat /sys/module/mt76/parameters/npu_enable')[0].strip()==b'N'
        assert command(c,'cat '+param)[0].strip()==b'N'
        for path,p in files.items():
            if unit==2 and p.suffix=='.so':continue
            assert command(c,'test ! -e '+path+' && test ! -L '+path,check=False)[2]==0
            i,o,e=c.exec_command('umask 077; set -C; cat > '+path);i.channel.sendall(p.read_bytes());i.channel.shutdown_write();o.read();assert o.channel.recv_exit_status()==0
            owned.append((unit,path));assert command(c,'sha256sum '+path)[0].decode().split()[0]==sha(p);command(c,'chmod 700 '+path)
        command(c,'echo Y > '+param);enabled.append(unit);assert command(c,'cat '+param)[0].strip()==b'Y'
    for unit in [1,2]:
        for iface in ['br-lan.1','mesh6g']:captures[f'ap{unit}-{iface}-headers']=pool.submit(capture,unit,iface)
    def sample_events(unit):
        client=connect(unit,via='lan')
        try:return command(client,"for i in $(seq 1 100); do printf 'CLOCK '; /tmp/xr-ap28-clock; cat /sys/module/mac80211/parameters/mesh_rx_drop_events; sleep 1; done",timeout=115,check=False)
        finally:client.close()
    for unit in [1,2]:captures[f'ap{unit}-event-samples']=pool.submit(sample_events,unit)

    before=dict(zip(['1','2'],pool.map(counters,[1,2])));time.sleep(1);start=time.monotonic()
    for index in range(16):
        assert time.monotonic()-start<90
        row={'index':index,'at':datetime.now().astimezone().isoformat(),'countersBefore':before,'probes':{}}
        prefix='LD_PRELOAD=/tmp/xr-ap28-ping-receive-observer.so XR_PING_RXBUF=0 /bin/ping -I br-lan.1 -i 1 -c 5 -W 1 '
        jobs={name:pool.submit(command,clients[1],prefix+ip,timeout=12,check=False) for name,ip in {**{'peer'+str(i):'192.168.10.4' for i in range(4)},'gateway':'192.168.10.1'}.items()}
        for name,job in jobs.items():
            d,e,x=job.result();m=re.search(rb'(\d+) packets transmitted, (\d+) packets received',d);assert m
            assert b'requested=65536 applied=65536 effective=131072' in e and b'RX_OBSERVER_ERROR' not in e
            row['probes'][name]={'sent':int(m[1]),'received':int(m[2]),'code':x,'stdout':d.decode(),'socketAccounting':e.decode()}
        row['countersAfter']=dict(zip(['1','2'],pool.map(counters,[1,2])));before=row['countersAfter'];rounds.append(row);save('rounds.json',rounds)
        print(json.dumps({'round':index,'pings':{n:[p['sent'],p['received']] for n,p in row['probes'].items()}}),flush=True)
finally:
    for unit in enabled:
        command(clients[unit],'echo N > '+param);assert command(clients[unit],'cat '+param)[0].strip()==b'N'
    for name,task in captures.items():
        d,e,x=task.result();(out/(name+'.txt')).write_bytes(d);(out/(name+'.stderr')).write_bytes(e)
    for unit,path in owned:
        c=clients[unit];assert command(c,'sha256sum '+path)[0].decode().split()[0]==sha(files[path]);command(c,'rm -- '+path)
    for c in clients.values():c.close()
    pool.shutdown(wait=True);save('cleanup.json',{'allOwnedHelpersRemoved':True,'observersDisabled':True})
after=sample_pair();save('after.json',after)
assert all(ready(r,int(u)) and r['bootID']==initial[u]['bootID'] for u,r in after.items())
assert all(b'0 packets dropped by kernel' in p.read_bytes() for p in out.glob('*-headers.stderr'))
save('result.json',{'completed':True,'rounds':len(rounds),'NpuOff':True,'sameBoot':True,'configurationUnchanged':True,'observersDisabled':True,'temporaryHelpersRemoved':True})
