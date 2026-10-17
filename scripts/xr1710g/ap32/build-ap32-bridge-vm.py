"""Private real-kernel VM build for bridge mutation notification ordering."""
from pathlib import Path
import fcntl, hashlib, json, shutil, subprocess
r = Path('/home/xrdev/projects/xr1710g/openwrt')
w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap32/bridge-transaction'
base = r.parent / 'boot-lab/ap31-publisher/linux-6.18.54'
lab = r.parent / 'boot-lab/ap32-bridge-transaction'
k = lab / 'linux-6.18.54'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
prep = json.loads((out / 'prepared.json').read_text())
paths = [p for p in prep['sources'] if not p.startswith('drivers/')]
held = {str(base / p): sha(base / p) for p in ['.config', 'arch/x86/boot/bzImage', 'Module.symvers', *paths] if (base / p).exists()}
lab.mkdir(exist_ok=True)
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not k.exists():
        subprocess.run(['cp', '-a', '--reflink=auto', str(base), str(k)], check=True)
    for p in paths:
        if (base / p).exists():
            assert sha(base / p) == prep['sources'][p]['before'], p
        assert sha(out / Path(p).name) == prep['sources'][p]['after'], p
        shutil.copy2(out / Path(p).name, k / p)
    # Private VM-only startup test of joining an existing mutation and nested
    # exit. It is not part of the candidate patch or AP firmware.
    selftest = r'''// SPDX-License-Identifier: GPL-2.0
#include <linux/init.h>
#include <linux/notifier.h>
#include "br_private.h"
static u32 seen;
static unsigned int init_count, begin_count, end_count;
static int observe(struct notifier_block *nb, unsigned long event, void *ptr)
{
 const struct br_fwd_policy_state *s=ptr;
 seen=s->writers;
 if(event==BR_FWD_POLICY_INIT)init_count++;
 if(event==BR_FWD_POLICY_BEGIN)begin_count++;
 if(event==BR_FWD_POLICY_END)end_count++;
 return NOTIFY_OK;
}
static struct notifier_block observer={.notifier_call=observe};
static int __init br_fence_selftest(void)
{
 bool failed=false;
 int err;
 br_fwd_policy_begin();
 err=br_fwd_policy_register(&observer);
 if(err){br_fwd_policy_end();pr_err("XR_TXN_STARTUP_FAIL register=%d\n",err);return 0;}
 failed|=seen!=1||init_count!=1;
 br_fwd_policy_begin();failed|=seen!=2||begin_count!=1;
 br_fwd_policy_end();failed|=seen!=1;
 br_fwd_policy_end();failed|=seen!=0||end_count!=2;
 br_fwd_policy_unregister(&observer);
 br_fwd_policy_begin();br_fwd_policy_end();failed|=begin_count!=1||end_count!=2;
 pr_info("XR_TXN_STARTUP_%s\n",failed?"FAIL":"OK");
 return 0;
}
late_initcall(br_fence_selftest);
'''
    (k / 'net/bridge/br_fence_selftest.c').write_text(selftest)
    with (k / 'net/bridge/Makefile').open('a') as f:
        f.write('\nbridge-y += br_fence_selftest.o\n')
    with (out / 'vm-kernel-build.log').open('w') as log:
        for target in ['olddefconfig', 'bzImage', 'modules']:
            p = subprocess.run(['make', '-C', str(k), '-j12', target], stdout=log, stderr=subprocess.STDOUT)
            assert p.returncode == 0, 'see vm-kernel-build.log'
    module = lab / 'module'
    module.mkdir(exist_ok=True)
    # Use actual RCU bridge fields in an atomic callback. Never acquire RTNL or
    # a bridge lock from a callback; referenced devices live for the module.
    fixture = r'''#include <linux/module.h>
#include <linux/notifier.h>
#include <linux/rtnetlink.h>
#include <linux/etherdevice.h>
#include "br_private.h"
static unsigned int phase;
module_param(phase,uint,0600);
static struct net_device *master,*pin,*pout;
static unsigned char mac[ETH_ALEN]={2,0,0,0,0,1};
static u32 writers;
static unsigned int events;
static bool bad;
static int observe(struct notifier_block *nb,unsigned long event,void *ptr)
{
 const struct br_fwd_policy_state *s=ptr;
 struct net_bridge_port *p;
 unsigned int fdb,state=255;
 if(event==BR_FWD_POLICY_BEGIN && s->writers!=writers+1)bad=true;
 if(event==BR_FWD_POLICY_END && (!writers||s->writers!=writers-1))bad=true;
 writers=s->writers;events++;
 rcu_read_lock();
 fdb=br_fdb_forward_to_rcu(master,pin,mac,1)|
     (br_fdb_forward_to_rcu(master,pout,mac,1)<<1);
 p=br_port_get_rcu(pin);if(p)state=READ_ONCE(p->state);
 rcu_read_unlock();
 pr_info("XR_TXN phase=%u event=%lu writers=%u fdb=%u stp=%u bad=%u\n",
         phase,event,writers,fdb,state,bad);
 return NOTIFY_OK;
}
static struct notifier_block observer={.notifier_call=observe};
static int __init probe_init(void)
{
 int err;
 rtnl_lock();
 master=dev_get_by_name(&init_net,"br-test");pin=dev_get_by_name(&init_net,"pin");pout=dev_get_by_name(&init_net,"pout");
 rtnl_unlock();
 if(!master||!pin||!pout){err=-ENODEV;goto fail;}
 err=br_fwd_policy_register(&observer);
 if(!err)return 0;
fail:
 if(master)dev_put(master);if(pin)dev_put(pin);if(pout)dev_put(pout);
 return err;
}
static void __exit probe_exit(void)
{
 br_fwd_policy_unregister(&observer);
 pr_info("XR_TXN_EXIT writers=%u events=%u bad=%u\n",writers,events,bad);
 dev_put(master);dev_put(pin);dev_put(pout);
}
module_init(probe_init);module_exit(probe_exit);MODULE_LICENSE("GPL");
'''
    (module / 'xr_fence_probe.c').write_text(fixture)
    (module / 'Makefile').write_text('obj-m += xr_fence_probe.o\nccflags-y += -I' + str(k / 'net/bridge') + '\n')
    with (out / 'vm-module-build.log').open('w') as log:
        p = subprocess.run(['make', '-C', str(k), 'M=' + str(module), '-j12', 'modules'], stdout=log, stderr=subprocess.STDOUT)
        assert p.returncode == 0, 'see vm-module-build.log'
assert held == {p: sha(Path(p)) for p in held}
report = {'passed': True, 'jobs': 12, 'kernel': str(k / 'arch/x86/boot/bzImage'),
          'kernelSHA256': sha(k / 'arch/x86/boot/bzImage'), 'configSHA256': sha(k / '.config'),
          'module': str(module / 'xr_fence_probe.ko'), 'moduleSHA256': sha(module / 'xr_fence_probe.ko'),
          'privateSelftestSHA256': sha(k / 'net/bridge/br_fence_selftest.c'),
          'candidate': prep['sources'], 'baselineVMUnchanged': True, 'productionOrDeviceChanged': False}
(out / 'vm-build.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k!='candidate'}))
