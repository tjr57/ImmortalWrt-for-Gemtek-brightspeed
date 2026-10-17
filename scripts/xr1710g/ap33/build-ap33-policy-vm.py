"""Isolated real kernel for VLAN/port mutation ordering and rollback probes."""
from pathlib import Path
import fcntl,hashlib,json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
ap=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
base=r.parent/'boot-lab/ap32-bridge-transaction/linux-6.18.54'
lab=r.parent/'boot-lab/ap33-policy';k=lab/'linux-6.18.54';out=w/'development/ap33/bridge-policy'
prep=json.loads((out/'prepared.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[p for p in prep['sources'] if not p.startswith('drivers/')]
paths+=['include/uapi/linux/if_link.h','net/core/rtnetlink.c','net/bridge/br_switchdev.c']
held={str(base/p):sha(base/p) for p in ['.config','arch/x86/boot/bzImage','Module.symvers',*paths]}
lab.mkdir(exist_ok=True);differences={}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if not k.exists():subprocess.run(['cp','-a','--reflink=auto',str(base),str(k)],check=True)
 for p in paths:
  # AP's already deployed BPDU-filter patch extends netlink and its enum.
  # Record the exact VM/base difference; all other files must match AP32.
  same=(base/p).read_bytes()==(ap/p).read_bytes()
  if not same:
   assert p in ['net/bridge/br_netlink.c','net/bridge/br_sysfs_if.c','include/uapi/linux/if_link.h','net/core/rtnetlink.c','net/bridge/br_switchdev.c'],p
   diff=subprocess.run(['diff','-u',str(base/p),str(ap/p)],capture_output=True,text=True).stdout
   differences[p]=diff
   if p=='net/bridge/br_switchdev.c':
    assert '!p->hwdom' in diff and 'port->offload_count' in diff,p
   else:assert 'BPDU_FILTER' in diff or 'bpdu_filter' in diff,p
  source=out/Path(p).name if p in prep['sources'] else ap/p
  if p in prep['sources']:assert sha(source)==prep['sources'][p]['after']
  if (k/p).read_bytes()!=source.read_bytes():
   shutil.copy2(source,k/p)
   # An AP source can predate the cloned VM objects. Force dependency rebuild
   # instead of letting copy2's preserved timestamp reuse a stale object.
   (k/p).touch()
 subprocess.run([str(k/'scripts/config'),'--file',str(k/'.config'),'-e','NET_SWITCHDEV'],check=True)
 with (out/'vm-kernel-build.log').open('w') as log:
  for target in ['olddefconfig','bzImage','modules']:
   p=subprocess.run(['make','-C',str(k),'-j12',target],stdout=log,stderr=subprocess.STDOUT)
   assert p.returncode==0,'see vm-kernel-build.log'
 assert 'CONFIG_NET_SWITCHDEV=y\n' in (k/'.config').read_text()
 module=lab/'module';module.mkdir(exist_ok=True)
 fixture=r'''#include <linux/module.h>
#include <linux/notifier.h>
#include <linux/rtnetlink.h>
#include <net/switchdev.h>
#include "br_private.h"
static unsigned int phase, fault;
module_param(phase,uint,0600);module_param(fault,uint,0600);
static struct net_device *master,*pin,*pout;
static u32 writers;
static unsigned int events,injections;
static bool bad;
static int observe(struct notifier_block *nb,unsigned long event,void *ptr)
{
 const struct br_fwd_policy_state *s=ptr;
 struct net_bridge_port *p;
 struct bridge_vlan_info info={};
 u16 pvid=0,proto=0;
 unsigned int vflags=0,flags=0,member,forward,mst,filter,present,state=255;
 if(event==BR_FWD_POLICY_BEGIN && s->writers!=writers+1)bad=true;
 if(event==BR_FWD_POLICY_END && (!writers||s->writers!=writers-1))bad=true;
 writers=s->writers;events++;
 rcu_read_lock();
 p=br_port_get_rcu(pin);present=!!p;if(p){flags=READ_ONCE(p->flags);state=READ_ONCE(p->state);}
 member=!br_vlan_get_info_rcu(pin,50,&info);if(member)vflags=info.flags;
 br_vlan_get_pvid_rcu(pin,&pvid);br_vlan_get_proto(master,&proto);
 filter=br_vlan_enabled(master);mst=br_mst_enabled(master);forward=br_vlan_forwarding_rcu(pin,50);
 rcu_read_unlock();
 pr_info("XR_POLICY phase=%u event=%lu writers=%u member=%u forward=%u vflags=%u pvid=%u filter=%u proto=%u flags=%u mst=%u present=%u state=%u bad=%u\n",
 phase,event,writers,member,forward,vflags,pvid,filter,proto,flags,mst,present,state,bad);
 return NOTIFY_OK;
}
static struct notifier_block observer={.notifier_call=observe};
static int fail_switchdev(struct notifier_block *nb,unsigned long event,void *ptr)
{
 bool fail=false;
 if(event==SWITCHDEV_PORT_ATTR_SET){
  struct switchdev_notifier_port_attr_info *i=ptr;
  fail=(fault==1 && i->attr->id==SWITCHDEV_ATTR_ID_BRIDGE_VLAN_FILTERING)||
       (fault==2 && i->attr->id==SWITCHDEV_ATTR_ID_PORT_PRE_BRIDGE_FLAGS)||
       (fault==3 && i->attr->id==SWITCHDEV_ATTR_ID_BRIDGE_VLAN_PROTOCOL);
  if(fail)i->handled=true;
 }else if(event==SWITCHDEV_PORT_OBJ_ADD){
  struct switchdev_notifier_port_obj_info *i=ptr;
  if(i->obj->id==SWITCHDEV_OBJ_ID_PORT_VLAN){
   struct switchdev_obj_port_vlan *v=SWITCHDEV_OBJ_PORT_VLAN(i->obj);
   fail=fault==4 && i->info.dev==pout && v->vid==99;
   if(fail)i->handled=true;
  }
 }
 if(!fail)return NOTIFY_DONE;
 if(!writers)bad=true;
 injections++;pr_info("XR_POLICY_INJECT phase=%u writers=%u fault=%u\n",phase,writers,fault);
 return notifier_from_errno(-EIO);
}
static struct notifier_block failure_observer={.notifier_call=fail_switchdev};
static struct notifier_block atomic_failure_observer={.notifier_call=fail_switchdev};
static int __init probe_init(void)
{
 int err;
 rtnl_lock();master=dev_get_by_name(&init_net,"br-test");pin=dev_get_by_name(&init_net,"pin");pout=dev_get_by_name(&init_net,"pout");rtnl_unlock();
 if(!master||!pin||!pout){err=-ENODEV;goto fail;}
 err=br_fwd_policy_register(&observer);if(err)goto fail;
 err=register_switchdev_notifier(&atomic_failure_observer);
 if(err){br_fwd_policy_unregister(&observer);goto fail;}
 err=register_switchdev_blocking_notifier(&failure_observer);
 if(!err)return 0;
 unregister_switchdev_notifier(&atomic_failure_observer);
 br_fwd_policy_unregister(&observer);
fail:
 if(master)dev_put(master);
 if(pin)dev_put(pin);
 if(pout)dev_put(pout);
 return err;
}
static void __exit probe_exit(void)
{
 unregister_switchdev_blocking_notifier(&failure_observer);
 unregister_switchdev_notifier(&atomic_failure_observer);
 br_fwd_policy_unregister(&observer);
 pr_info("XR_POLICY_EXIT writers=%u events=%u injections=%u bad=%u\n",writers,events,injections,bad);
 dev_put(master);dev_put(pin);dev_put(pout);
}
module_init(probe_init);module_exit(probe_exit);MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Isolated XR bridge policy transaction test probe");
'''
 (module/'xr_policy_probe.c').write_text(fixture)
 (module/'Makefile').write_text('obj-m += xr_policy_probe.o\nccflags-y += -I'+str(k/'net/bridge')+'\n')
 with (out/'vm-module-build.log').open('w') as log:
  p=subprocess.run(['make','-C',str(k),'M='+str(module),'-j12','modules'],stdout=log,stderr=subprocess.STDOUT)
  assert p.returncode==0,'see vm-module-build.log'
 shutil.copy2(module/'xr_policy_probe.c',out/'vm-probe.c')
 symbols=subprocess.run(['nm',str(module/'xr_policy_probe.ko')],capture_output=True,text=True,check=True).stdout
 for name in ['register_switchdev_notifier','register_switchdev_blocking_notifier','fail_switchdev']:
  assert name in symbols,'switchdev probe compiled away: '+name
assert held=={p:sha(Path(p)) for p in held}
report={'passed':True,'jobs':12,'kernel':str(k/'arch/x86/boot/bzImage'),'kernelSHA256':sha(k/'arch/x86/boot/bzImage'),
 'module':str(module/'xr_policy_probe.ko'),'moduleSHA256':sha(module/'xr_policy_probe.ko'),
 'configSHA256':sha(k/'.config'),'probeSHA256':sha(out/'vm-probe.c'),'APPreexistingChangesToVM':differences,
 'sources':prep['sources'],'baselineVMUnchanged':True,'productionOrDeviceChanged':False}
(out/'vm-build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['sources','APPreexistingChangesToVM']}))
