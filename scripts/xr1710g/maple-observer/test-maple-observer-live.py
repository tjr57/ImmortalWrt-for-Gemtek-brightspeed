"""AP2 then AP1: passive observer load/read/unload, NPU remains disabled."""
from pathlib import Path
from datetime import datetime
import hashlib
import importlib.util
import json
import re
import argparse
from xr_two_ap import WORKSPACE as W, connect, command

O = W/'development/ap24/maple-observer'
parser = argparse.ArgumentParser()
parser.add_argument('--attempt', type=int, choices=(1, 2), default=1)
attempt = parser.parse_args().attempt
L = O/('live-baseline' if attempt == 1 else 'live-baseline2')
L.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('a', W/'environment/ap22-upgrade-common.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
a.base.VERSION = '20261010-ap24-d331711d'
a.base.connect = lambda unit, **kwargs: connect(unit, via='lan')
bad = rb'WARNING:|BUG:|kernel BUG|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
arm = json.loads((O/'result-latest.json').read_text())
vm = json.loads((O/'vm-result-latest.json').read_text())
module = O/'xr_maple_observer.ko'
assert arm['passed'] and vm['passed'] and arm['sources'] == vm['sources']
assert all(sha(O/'src'/name) == digest for name, digest in arm['sources'].items())
assert sha(module) == arm['moduleSHA256']
remote = '/tmp/xr_maple_observer.ko'

def save(name, value):
    (L/name).write_text(json.dumps(value, indent=2)+'\n')

def read(c, s):
    return command(c, s)[0].decode().strip()

assert not (L/'scheduled.json').exists(), 'One-shot already submitted; inspect journal'
before = {}
for unit in (2, 1):
    check = a.health(unit, a.base.VERSION)
    save(f'ap{unit}-preflight-health.json', check)
    assert check['healthy'], check
    c = connect(unit, via='lan')
    try:
        before[unit] = {'boot': read(c, 'cat /proc/sys/kernel/random/boot_id'),
                        'preservation': a.preservation(c)}
        assert read(c, 'cat /sys/module/mt76/parameters/npu_enable') == 'N'
        assert not re.search(bad, command(c, 'dmesg')[0])
        assert command(c, 'test ! -e /sys/module/xr_maple_observer && test ! -e '+remote)[2] == 0
    finally:
        c.close()
save('before.json', before)
save('scheduled.json', {'at': datetime.now().astimezone().isoformat(), 'order': [2, 1],
                        'moduleSHA256': arm['moduleSHA256'], 'npuActivated': False})
results = []
for unit in (2, 1):
    c = connect(unit, via='lan')
    uploaded = False
    try:
        stdin, stdout, stderr = c.exec_command('umask 077; set -C; cat > '+remote+'; sha256sum '+remote, timeout=30)
        stdin.channel.sendall(module.read_bytes())
        stdin.channel.shutdown_write()
        data, error = stdout.read(), stderr.read()
        assert stdout.channel.recv_exit_status() == 0 and data.decode().split()[0] == arm['moduleSHA256']
        uploaded = True
        save(f'ap{unit}-load-submitted.json', {'moduleSHA256': arm['moduleSHA256']})
        command(c, 'insmod '+remote)
        snapshot = read(c, 'cat /sys/kernel/debug/xr_maple_observer')
        assert snapshot == 'schema=1 captured=0', snapshot
        (L/f'ap{unit}-snapshot.txt').write_text(snapshot+'\n')
        mode = read(c, 'ls -ld /sys/kernel/debug/xr_maple_observer').split()[0]
        assert mode == '-r--------', mode
    finally:
        if uploaded:
            if command(c, 'test -e /sys/module/xr_maple_observer', check=False)[2] == 0:
                command(c, 'rmmod xr_maple_observer')
            if command(c, 'test ! -e /sys/module/xr_maple_observer', check=False)[2] == 0:
                command(c, 'rm -f -- '+remote)
        c.close()
    for peer in (2, 1):
        c = connect(peer, via='lan')
        try:
            assert read(c, 'cat /proc/sys/kernel/random/boot_id') == before[peer]['boot']
            assert a.preservation(c) == before[peer]['preservation']
            kernel = command(c, 'dmesg')[0]
            assert not re.search(bad, kernel)
            if peer == unit:
                assert b'XR_MAPLE_OBSERVER ready exact_site=d4 passive=1' in kernel
                assert b'XR_MAPLE_OBSERVER removed' in kernel
                assert command(c, 'test ! -e /sys/module/xr_maple_observer && test ! -e /sys/kernel/debug/xr_maple_observer && test ! -e '+remote)[2] == 0
                (L/f'ap{peer}-kernel.txt').write_bytes(kernel)
        finally:
            c.close()
        assert a.health(peer, a.base.VERSION)['healthy']
    result = {'unit': unit, 'loadedAndUnloaded': True, 'captured': False,
              'exactKernelTextBindingPassed': True, 'bothBootAndPreservationUnchanged': True}
    results.append(result)
    save(f'ap{unit}-result.json', result)
    print(json.dumps(result), flush=True)
result = {'passed': True, 'at': datetime.now().astimezone().isoformat(), 'results': results,
          'moduleSHA256': arm['moduleSHA256'], 'observerRemovedFromBoth': True,
          'npuActivated': False, 'flashed': False, 'phoneTested': False,
          'mainRouterSwitchPCNetworkChanged': False,
          'limits': ['No artificial router exception or NPU activation; no live fault snapshot captured.']}
save('result.json', result)
print(json.dumps(result), flush=True)
