"""Build an isolated x86 kernel for actual bridge/FDB and TC action tests."""
from pathlib import Path
import fcntl, hashlib, json, os, shutil, subprocess

r = Path('/home/xrdev/projects/xr1710g/openwrt')
w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap31/publisher'
candidate = w / 'development/ap31/ppe-context'
base = r.parent / 'boot-lab/npu-addresses/linux-6.18.54'
lab = r.parent / 'boot-lab/ap31-publisher'
k = lab / 'linux-6.18.54'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
held = {str(base / x): sha(base / x) for x in ('.config', 'arch/x86/boot/bzImage', 'Module.symvers', 'net/bridge/br_fdb.c', 'include/linux/if_bridge.h')}
lab.mkdir(exist_ok=True)
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not k.exists():
        subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(k)], check=True)
    for path in ['net/bridge/br_fdb.c', 'include/linux/if_bridge.h']:
        n = Path(path).name
        # The AP tree additionally exports an existing FDB lookup and has
        # the BPDU-filter flag. Check these exact known differences rather
        # than treating a generic VM source as identical to the AP tree.
        expected = (candidate / ('before-' + n)).read_text()
        expected = expected.replace('EXPORT_SYMBOL_GPL(br_fdb_find_rcu);\n', '')
        expected = expected.replace('#define BR_BPDU_FILTER\t\tBIT(24)\n', '')
        assert (base / path).read_text() == expected, path
        shutil.copy2(candidate / n, k / path)
    options = ['VETH', 'NET_NS', 'NET_SCH_INGRESS', 'NET_CLS_FLOWER', 'NET_CLS_ACT', 'NET_ACT_GACT', 'NET_ACT_MIRRED', 'NET_ACT_VLAN']
    subprocess.run([str(k / 'scripts/config'), '--file', str(k / '.config'), *[a for n in options for a in ('--enable', n)]], check=True)
    with (out / 'vm-kernel-build.log').open('w') as log:
        for target in ['olddefconfig', 'bzImage', 'modules']:
            p = subprocess.run(['make', '-C', str(k), '-j12', target], stdout=log, stderr=subprocess.STDOUT)
            assert p.returncode == 0, 'see vm-kernel-build.log'
    config = (k / '.config').read_text()
    assert all('CONFIG_' + n + '=y\n' in config for n in options)
    assert held == {p: sha(Path(p)) for p in held}
    # Fixture calls the actual exported bridge function and exact PPE port
    # predicate in the real kernel. It contains no fake FDB implementation.
    module = lab / 'module'
    module.mkdir(exist_ok=True)
    s = (candidate / 'airoha_ppe.c').read_text()
    a = s.index('static bool airoha_ppe_l2_port_eligible(')
    port = s[a:s.index('\n}\n', a) + 3]
    fixture = '''#include <linux/module.h>
#include <linux/netdevice.h>
#include <linux/if_bridge.h>
#include <linux/etherdevice.h>
#include <linux/rtnetlink.h>
#include <net/net_namespace.h>
static char *address="02:00:00:00:00:01";
static char *port_name="pin";
static unsigned int vid=50;
static bool expected_fdb=true, expected_port=true;
module_param(address,charp,0400);
module_param(port_name,charp,0400);
module_param(vid,uint,0400);
module_param(expected_fdb,bool,0400);
module_param(expected_port,bool,0400);
''' + port + '''
static int __init probe_init(void)
{
 struct net_device *br, *port;
 unsigned char mac[ETH_ALEN];
 bool fdb, eligible;
 if(!mac_pton(address,mac)) return -EINVAL;
 rtnl_lock();
 br=dev_get_by_name(&init_net,"br-test");
 port=dev_get_by_name(&init_net,port_name);
 if(!br||!port) { if(br)dev_put(br);if(port)dev_put(port);rtnl_unlock();return -ENODEV; }
 rcu_read_lock();
 fdb=br_fdb_forward_to_rcu(br,port,mac,vid);
 eligible=airoha_ppe_l2_port_eligible(port);
 rcu_read_unlock();
 dev_put(port);dev_put(br);rtnl_unlock();
 pr_info("XR_BRIDGE_PROBE fdb=%u port=%u expected=%u/%u\\n",fdb,eligible,expected_fdb,expected_port);
 return (fdb==expected_fdb&&eligible==expected_port)?0:-EINVAL;
}
static void __exit probe_exit(void){}
module_init(probe_init);module_exit(probe_exit);MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("AP31 isolated bridge API qualification fixture");
'''
    (module / 'xr_bridge_probe.c').write_text(fixture)
    (module / 'Makefile').write_text('obj-m += xr_bridge_probe.o\n')
    with (out / 'vm-module-build.log').open('w') as log:
        p = subprocess.run(['make', '-C', str(k), 'M=' + str(module), '-j12', 'modules'], stdout=log, stderr=subprocess.STDOUT)
        assert p.returncode == 0, 'see vm-module-build.log'
report = {'passed': True, 'jobs': 12, 'kernel': str(k / 'arch/x86/boot/bzImage'),
          'kernelSHA256': sha(k / 'arch/x86/boot/bzImage'), 'configSHA256': sha(k / '.config'),
          'module': str(module / 'xr_bridge_probe.ko'), 'moduleSHA256': sha(module / 'xr_bridge_probe.ko'),
          'bridgeSourceSHA256': sha(k / 'net/bridge/br_fdb.c'), 'portPredicateSHA256': hashlib.sha256(port.encode()).hexdigest(),
          'baselineKernelUnchanged': True, 'APKernelOrImageChanged': False}
(out / 'vm-build.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
