"""One-shot PC -> AP1 bridge -> 6 GHz Mesh -> AP2 baseline; no configuration writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib, importlib.util, json, re, subprocess, time
from xr_two_ap import WORKSPACE, connect, command
from ap27_forwarding_observer import Probes
from xr_npu_diagnostic_gates import complete_iperf, kernel_findings

OUT = WORKSPACE/'development/ap30/forwarding/loaded-transit1'
VERSION = '20261010-ap30-d331711d'
PORT, DURATION, STREAMS = 5330, 20, 4
EXE = WORKSPACE/'development/tools/msys2-iperf3/bin/iperf3.exe'
spec = importlib.util.spec_from_file_location('checks', Path(__file__).with_name('ap22-upgrade-common.py'))
checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
checks.base.VERSION = VERSION
checks.base.connect = lambda unit, **kw: connect(unit, via='lan')

def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

def read(c, cmd):
    return command(c, cmd)[0].decode().strip()

def snapshot(unit):
    c = connect(unit, via='lan')
    try:
        row = {name: read(c, cmd) for name,cmd in {
            'bootID':'cat /proc/sys/kernel/random/boot_id',
            'board':'ubus call system board', 'cpu':'cat /proc/stat',
            'net':'cat /proc/net/dev', 'mesh':'iw dev mesh6g station dump',
            'fdb':'bridge fdb show br br-lan', 'vlan':'bridge vlan show',
            'ports':'for d in lan2 lan3 lan4 wan; do printf "%s=" "$d"; cat /sys/class/net/$d/carrier; done',
            'guard':'cat /var/run/xr1710g-uplink-guard/status.json',
            'kernel':'dmesg', 'ppePolicy':'cat /sys/kernel/debug/ppe/xr_l2_policy_latched',
            'npu':'cat /sys/module/mt76/parameters/npu_enable',
            'ppe':'cat /sys/module/airoha_eth/parameters/ppe_bind_enable',
            'ppeBridge':'cat /sys/module/airoha_eth/parameters/ppe_bridge_bind_enable',
            'bridgeFirewall':'nft list table bridge fw4',
            'configHashes':'sha256sum /etc/config/network /etc/config/wireless /etc/config/firewall /etc/config/xr1710g_ap_configurator',
        }.items()}
        assert json.loads(row['board'])['release']['version'] == VERSION
        assert not kernel_findings(row['kernel'])
        assert all(row[x]=='N' for x in ('npu','ppe','ppeBridge'))
        assert re.search(r'mesh plink:\s+ESTAB', row['mesh']) and re.search(r'authorized:\s+yes', row['mesh'])
        assert read(c,'cat /sys/class/net/mesh6g/brport/state') == '3'
        assert json.loads(row['guard'])['gate_autostart'] == 'open'
        if unit==2:
            assert row['ports'].splitlines() == ['lan2=0','lan3=0','lan4=0','wan=0']
        else:
            assert 'lan2=1' in row['ports']
        return row
    finally:
        c.close()

def snapshots():
    with ThreadPoolExecutor(max_workers=2) as pool:
        return dict(zip(('1','2'),pool.map(snapshot,(1,2))))

def server():
    c = connect(2, via='lan')
    try:
        return command(c, f'timeout 50 iperf3 -s -1 -B 192.168.10.4 -p {PORT} -J --server-max-duration 35', timeout=60, check=False)
    finally:
        c.close()

assert not OUT.exists(), 'Baseline already submitted; inspect existing evidence.'
provenance = json.loads((EXE.parent.parent/'provenance.json').read_text())
assert provenance['package_signatures_verified']
for row in provenance['extracted_files']:
    assert hashlib.sha256((EXE.parent/row['name']).read_bytes()).hexdigest() == row['sha256']
OUT.mkdir(parents=True)
save('operation.json', {'at':datetime.now(timezone(timedelta(hours=8))).isoformat(), 'status':'started',
    'scope':'PC .101 -> switch -> AP1 lan2 -> mesh6g -> AP2 local TCP endpoint',
    'NpuPpeEnabled':False, 'networkConfigurationChanged':False})
route = subprocess.run(['powershell','-NoProfile','-Command',
    'Find-NetRoute -RemoteIPAddress 192.168.10.4 | Select-Object InterfaceIndex,IPAddress,NextHop | ConvertTo-Json -Compress'],capture_output=True,text=True,check=True)
route_data = json.loads(route.stdout)
assert all(row['InterfaceIndex']==22 for row in route_data) and any(row['IPAddress']=='192.168.10.101' for row in route_data)
save('pc-route.json',route_data)
with ThreadPoolExecutor(max_workers=2) as pool:
    health = dict(zip(('1','2'),pool.map(lambda u:checks.health(u,VERSION),(1,2))))
assert all(row['healthy'] for row in health.values())
save('health-before.json',health)
results=[]
for reverse in (False,True):
    label='ap2-to-pc' if reverse else 'pc-to-ap2'
    before=snapshots();save(label+'-before.json',before)
    probe_out=OUT/label;probe_out.mkdir();probes=Probes(probe_out)
    c=connect(2,via='lan')
    try:
        listening=read(c,'cat /proc/net/tcp')
        assert not re.search(r':'+format(PORT,'04X')+r'\s',listening)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(server)
            end=time.monotonic()+5
            while time.monotonic()<end:
                if re.search(r':'+format(PORT,'04X')+r'\s+\S+\s+0A\s',read(c,'cat /proc/net/tcp')):
                    break
                time.sleep(.2)
            else:
                raise RuntimeError('Owned one-shot server did not listen')
            print('TRANSIT_START '+label,flush=True)
            cli=subprocess.run([str(EXE),'-c','192.168.10.4','-B','192.168.10.101','-p',str(PORT),'-t',str(DURATION),'-P',str(STREAMS),'-J','--connect-timeout','4000']+(['-R'] if reverse else []),capture_output=True,timeout=45)
            data,error,code=pending.result(timeout=15)
    finally:
        c.close();probes.finish()
    for name,value in [('client',cli.stdout),('client-stderr',cli.stderr),('server',data),('server-stderr',error)]:
        (OUT/(label+'-'+name+('.json' if 'stderr' not in name else '.txt'))).write_bytes(value)
    assert cli.returncode==code==0
    client=json.loads(cli.stdout);remote=json.loads(data)
    complete_iperf(client,DURATION,reverse,STREAMS,'client')
    complete_iperf(remote,DURATION,reverse,STREAMS,'server')
    assert all(row['local_host']=='192.168.10.101' and row['remote_host']=='192.168.10.4' for row in client['start']['connected'])
    after=snapshots();save(label+'-after.json',after)
    for unit in ('1','2'):
        assert before[unit]['bootID']==after[unit]['bootID'] and before[unit]['configHashes']==after[unit]['configHashes']
    received=(client if reverse else remote)['end']['sum_received']
    row={'direction':label,'receiverMbps':received['bits_per_second']/1e6,'receiverBytes':received['bytes'],'seconds':received['seconds'],
         'passed':True,'NpuPpeEnabled':False}
    results.append(row);print(json.dumps(row),flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:
    health=dict(zip(('1','2'),pool.map(lambda u:checks.health(u,VERSION),(1,2))))
save('health-after.json',health);assert all(row['healthy'] for row in health.values())
save('result.json',{'passed':True,'transfers':results,'configurationPreserved':True,'noReboots':True,
                   'path':'PC via wired switch/AP1 bridge/6GHz Mesh to AP2 CPU endpoint',
                   'hardwareOffloadQualified':False,'limits':['NPU and PPE disabled throughout','AP2 terminates TCP; AP1 forwards','Aggregate interface counters include ambient traffic']})
state=json.loads((OUT/'operation.json').read_text());state['status']='completed';save('operation.json',state)
print('TRANSIT_BASELINE_COMPLETE',flush=True)
