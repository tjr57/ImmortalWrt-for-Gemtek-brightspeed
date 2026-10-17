"""Real VLAN/port transitions and injected switchdev failures, isolated VM."""
from pathlib import Path
from datetime import datetime
import gzip,hashlib,json,re,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap33/bridge-policy'
lab=Path('/home/xrdev/projects/xr1710g/boot-lab/ap33-policy')
build=json.loads((out/'vm-build.json').read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert build['passed'] and sha(build['kernel'])==build['kernelSHA256'] and sha(build['module'])==build['moduleSHA256']
stamp=datetime.now().strftime('%Y%m%d-%H%M%S');root=lab/('guest-'+stamp);root.mkdir()
for d in ['bin','sbin','dev','proc','sys','tmp','run','etc','lib/modules']:(root/d).mkdir(parents=True,exist_ok=True)
shutil.copy2('/bin/busybox',root/'bin/busybox')
for n in ['sh','mount','cat','sleep','grep','mkdir','sync','insmod','rmmod','poweroff','dmesg']:(root/'bin'/n).symlink_to('busybox')
for tool in ['ip','bridge']:
 source=shutil.which(tool);shutil.copy2(source,root/'sbin'/tool)
 ldd=subprocess.run(['ldd',source],capture_output=True,text=True,check=True).stdout
 for name in re.findall(r'(/[^\s()]+)',ldd):
  p=Path(name);dest=root/p.relative_to('/');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p.resolve(),dest)
shutil.copy2(build['module'],root/'lib/modules/xr_policy_probe.ko')
init=r'''#!/bin/sh
export PATH=/bin:/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
fail() { echo "XR_POLICY_FAIL: $*"; sync; poweroff -f; }
phase() { sleep 0.1; echo "$1" >/sys/module/xr_policy_probe/parameters/phase || fail phase; }
fault() { echo "$1" >/sys/module/xr_policy_probe/parameters/fault || fail fault; }
port_state() {
 n=0
 while [ "$(cat /sys/class/net/pin/brport/state)" != "$1" ]; do
  n=$((n+1)); [ "$n" -le 30 ] || fail "port state $1"; sleep 0.1
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
port_state 3
insmod /lib/modules/xr_policy_probe.ko || fail probe
phase 1
/sbin/bridge vlan add dev pin vid 50 || fail add
phase 2
/sbin/bridge vlan add dev pin vid 50 pvid untagged || fail pvid
phase 3
/sbin/bridge vlan set dev pin vid 50 state 4 || fail vlan_block
phase 4
/sbin/bridge vlan set dev pin vid 50 state 3 || fail vlan_forward
phase 5
if /sbin/bridge vlan set dev pin vid 50 state 6; then fail invalid_state_accepted; fi
phase 6
/sbin/bridge link set dev pin isolated on || fail isolated_on
phase 7
echo 0 >/sys/class/net/pin/brport/isolated || fail sysfs_isolated_off
phase 8
if /sbin/bridge link set dev pin mab on; then fail invalid_mab_accepted; fi
phase 9
fault 2
if echo 1 >/sys/class/net/pin/brport/isolated; then fail fault_sysfs_accepted; fi
fault 0
phase 10
fault 2
if /sbin/bridge link set dev pin isolated on; then fail fault_netlink_accepted; fi
fault 0
phase 11
fault 1
if /sbin/ip link set br-test type bridge vlan_filtering 0; then fail fault_filter_accepted; fi
fault 0
phase 12
/sbin/ip link set br-test type bridge vlan_filtering 0 || fail filter_off
phase 13
/sbin/ip link set br-test type bridge vlan_filtering 1 || fail filter_on
phase 14
fault 3
if /sbin/ip link set br-test type bridge vlan_protocol 802.1ad; then fail fault_proto_accepted; fi
fault 0
phase 15
/sbin/ip link set br-test type bridge vlan_protocol 802.1ad || fail proto_ad
phase 16
/sbin/ip link set br-test type bridge vlan_protocol 802.1Q || fail proto_q
phase 17
fault 4
if /sbin/ip link set br-test type bridge vlan_default_pvid 99; then fail fault_default_accepted; fi
fault 0
[ "$(cat /sys/class/net/br-test/bridge/default_pvid)" = 1 ] || fail default_rollback
echo XR_DEFAULT_ROLLBACK_OK
phase 18
/sbin/ip link set br-test type bridge vlan_default_pvid 99 || fail default_99
[ "$(cat /sys/class/net/br-test/bridge/default_pvid)" = 99 ] || fail default_readback
phase 19
/sbin/ip link set br-test type bridge vlan_default_pvid 0 || fail default_disable
[ "$(cat /sys/class/net/br-test/bridge/default_pvid)" = 0 ] || fail default_disabled_readback
phase 20
/sbin/bridge vlan add dev pin vid 50 || fail pvid_clear
phase 21
/sbin/bridge vlan del dev pin vid 50 || fail delete
phase 22
/sbin/ip link set pin nomaster || fail detach
phase 23
/sbin/ip link set pin master br-test || fail attach
port_state 3
phase 24
/sbin/bridge vlan add dev pin vid 50 || fail add2
phase 25
if /sbin/ip link set br-test type bridge mst_enabled 1; then fail mst_with_vlans_accepted; fi
phase 26
/sbin/bridge vlan del dev pin vid 50 || fail delete2
phase 27
/sbin/ip link set br-test type bridge mst_enabled 1 || fail mst_on
phase 28
/sbin/ip link set br-test type bridge mst_enabled 0 || fail mst_off
phase 29
/sbin/bridge vlan add dev pin vid 50 pvid untagged || fail flush_setup
phase 30
/sbin/ip link set pin nomaster || fail flush_detach
phase 31
rmmod xr_policy_probe || fail remove_probe
echo XR_POLICY_VM_OK
sync
poweroff -f
'''
(root/'init').write_text(init);(root/'init').chmod(0o755)
paths=['.']+[str(p.relative_to(root)) for p in sorted(root.rglob('*'))]
p=subprocess.run(['cpio','--null','-o','--format=newc','--owner=0:0'],cwd=root,input=('\0'.join(paths)+'\0').encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
initrd=lab/('guest-'+stamp+'.cpio.gz')
with gzip.open(initrd,'wb') as f:f.write(p.stdout)
accel='kvm' if Path('/dev/kvm').exists() else 'tcg'
cmd=['sudo','-n','timeout','55','qemu-system-x86_64','-accel',accel,'-cpu','host' if accel=='kvm' else 'qemu64',
 '-smp','2','-m','1024','-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none',
 '-no-reboot','-run-with','user=xrdev','-kernel',build['kernel'],'-initrd',str(initrd),
 '-append','console=ttyS0 rdinit=/init panic=1 panic_on_oops=1 panic_on_warn=1 ipv6.disable=1']
log=out/('vm-'+stamp+'.log')
with log.open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
text=log.read_text(errors='replace')
faults=re.findall(r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|possible circular locking|sleeping function called from invalid context|XR_POLICY_FAIL:|XR_TXN_STARTUP_FAIL).*$',text,re.M)
keys=['phase','event','writers','member','forward','vflags','pvid','filter','proto','flags','mst','present','state','bad']
pattern='XR_POLICY '+' '.join(k+r'=(\d+)' for k in keys)
events=[dict(zip(keys,map(int,m))) for m in re.findall(pattern,text)]
checks={}
def check(n,field,before,after,mask=None):
 seq=[e for e in events if e['phase']==n]
 value=lambda e:e[field] if mask is None else bool(e[field]&mask)
 checks[str(n)+'_'+field]=bool(seq and seq[0]['event']==1 and seq[-1]['event']==2 and seq[-1]['writers']==0 and value(seq[0])==before and value(seq[-1])==after)
for n,f,a,b in [(1,'member',0,1),(1,'forward',0,1),(2,'pvid',1,50),(3,'forward',1,0),(4,'forward',0,1),
 (11,'filter',1,1),(12,'filter',1,0),(13,'filter',0,1),(14,'proto',0x8100,0x8100),(15,'proto',0x8100,0x88a8),(16,'proto',0x88a8,0x8100),
 (17,'pvid',50,50),(18,'pvid',50,50),(19,'pvid',50,50),(20,'pvid',50,0),(21,'member',1,0),
 (22,'present',1,0),(23,'present',0,1),(24,'member',0,1),(26,'member',1,0),(27,'mst',0,1),(28,'mst',1,0),
 (29,'member',0,1),(30,'member',1,0),(30,'present',1,0)]:check(n,f,a,b)
for n,a,b in [(6,0,1),(7,1,0),(9,0,0),(10,0,0)]:check(n,'flags',a,b,1<<16)
check(8,'flags',0,0,1<<22)
checks['invalid_vlan_state_no_mutation']=not any(e['phase']==5 for e in events)
checks['rejected_MST_no_mutation']=not any(e['phase']==25 for e in events)
checks['default_pvid_rollback']='XR_DEFAULT_ROLLBACK_OK' in text
injected=[tuple(map(int,m)) for m in re.findall(r'XR_POLICY_INJECT phase=(\d+) writers=(\d+) fault=(\d+)',text)]
checks['five_failures_inside_fence']=len(injected)==5 and {a for a,b,c in injected}=={9,10,11,14,17} and all(b>0 for a,b,c in injected)
checks['coherent_counts']=bool(events and not any(e['bad'] for e in events))
checks['balanced_exit']=bool(re.search(r'XR_POLICY_EXIT writers=0 events=\d+ injections=5 bad=0',text))
checks['nested_transactions']=any(e['writers']>1 for e in events)
checks['inherited_startup_registration']='XR_TXN_STARTUP_OK' in text
passed=p.returncode==0 and 'XR_POLICY_VM_OK' in text and not faults and all(checks.values())
report={'passed':passed,'exitCode':p.returncode,'log':str(log.relative_to(w)),'kernelSHA256':build['kernelSHA256'],
 'moduleSHA256':build['moduleSHA256'],'checks':checks,'events':events,'eventCount':len(events),'injections':injected,'faults':faults,
 'APOrHostNetworkChanged':False,'noExternalNICOrExistingDisk':True,'fullTCPolicyOrHardwareQualified':False}
for name in ['vm-'+stamp+'.json','vm-result.json']:(out/name).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='events'}));raise SystemExit(0 if passed else 1)
