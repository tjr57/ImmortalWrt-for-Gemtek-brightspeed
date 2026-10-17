"""Private AP33 VLAN/port policy mutation and eligibility candidate."""
from pathlib import Path
import difflib,hashlib,json,re
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out=w/'development/ap33/bridge-policy';out.mkdir(parents=True,exist_ok=True)
assert not (out/'prepared.json').exists(),'candidate already prepared'
paths=['net/bridge/br_vlan.c','net/bridge/br_vlan_options.c','net/bridge/br_netlink.c',
 'net/bridge/br_sysfs_if.c','net/bridge/br_mst.c','net/bridge/br_if.c',
 'drivers/net/ethernet/airoha/airoha_ppe.c','include/linux/if_bridge.h']
before={p:(k/p).read_text() for p in paths};files=dict(before);sites=[]
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
assert sha(before[paths[-2]])=='3b769345430966ea6704c5994a906537cb6e62a8c62634cbfeb4eb81f6dd01e1'
def replace(path,a,b):
 s=files[path];assert s.count(a)==1,(path,a[:90],s.count(a));files[path]=s.replace(a,b,1)
def guard(path,fn,needle,device,indent='\t'):
 s=files[path];match=re.search(r'(?m)^(?:static )?(?:int|void|bool) '+fn+r'\([^;]*?\n\{',s)
 assert match,fn
 a=match.start();end=s.index('\n}\n',a);body=s[a:end]
 assert body.count(needle)==1,(fn,needle)
 body=body.replace(needle,indent+'guard(br_fwd_change)('+device+');\n'+needle,1)
 files[path]=s[:a]+body+s[end:];sites.append({'path':path,'function':fn,'before':needle.strip()})
v='net/bridge/br_vlan.c'
for fn,dev in [('br_vlan_add','br->dev'),('br_vlan_delete','br->dev'),('br_vlan_flush','br->dev'),
               ('nbp_vlan_add','port->br->dev'),('nbp_vlan_delete','port->br->dev'),('nbp_vlan_flush','port->br->dev')]:
 # Start before lookup/notification/mutation. The fence
 # covers allocation failures and all rollback/flush branches as well.
 guard(v,fn,'\tASSERT_RTNL();',dev)
guard(v,'br_vlan_filter_toggle','\tbr_opt_toggle(br, BROPT_VLAN_ENABLED, !!val);','br->dev')
guard(v,'__br_vlan_set_proto','\terr = switchdev_port_attr_set(br->dev, &attr, extack);','br->dev')
guard(v,'__br_vlan_set_default_pvid','\tif (!pvid) {','br->dev')
guard('net/bridge/br_vlan_options.c','br_vlan_modify_state','\tif (v->vid == br_get_pvid(vg))','br->dev')
guard('net/bridge/br_mst.c','br_mst_set_enabled','\terr = switchdev_port_attr_set(br->dev, &attr, extack);','br->dev')
guard('net/bridge/br_netlink.c','br_setport','\told_flags = p->flags;','p->br->dev')
guard('net/bridge/br_sysfs_if.c','store_flag','\t\terr = br_switchdev_set_port_flag(p, flags, mask, &extack);','p->br->dev','\t\t')
guard('net/bridge/br_if.c','br_add_if','\tp = new_nbp(br, dev);','br->dev')
guard('net/bridge/br_if.c','del_nbp','\tsysfs_remove_link(br->ifobj, p->dev->name);','br->dev')
helper='''/* Membership alone is insufficient: a VLAN can be blocked while its
 * port remains forwarding (including without MST). Caller holds RCU.
 */
bool br_vlan_forwarding_rcu(const struct net_device *dev, u16 vid)
{
	struct net_bridge_vlan_group *vg;
	struct net_bridge_vlan *v;
	struct net_bridge_port *p;

	p = br_port_get_check_rcu(dev);
	if (p)
		vg = nbp_vlan_group_rcu(p);
	else if (netif_is_bridge_master(dev))
		vg = br_vlan_group_rcu(netdev_priv(dev));
	else
		return false;

	v = br_vlan_find(vg, vid);
	return v && br_vlan_should_use(v) &&
	       READ_ONCE(v->state) == BR_STATE_FORWARDING;
}
EXPORT_SYMBOL_GPL(br_vlan_forwarding_rcu);

'''
replace(v,'EXPORT_SYMBOL_GPL(br_vlan_get_info_rcu);\n','EXPORT_SYMBOL_GPL(br_vlan_get_info_rcu);\n\n'+helper)
hdr='include/linux/if_bridge.h'
replace(hdr,'bool br_mst_enabled(const struct net_device *dev);','bool br_vlan_forwarding_rcu(const struct net_device *dev, u16 vid);\nbool br_mst_enabled(const struct net_device *dev);')
replace(hdr,'static inline bool br_mst_enabled(const struct net_device *dev)','''static inline bool br_vlan_forwarding_rcu(const struct net_device *dev, u16 vid)
{
	return false;
}

static inline bool br_mst_enabled(const struct net_device *dev)''')
ppe='drivers/net/ethernet/airoha/airoha_ppe.c'
replace(ppe,'br_vlan_get_info_rcu(odev, vid, &info))','br_vlan_get_info_rcu(odev, vid, &info) ||\n      !br_vlan_forwarding_rcu(indev, vid) ||\n      !br_vlan_forwarding_rcu(odev, vid))')
replace(ppe,'br_vlan_get_info_rcu(skb->dev, vid, &vinfo))','br_vlan_get_info_rcu(skb->dev, vid, &vinfo) ||\n\t\t    !br_vlan_forwarding_rcu(skb->dev, vid))')
replace(ppe,'\tbr_fwd_policy_unregister(&eth->ppe->l2_bridge_nb);','''	/* Quiesce L2 binding before detaching its policy notifiers. A racing
	 * packet or TC callback must not republish during observer teardown.
	 */
	airoha_ppe_l2_policy_event(&eth->ppe->l2_policy_nb, 0, NULL);
	br_fwd_policy_unregister(&eth->ppe->l2_bridge_nb);''')
patch='Subject: [PATCH] XR: fence VLAN and bridge-port policy changes before PPE binding\n\n'
for p,s in files.items():
 n=Path(p).name;(out/n).write_text(s);(out/('before-'+n)).write_text(before[p])
 patch+=''.join(difflib.unified_diff(before[p].splitlines(True),s.splitlines(True),fromfile='a/'+p,tofile='b/'+p))
(out/'99999i-XR-PPE-VLAN-port-policy-fence.patch').write_text(patch)
report={'prepared':True,'baseline':'20261011-ap32-d331711d','sources':{p:{'before':sha(before[p]),'after':sha(s)} for p,s in files.items()},
 'guardSites':sites,'newEligibility':'Both bridge ports must forward the selected VLAN, not merely have membership',
 'MRPCompiled':False,'productionOrDeviceChanged':False,'fullTCPolicyOrHardwareQualified':False}
(out/'prepared.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'prepared':True,'guardSites':len(sites),'files':len(files)}))
