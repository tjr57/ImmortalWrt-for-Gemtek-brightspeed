"""Read-only AP25 forwarding baseline; no boot, rule or network changes."""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json
from xr_two_ap import WORKSPACE, connect, command

OUT = WORKSPACE / 'development/ap25/ppe-transit'
OUT.mkdir(exist_ok=True)
commands = {
    'board': 'ubus call system board',
    'bootID': 'cat /proc/sys/kernel/random/boot_id',
    'cmdline': 'cat /proc/cmdline',
    'parameters': 'for p in /sys/module/airoha_eth/parameters/ppe* /sys/module/mt76/parameters/npu_enable; do printf "%s=" "$p"; cat "$p"; done',
    'ports': 'for d in lan2 lan3 lan4 wan mesh6g; do printf "%s=" "$d"; cat /sys/class/net/$d/carrier; done',
    'links': 'ip -s link show',
    'routes': 'ip route show',
    'vlan': 'bridge vlan show',
    'fdb': 'bridge fdb show br br-lan',
    'tc': 'tc -s qdisc show; for d in lan2 lan3 lan4 wan mesh6g; do tc -s filter show dev "$d" ingress; done',
    'nft': 'nft list tables',
    'modules': 'lsmod',
    'ppeFiles': 'find /sys/kernel/debug -maxdepth 3 -iname "*ppe*" -o -name "xr_l2_*"',
    'ppePolicy': 'for p in /sys/kernel/debug/*ppe*/xr_l2_*; do test -f "$p" || continue; printf "%s=" "$p"; cat "$p"; done',
    'mesh': 'iw dev mesh6g station dump',
    'guard': 'cat /var/run/xr1710g-uplink-guard/status.json',
    'kernel': 'dmesg',
    'serverTool': 'iperf3 --version; command -v timeout',
}

def inspect(unit):
    c = connect(unit, via='lan')
    try:
        rows = {}
        for name, cmd in commands.items():
            data, error, code = command(c, cmd, check=False)
            rows[name] = {'stdout': data.decode(), 'stderr': error.decode(), 'exit': code}
        return unit, rows
    finally:
        c.close()

with ThreadPoolExecutor(max_workers=2) as pool:
    aps = dict(pool.map(inspect, (1, 2)))
data = {'at': datetime.now().astimezone().isoformat(), 'readOnly': True, 'APs': aps}
name = 'baseline-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json'
(OUT/name).write_text(json.dumps(data, indent=2)+'\n')
for unit, rows in aps.items():
    print(json.dumps({'unit':unit, 'boot':rows['bootID']['stdout'].strip(),
                     'parameters':rows['parameters']['stdout'], 'ports':rows['ports']['stdout'],
                     'ppePolicy':rows['ppePolicy']['stdout'], 'nft':rows['nft']['stdout'],
                     'tc':rows['tc'], 'ppeFiles':rows['ppeFiles'],
                     'version':json.loads(rows['board']['stdout'])['release']['version']}))
print(OUT/name)
