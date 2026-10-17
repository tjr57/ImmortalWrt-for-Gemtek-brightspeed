"""Real kernel bridge/FDB and generated TC argv, with no guest external NIC."""
from pathlib import Path
from datetime import datetime
from dataclasses import replace
import gzip, hashlib, importlib.util, json, re, shlex, shutil, subprocess, sys

w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap31/publisher'
lab = Path('/home/xrdev/projects/xr1710g/boot-lab/ap31-publisher')
build = json.loads((out / 'vm-build.json').read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert build['passed'] and sha(build['kernel']) == build['kernelSHA256']
assert sha(build['module']) == build['moduleSHA256']
spec = importlib.util.spec_from_file_location('xr_ppe_rules', out / 'xr_ppe_rules.py')
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
rule = m.Rule('00000000-0000-0000-0000-000000000001', 1, 'pin', 11, 'pout', 12, 10,
              '02:00:00:00:00:01', '02:00:00:00:00:02', 50, False, False)
rules = [rule, replace(rule, tagged_in=True), replace(rule, tagged_out=True)]
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
root = lab / ('guest-' + stamp)
root.mkdir()
for d in ('bin', 'sbin', 'dev', 'proc', 'sys', 'tmp', 'run', 'etc', 'usr/sbin', 'lib/modules'):
    (root / d).mkdir(parents=True, exist_ok=True)
shutil.copy2('/bin/busybox', root / 'bin/busybox')
for n in ('sh', 'mount', 'cat', 'sleep', 'grep', 'mkdir', 'ls', 'rm', 'sync', 'insmod', 'rmmod', 'poweroff', 'dmesg'):
    (root / 'bin' / n).symlink_to('busybox')
for tool in ('ip', 'tc', 'bridge'):
    source = shutil.which(tool)
    shutil.copy2(source, root / 'sbin' / tool)
    ldd = subprocess.run(['ldd', source], capture_output=True, text=True, check=True).stdout
    for name in re.findall(r'(/[^\s()]+)', ldd):
        p = Path(name)
        dest = root / p.relative_to('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p.resolve(), dest)
shutil.copy2(build['module'], root / 'lib/modules/xr_bridge_probe.ko')
init = r'''#!/bin/sh
export PATH=/bin:/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
fail() { echo "XR_PUBLISHER_FAIL: $*"; sync; poweroff -f; }
probe() { insmod /lib/modules/xr_bridge_probe.ko "$@" || fail "bridge probe $*"; rmmod xr_bridge_probe || fail remove_probe; }
ip link set lo up || fail lo
ip link add pin type veth peer name in-peer || fail pin
ip link add pout type veth peer name out-peer || fail pout
for d in pin in-peer pout out-peer; do ip link set "$d" up || fail up; done
tc qdisc add dev pin clsact || fail clsact
'''
for i, r in enumerate(rules):
    init += f'''
if {shlex.join(r.add_argv())} >/tmp/tc-error 2>&1; then fail hw_only_unexpected_success; fi
cat /tmp/tc-error
grep -Eiq 'offload|[Oo]peration not supported' /tmp/tc-error || fail unexpected_tc_error_{i}
tc -j filter show dev pin ingress >/tmp/filters || fail list
if grep -q '"options"' /tmp/filters; then fail software_rule_leaked; fi
echo XR_SKIP_SW_REJECTED_{i}
{shlex.join(['skip_hw' if x == 'skip_sw' else x for x in r.add_argv()])} || fail software_parser_{i}
echo XR_TC_JSON_BEGIN_{i}
tc -j filter show dev pin ingress || fail readback_{i}
echo XR_TC_JSON_END_{i}
{shlex.join(r.del_argv())} || fail exact_delete_{i}
tc -j filter show dev pin ingress >/tmp/filters || fail list_after_delete
if grep -q '"options"' /tmp/filters; then fail exact_delete_left_filter; fi
'''
# Check that tagged and untagged selectors coexist, with separate priorities.
for r in rules[:2]:
    init += shlex.join(['skip_hw' if x == 'skip_sw' else x for x in r.add_argv()]) + ' || fail coexist_add\n'
for r in rules[:2]:
    init += shlex.join(r.del_argv()) + ' || fail coexist_delete\n'
init += r'''
echo XR_TC_COEXIST_OK
tc qdisc del dev pin clsact || fail fixture_clsact_remove
ip link add br-test type bridge vlan_filtering 1 stp_state 0 || fail bridge
ip link set br-test up || fail bridge_up
ip link set pin master br-test || fail pin_master
ip link set pout master br-test || fail pout_master
bridge vlan add dev pin vid 50 pvid untagged || fail pin_vlan
bridge vlan add dev pout vid 50 pvid untagged || fail pout_vlan
bridge fdb add 02:00:00:00:00:01 dev pin master static vlan 50 || fail fdb
probe
probe port_name=pout expected_fdb=0
probe vid=51 expected_fdb=0
probe address=02:00:00:00:00:99 expected_fdb=0
bridge fdb add 02:00:00:00:00:03 dev pin master local vlan 50 || fail local_fdb
probe address=02:00:00:00:00:03 expected_fdb=0
ip link set br-test type bridge stp_state 1 || fail stp_enable
ip link set pin down || fail stp_port_down
ip link set pin up || fail stp_port_up
probe expected_port=0
ip link set br-test type bridge stp_state 0 || fail stp_disable
ip link set pin down || fail forwarding_port_down
ip link set pin up || fail forwarding_port_up
probe
bridge link set dev pin isolated on || fail isolate
probe expected_port=0
bridge link set dev pin isolated off || fail deisolate
probe
ip link set in-peer down || fail carrier_down
probe expected_port=0
ip link set in-peer up || fail carrier_up
probe
bridge fdb replace 02:00:00:00:00:01 dev pout master static vlan 50 || fail move_fdb
probe expected_fdb=0
probe port_name=pout
bridge fdb del 02:00:00:00:00:01 dev pout master vlan 50 || fail delete_fdb
probe port_name=pout expected_fdb=0
echo XR_PUBLISHER_VM_OK
sync
poweroff -f
'''
# BusyBox standalone ash may otherwise dispatch its built-in ip applet before
# PATH. Use the copied iproute2 programs explicitly for this qualification.
for tool in ('ip', 'tc', 'bridge'):
    init = re.sub(r'(?m)^' + tool + r'(?= )', '/sbin/' + tool, init)
    init = re.sub(r'(?<=if )' + tool + r'(?= )', '/sbin/' + tool, init)
    init = re.sub(r'(?<=do )' + tool + r'(?= )', '/sbin/' + tool, init)
(root / 'init').write_text(init); (root / 'init').chmod(0o755)
paths = ['.'] + [str(p.relative_to(root)) for p in sorted(root.rglob('*'))]
p = subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=root,
                   input=('\0'.join(paths) + '\0').encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
initrd = lab / ('guest-' + stamp + '.cpio.gz')
with gzip.open(initrd, 'wb') as f:
    f.write(p.stdout)
accel = 'kvm' if Path('/dev/kvm').exists() else 'tcg'
cmd = ['sudo', '-n', 'timeout', '55', 'qemu-system-x86_64', '-accel', accel,
       '-cpu', 'host' if accel == 'kvm' else 'qemu64', '-smp', '2', '-m', '1024',
       '-nodefaults', '-nic', 'none', '-display', 'none', '-serial', 'stdio', '-monitor', 'none',
       '-no-reboot', '-run-with', 'user=xrdev', '-kernel', build['kernel'], '-initrd', str(initrd),
       '-append', 'console=ttyS0 rdinit=/init panic=1 panic_on_oops=1 panic_on_warn=1']
log = out / ('vm-' + stamp + '.log')
with log.open('w') as f:
    p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
text = log.read_text(errors='replace')
faults = re.findall(r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|possible circular locking|sleeping function called from invalid context|XR_PUBLISHER_FAIL:).*$', text, re.M)
passed = p.returncode == 0 and 'XR_PUBLISHER_VM_OK' in text and not faults
readbacks = []
for i in range(3):
    match = re.search(r'XR_TC_JSON_BEGIN_' + str(i) + r'\s*(.*?)\s*XR_TC_JSON_END_' + str(i), text, re.S)
    if match:
        readbacks.append(json.loads(match[1]))
passed = passed and len(readbacks) == 3 and all('XR_SKIP_SW_REJECTED_' + str(i) in text for i in range(3))
report = {'passed': passed, 'exitCode': p.returncode, 'log': str(log.relative_to(w)),
          'kernelSHA256': build['kernelSHA256'], 'moduleSHA256': build['moduleSHA256'],
          'sourceSHA256': sha(out / 'xr_ppe_rules.py'), 'faults': faults,
          'bridgeProbeCount': text.count('XR_BRIDGE_PROBE fdb='), 'tcReadbacks': readbacks,
          'noExternalNICOrExistingDisk': True, 'APOrHostNetworkChanged': False,
          'realBridgeAndTcActionsPassed': passed, 'PPEHardwareOrFullPolicyHandoffQualified': False}
(out / ('vm-' + stamp + '.json')).write_text(json.dumps(report, indent=2) + '\n')
(out / 'vm-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'tcReadbacks'}))
raise SystemExit(0 if passed else 1)
