#include <linux/module.h>
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
