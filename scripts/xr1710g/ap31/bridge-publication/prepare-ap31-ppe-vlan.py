"""Prepare a private bridge action/context candidate. No live or production changes."""
from pathlib import Path
import difflib, hashlib, json
w=Path('/mnt/d/ChatGPT/XR1710G')
r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out=w/'development/ap31/ppe-vlan'
out.mkdir()
base=k/'drivers/net/ethernet/airoha'
old={n:(base/n).read_text() for n in ('airoha_ppe.c','airoha_eth.h')}
assert old['airoha_ppe.c']==(w/'development/ap31/ppe-target/before.c').read_text()
t=(w/'development/ap31/ppe-target/after.c').read_text()
def rep(s,a,b):
 assert s.count(a)==1,(a[:100],s.count(a))
 return s.replace(a,b,1)
t=rep(t,"/* A hardware entry has exactly one egress. An absent redirect must not\n * reach DSA lookup with a NULL netdev, and multiple redirects cannot be\n * represented by retaining only the last action's target.\n */",
"""/* A hardware entry has exactly one egress. Reject absent/null targets early
 * and do not collapse multiple redirects into their final target.
 */""")
planner='''/* FOE VLAN fields describe the final output stack, not a push counter.
 * Keeping an input tag needs per-packet PCP/DEI preservation and remains in
 * software. This helper only validates; it does not touch hardware.
 */
static bool airoha_ppe_l2_actions(struct flow_rule *rule, u16 vid,
                                bool ingress_tagged, bool egress_untagged,
                                struct airoha_flow_data *data)
{
 const struct flow_action_entry *act;
 bool tagged = ingress_tagged, popped = false, pushed = false;
 bool redirected = false;
 int i;

 if (vid >= VLAN_VID_MASK || (!vid && (ingress_tagged || !egress_untagged)))
  return false;
 flow_action_for_each(i, act, &rule->action) {
  if (redirected)
   return false;
  switch (act->id) {
  case FLOW_ACTION_VLAN_POP:
   if (!tagged || popped || pushed)
    return false;
   tagged = false;
   popped = true;
   break;
  case FLOW_ACTION_VLAN_PUSH:
   if (tagged || pushed || !vid || act->vlan.vid != vid ||
       act->vlan.proto != htons(ETH_P_8021Q) || act->vlan.prio)
    return false;
   tagged = true;
   pushed = true;
   break;
  case FLOW_ACTION_REDIRECT:
   if (!act->dev)
    return false;
   redirected = true;
   break;
  default:
   /* Includes checksum mutation, PPPoE and unrepresented metadata. */
   return false;
  }
 }
 if (!redirected || (ingress_tagged && !popped) ||
     tagged == egress_untagged)
  return false;
 data->vlan.num = tagged ? 1 : 0;
 if (tagged) {
  data->vlan.hdr[0].id = vid;
  data->vlan.hdr[0].proto = htons(ETH_P_8021Q);
 }
 return true;
}

/* Use actual bridge port membership, PVID and output tag policy. */
static bool airoha_ppe_l2_context(struct flow_rule *rule,
                                struct net_device *odev,
                                struct airoha_flow_data *data,
                                struct airoha_l2_flow_key *key)
{
 struct flow_match_meta meta;
 struct net_device *indev, *master;
 struct bridge_vlan_info info;
 bool tagged = flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_VLAN);
 bool untagged = true, valid = false;
 u16 vid = 0, proto;

 if (!odev || !airoha_ppe_l2_rule_exact(rule))
  return false;
 flow_rule_match_meta(rule, &meta);
 rcu_read_lock();
 indev = dev_get_by_index_rcu(dev_net(odev), meta.key->ingress_ifindex);
 if (!indev || indev == odev || is_vlan_dev(indev) || is_vlan_dev(odev) ||
     !netif_is_bridge_port(indev) || !netif_is_bridge_port(odev))
  goto out;
 master = airoha_ppe_foe_get_bridge_master_rcu(indev);
 if (!master || !net_eq(dev_net(indev), dev_net(odev)) ||
     airoha_ppe_foe_get_bridge_master_rcu(odev) != master)
  goto out;
 if (br_vlan_enabled(master)) {
  if (br_vlan_get_proto(master, &proto) || proto != ETH_P_8021Q)
   goto out;
  if (tagged) {
   struct flow_match_vlan vlan;
   flow_rule_match_vlan(rule, &vlan);
   vid = vlan.key->vlan_id;
   if (vlan.mask->vlan_id != VLAN_VID_MASK ||
       vlan.key->vlan_tpid != htons(ETH_P_8021Q) ||
       vlan.mask->vlan_tpid != htons(0xffff))
    goto out;
  } else if (br_vlan_get_pvid_rcu(indev, &vid)) {
   goto out;
  }
  if (!vid || vid >= VLAN_VID_MASK ||
      br_vlan_get_info_rcu(indev, vid, &info) ||
      br_vlan_get_info_rcu(odev, vid, &info))
   goto out;
  untagged = !!(info.flags & BRIDGE_VLAN_INFO_UNTAGGED);
 } else if (tagged) {
  goto out;
 }
 if (!airoha_ppe_l2_actions(rule, vid, tagged, untagged, data))
  goto out;
 key->net_cookie = dev_net(indev)->net_cookie;
 key->ingress_ifindex = indev->ifindex;
 key->bridge_ifindex = master->ifindex;
 key->vid = vid;
 key->vlan_proto = htons(ETH_P_8021Q);
 key->ingress_tagged = tagged;
 ether_addr_copy(key->source, data->eth.h_source);
 ether_addr_copy(key->dest, data->eth.h_dest);
 valid = true;
out:
 rcu_read_unlock();
 return valid;
}

'''
t=rep(t,'static int airoha_ppe_flow_offload_replace(',planner+'static int airoha_ppe_flow_offload_replace(')
t=rep(t,'\tstruct airoha_flow_data data = {};','\tstruct airoha_flow_data data = {};\n\tstruct airoha_l2_flow_key l2_key = {};')
start=t.index('static int airoha_ppe_flow_offload_replace(')
pre,s=t[:start],t[start:]
s=rep(s,'\tflow_action_for_each(i, act, &rule->action) {\n\t\tswitch (act->id)',
'''\tflow_action_for_each(i, act, &rule->action) {
\t\t/* Derive bridge output after validating its context. */
\t\tif (offload_type == PPE_PKT_TYPE_BRIDGE) {
\t\t\tif (act->id == FLOW_ACTION_REDIRECT)
\t\t\t\todev = act->dev;
\t\t\tcontinue;
\t\t}
\t\tswitch (act->id)''')
s=rep(s,'\tif (!is_valid_ether_addr(data.eth.h_source)',
'''\tif (offload_type == PPE_PKT_TYPE_BRIDGE &&
\t    !airoha_ppe_l2_context(rule, odev, &data, &l2_key)) {
\t\tNL_SET_ERR_MSG_MOD(f->common.extack,
\t\t\t"PPE bridge actions do not match exact VLAN/port context");
\t\treturn -EOPNOTSUPP;
\t}

\tif (!is_valid_ether_addr(data.eth.h_source)''')
a=s.index('\tif (offload_type == PPE_PKT_TYPE_BRIDGE) {\n\t\tstruct flow_match_meta meta;')
b=s.index('\n\te->cookie = f->cookie;',a)
s=s[:a]+'\tif (offload_type == PPE_PKT_TYPE_BRIDGE)\n\t\te->l2_key = l2_key;\n'+s[b:]
t=pre+s
t=rep(t,'(basic.mask->n_proto && (basic.mask->n_proto != htons(0xffff) ||\n\t                             basic.key->n_proto != htons(ETH_P_IP))))',
      'basic.mask->n_proto != htons(0xffff) ||\n\t    basic.key->n_proto != htons(ETH_P_IP))')
a=t.index('static bool airoha_ppe_skb_l2_key(')
b=t.index('static bool airoha_ppe_foe_skb_is_local(',a)
s=t[a:b]
s=rep(s,'\tbool valid = false;','\tbool valid = false, tagged = false;')
s=rep(s,'if (!ppe_bridge_bind_enable || !skb->dev || skb->mark ||',
      'if (!ppe_bridge_bind_enable || !skb->dev || is_vlan_dev(skb->dev) || skb->mark ||')
s=rep(s,'\t\tvid = ntohs(veh->h_vlan_TCI) & VLAN_VID_MASK;',
      '\t\tvid = ntohs(veh->h_vlan_TCI) & VLAN_VID_MASK;\n\t\ttagged = true;')
s=rep(s,'\t\tvid = skb_vlan_tag_get_id(skb);','\t\tvid = skb_vlan_tag_get_id(skb);\n\t\ttagged = true;')
s=rep(s,'\tiph = (const void *)','\tif (tagged && (!vid || vid >= VLAN_VID_MASK))\n\t\treturn false;\n\tiph = (const void *)')
s=rep(s,'\tkey->vlan_proto = htons(proto);','\tkey->vlan_proto = htons(proto);\n\tkey->ingress_tagged = tagged;')
t=t[:a]+s+t[b:]
h=rep(old['airoha_eth.h'],'\t__be16 vlan_proto;\n\tu8 dest[ETH_ALEN];','\t__be16 vlan_proto;\n\tu16 ingress_tagged;\n\tu8 dest[ETH_ALEN];')
new={'airoha_ppe.c':t,'airoha_eth.h':h}
patch='Subject: [PATCH] XR: validate bridge action order and exact VLAN egress\n\n'
for n in old:
 (out/('before-'+n)).write_text(old[n]);(out/n).write_text(new[n])
 path='drivers/net/ethernet/airoha/'+n
 patch+=''.join(difflib.unified_diff(old[n].splitlines(True),new[n].splitlines(True),fromfile='a/'+path,tofile='b/'+path))
(out/'99999g-XR-exact-PPE-bridge-actions.patch').write_text(patch)
report={'prepared':True,'productionSourceChanged':False,'liveDevicesChanged':False,
 'includesEarlierSingleRedirectCandidate':True,
 'remainingBeforeHardwareQualification':['policy/context publication and revocation races','exact rule publisher','actual PPE/firmware behavior'],
 'candidateSHA256':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in new.items()}}
(out/'prepared.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
