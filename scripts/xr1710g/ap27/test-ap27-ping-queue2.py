"""Old/new actual ARM ping under identical bounded own-process queue delay."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,time
from xr_two_ap import WORKSPACE,connect,command
from ap27_forwarding_observer import sample_pair,ready
out=WORKSPACE/'development/ap27/ping-rxbuf/live-queue2';assert not out.exists();out.mkdir()
files={'/tmp/xr-ap27-ping-queue-gate.so':WORKSPACE/'development/ap27/tools/ping-queue-gate.so','/tmp/busybox-ap27':WORKSPACE/'development/ap27/ping-rxbuf/busybox'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(files['/tmp/busybox-ap27'])==json.loads((out.parent/'build.json').read_text())['binarySHA256']
assert sha(files['/tmp/xr-ap27-ping-queue-gate.so'])==json.loads((WORKSPACE/'development/ap27/tools/ping-queue-gate-build.json').read_text())['binarySHA256']
before=sample_pair();assert all(ready(r,int(u)) for u,r in before.items())
c=connect(1,via='lan');owned=[];rows=[];pool=ThreadPoolExecutor(max_workers=8);captures={}
def capture(unit,iface):
    client=connect(unit,via='lan');f='icmp and host 192.168.10.3 and host 192.168.10.4'
    if iface=='mesh6g':f='('+f+') or (vlan and '+f+')'
    try:return command(client,f"timeout 38 tcpdump -p -l -nn -e -tt -s 96 -i {iface} '{f}'",timeout=45,check=False)
    finally:client.close()
try:
    for path,src in files.items():
        assert command(c,'test ! -e '+path+' && test ! -L '+path,check=False)[2]==0
        i,o,e=c.exec_command('umask 077; set -C; cat > '+path);i.channel.sendall(src.read_bytes());i.channel.shutdown_write();o.read();assert o.channel.recv_exit_status()==0
        owned.append(path);assert command(c,'sha256sum '+path)[0].decode().split()[0]==sha(src)
        command(c,'chmod 700 '+path)
    for unit in [1,2]:
        for iface in ['br-lan.1','mesh6g']:captures[f'ap{unit}-{iface}-headers']=pool.submit(capture,unit,iface)
    time.sleep(1)
    for index in range(4):
        mode='original' if index%2==0 else 'candidate'
        executable='/bin/ping' if mode=='original' else '/tmp/busybox-ap27 ping'
        probe=pool.submit(command,c,'LD_PRELOAD=/tmp/xr-ap27-ping-queue-gate.so '+executable+' -I br-lan.1 -i 1 -c 6 -W 1 192.168.10.4',timeout=12,check=False)
        time.sleep(.15)
        shadows=[pool.submit(command,c,'/bin/ping -I br-lan.1 -i 1 -c 3 -W 1 192.168.10.4',timeout=8,check=False) for _ in range(3)]
        data,error,code=probe.result();(out/f'round-{index}-stdout.txt').write_bytes(data);(out/f'round-{index}-stderr.txt').write_bytes(error);m=re.search(rb'(\d+) packets transmitted, (\d+) packets received',data);assert m
        row={'round':index,'mode':mode,'sent':int(m[1]),'received':int(m[2]),'stdout':data.decode(),'stderr':error.decode(),'exitCode':code,'shadowResults':[]}
        for f in shadows:
            d,e,x=f.result();row['shadowResults'].append({'stdout':d.decode(),'stderr':e.decode(),'exitCode':x})
        assert 'QUEUE_RELEASE' in row['stderr'];rows.append(row);(out/'rounds.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps({k:row[k] for k in ['round','mode','sent','received','stderr']}),flush=True)
    for name,f in captures.items():
        d,e,x=f.result();(out/(name+'.txt')).write_bytes(d);(out/(name+'.stderr')).write_bytes(e);assert b'0 packets dropped by kernel' in e
finally:
    for path in owned:
        assert command(c,'sha256sum '+path)[0].decode().split()[0]==sha(files[path]);command(c,'rm -- '+path)
    c.close();pool.shutdown(wait=True)
after=sample_pair();assert all(ready(r,int(u)) and r['bootID']==before[u]['bootID'] for u,r in after.items())
(out/'result.json').write_text(json.dumps({'completed':True,'sameBoot':True,'temporaryHelpersRemoved':True,'configurationUnchanged':True,'controlledLocalReceiveDelayMs':2500,'notANormalTrafficLossRate':True},indent=2)+'\n')
