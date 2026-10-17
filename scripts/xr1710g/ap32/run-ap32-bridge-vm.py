"""Exercise real FDB mutations/STP transitions in a VM with no external NIC."""
from pathlib import Path
from datetime import datetime
import gzip, hashlib, json, re, shutil, subprocess
w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap32/bridge-transaction'
lab = Path('/home/xrdev/projects/xr1710g/boot-lab/ap32-bridge-transaction')
build = json.loads((out / 'vm-build.json').read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert build['passed'] and sha(build['kernel']) == build['kernelSHA256']
assert sha(build['module']) == build['moduleSHA256']
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
root = lab / ('guest-' + stamp)
root.mkdir()
for d in ('bin', 'sbin', 'dev', 'proc', 'sys', 'tmp', 'run', 'etc', 'usr/sbin', 'lib/modules'):
    (root / d).mkdir(parents=True, exist_ok=True)
shutil.copy2('/bin/busybox', root / 'bin/busybox')
for n in ('sh', 'mount', 'cat', 'sleep', 'grep', 'mkdir', 'ls', 'sync', 'insmod', 'rmmod', 'poweroff', 'dmesg'):
    (root / 'bin' / n).symlink_to('busybox')
for tool in ('ip', 'bridge'):
    source = shutil.which(tool)
    shutil.copy2(source, root / 'sbin' / tool)
    ldd = subprocess.run(['ldd', source], capture_output=True, text=True, check=True).stdout
    for name in re.findall(r'(/[^\s()]+)', ldd):
        p = Path(name)
        dest = root / p.relative_to('/')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p.resolve(), dest)
shutil.copy2(build['module'], root / 'lib/modules/xr_fence_probe.ko')
sender = r'''#include <sys/socket.h>
#include <net/if.h>
#include <netpacket/packet.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
int main(int argc,char**argv){
 unsigned char frame[60]={255,255,255,255,255,255,2,0,0,0,0,1,0x88,0xb5};
 struct sockaddr_ll a={.sll_family=AF_PACKET,.sll_protocol=htons(0x88b5),.sll_halen=6};
 int s;if(argc!=2)return 1;a.sll_ifindex=if_nametoindex(argv[1]);if(!a.sll_ifindex)return 2;
 memset(a.sll_addr,255,6);s=socket(AF_PACKET,SOCK_RAW,htons(0x88b5));if(s<0)return 3;
 if(sendto(s,frame,sizeof(frame),0,(struct sockaddr*)&a,sizeof(a))!=sizeof(frame)){perror("send");close(s);return 4;}
 close(s);return 0;
}
'''
(out / 'vm-frame.c').write_text(sender)
subprocess.run(['gcc', '-static', '-Os', '-Wall', '-Wextra', '-Werror', str(out / 'vm-frame.c'), '-o', str(root / 'sbin/send-frame')], check=True)
init = r'''#!/bin/sh
export PATH=/bin:/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
fail() { echo "XR_TXN_FAIL: $*"; sync; poweroff -f; }
phase() { sleep 0.1; echo "$1" >/sys/module/xr_fence_probe/parameters/phase || fail phase; }
port_state() {
 n=0
 while [ "$(cat /sys/class/net/pin/brport/state)" != "$1" ]; do
  n=$((n+1)); [ "$n" -le 30 ] || fail "port state $1"
  sleep 0.1
 done
}
/sbin/ip link set lo up || fail lo
/sbin/ip link add pin type veth peer name in-peer || fail pin
/sbin/ip link add pout type veth peer name out-peer || fail pout
for d in pin in-peer pout out-peer; do /sbin/ip link set "$d" up || fail up; done
/sbin/ip link add br-test type bridge vlan_filtering 1 stp_state 0 || fail bridge
/sbin/ip link set br-test up || fail brup
/sbin/ip link set pin master br-test || fail pin_master
/sbin/ip link set pout master br-test || fail pout_master
insmod /lib/modules/xr_fence_probe.ko || fail probe
phase 1
/sbin/bridge fdb add 02:00:00:00:00:01 dev pin master static vlan 1 || fail add
phase 2
/sbin/bridge fdb replace 02:00:00:00:00:01 dev pout master static vlan 1 || fail move
phase 3
/sbin/bridge fdb replace 02:00:00:00:00:01 dev pout master local vlan 1 || fail local
phase 4
/sbin/bridge fdb replace 02:00:00:00:00:01 dev pin master static vlan 1 || fail static
phase 5
if /sbin/bridge fdb add 02:00:00:00:00:01 dev pin master static vlan 1; then fail duplicate_accepted; fi
phase 6
/sbin/bridge fdb del 02:00:00:00:00:01 dev pin master vlan 1 || fail delete
phase 7
/sbin/send-frame in-peer || fail learn_pin
sleep 0.1
phase 8
/sbin/send-frame in-peer || fail same_port_refresh
sleep 0.1
phase 9
/sbin/send-frame out-peer || fail dynamic_move
sleep 0.1
phase 10
/sbin/ip link set pin down || fail down
phase 11
/sbin/ip link set pin up || fail up
port_state 3
phase 12
/sbin/ip link set br-test type bridge stp_state 1 || fail stp_enable
phase 13
/sbin/ip link set pin down || fail stp_down
phase 14
/sbin/ip link set pin up || fail stp_up
port_state 1
phase 15
/sbin/ip link set br-test type bridge stp_state 0 || fail stp_disable
/sbin/ip link set pin down || fail reset_down
/sbin/ip link set pin up || fail reset_up
port_state 3
phase 16
/sbin/bridge fdb replace 02:00:00:00:00:01 dev pin master static extern_learn vlan 1 || fail ext_replace
phase 17
/sbin/bridge fdb del 02:00:00:00:00:01 dev pin master vlan 1 || fail ext_delete
phase 18
/sbin/bridge fdb add 02:00:00:00:00:01 dev pin master static extern_learn vlan 1 || fail ext_add
phase 19
/sbin/bridge fdb del 02:00:00:00:00:01 dev pin master vlan 1 || fail final_delete
phase 20
if /sbin/bridge fdb del 02:00:00:00:00:01 dev pin master vlan 1; then fail missing_delete_accepted; fi
rmmod xr_fence_probe || fail remove_probe
echo XR_TXN_VM_OK
sync
poweroff -f
'''
(root / 'init').write_text(init)
(root / 'init').chmod(0o755)
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
       '-append', 'console=ttyS0 rdinit=/init panic=1 panic_on_oops=1 panic_on_warn=1 ipv6.disable=1']
log = out / ('vm-' + stamp + '.log')
with log.open('w') as f:
    p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
text = log.read_text(errors='replace')
faults = re.findall(r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|possible circular locking|sleeping function called from invalid context|XR_TXN_FAIL:|XR_TXN_STARTUP_FAIL).*$', text, re.M)
events = [dict(zip(['phase','event','writers','fdb','stp','bad'], map(int, m))) for m in re.findall(
    r'XR_TXN phase=(\d+) event=(\d+) writers=(\d+) fdb=(\d+) stp=(\d+) bad=(\d+)', text)]
checks = {}
def phase_check(n, field, before, after):
    seq = [e for e in events if e['phase'] == n]
    checks[str(n) + '_' + field] = bool(seq and seq[0]['event'] == 1 and seq[0][field] == before
                                       and seq[-1]['event'] == 2 and seq[-1]['writers'] == 0 and seq[-1][field] == after)
for n,a,b in [(1,0,1),(2,1,2),(3,2,0),(4,0,1),(5,1,1),(6,1,0),(7,0,1),(9,1,2),
              (16,2,1),(17,1,0),(18,0,1),(19,1,0)]:
    phase_check(n,'fdb',a,b)
for n,a,b in [(10,3,0),(11,0,3),(13,3,0),(14,0,1)]:
    phase_check(n,'stp',a,b)
checks['ordinary_same_port_refresh_no_fence'] = not any(e['phase'] == 8 for e in events)
checks['missing_delete_no_fence'] = not any(e['phase'] == 20 for e in events)
checks['coherent_counts'] = bool(events and not any(e['bad'] for e in events))
checks['unregister_balanced'] = bool(re.search(r'XR_TXN_EXIT writers=0 events=\d+ bad=0',text))
checks['active_writer_registration_and_nested_selftest'] = 'XR_TXN_STARTUP_OK' in text
checks['nested_create'] = any(e['phase'] in (1,18) and e['writers'] == 2 for e in events)
passed = p.returncode == 0 and 'XR_TXN_VM_OK' in text and not faults and all(checks.values())
report = {'passed': passed, 'exitCode': p.returncode, 'log': str(log.relative_to(w)),
          'kernelSHA256': build['kernelSHA256'], 'moduleSHA256': build['moduleSHA256'],
          'checks': checks, 'eventCount': len(events), 'events': events, 'faults': faults,
          'noExternalNICOrExistingDisk': True, 'APOrHostNetworkChanged': False,
          'PPEHardwareOrFullPolicyQualified': False}
(out / ('vm-' + stamp + '.json')).write_text(json.dumps(report, indent=2) + '\n')
(out / 'vm-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k!='events'}))
raise SystemExit(0 if passed else 1)
