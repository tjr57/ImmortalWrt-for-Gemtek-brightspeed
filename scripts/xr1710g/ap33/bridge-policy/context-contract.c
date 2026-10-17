
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <arpa/inet.h>
typedef uint16_t u16;
#define VLAN_VID_MASK 4095
#define ETH_P_8021Q 0x8100
#define BRIDGE_VLAN_INFO_UNTAGGED 4
#define FLOW_DISSECTOR_KEY_VLAN 0
#define FLOW_ACT_MANGLE_HDR_TYPE_ETH 1
#define PPE_PKT_TYPE_BRIDGE 7
enum {FLOW_ACTION_REDIRECT,FLOW_ACTION_VLAN_POP,FLOW_ACTION_VLAN_PUSH,
 FLOW_ACTION_CSUM,FLOW_ACTION_PPPOE_PUSH,FLOW_ACTION_MANGLE,FLOW_ACTION_DROP};
struct net {uint64_t net_cookie;};
struct net_device {int ifindex;struct net*net;struct net_device*master;
 bool port,vlan,filter,member,running,carrier,mst; unsigned long policy; unsigned int state,vlan_state;u16 pvid,proto,flags;};
struct ethhdr {unsigned char h_dest[6],h_source[6];};
struct airoha_flow_data {struct ethhdr eth;struct {struct {u16 id,proto;}hdr[2];int num;}vlan;struct {int num;u16 sid;}pppoe;};
struct airoha_l2_flow_key {uint64_t net_cookie;uint32_t ingress_ifindex,bridge_ifindex;u16 vid,vlan_proto,ingress_tagged;unsigned char dest[6],source[6];};
struct flow_action_entry {int id;struct net_device*dev;struct {u16 vid,proto,prio;}vlan;struct {u16 sid;}pppoe;struct {int htype;}mangle;};
struct flow_action {int num_entries;struct flow_action_entry entries[6];};
struct meta {int ingress_ifindex;};struct vlan {u16 vlan_id,vlan_tpid;};
struct flow_rule {struct flow_action action;bool exact,tagged;struct meta meta;struct vlan vlan[2];};
struct flow_match_meta {struct meta*key;};struct flow_match_vlan {struct vlan*key,*mask;};
struct bridge_vlan_info {u16 flags;};
static struct net ns={1},other_ns={2};
static struct net_device in,outdev,bridge,other_bridge;
#define flow_action_for_each(i,a,f) for((i)=0;(i)<(f)->num_entries&&((a)=&(f)->entries[i],1);(i)++)
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
static bool flow_rule_match_key(struct flow_rule*r,int key){(void)key;return r->tagged;}
static void flow_rule_match_meta(struct flow_rule*r,struct flow_match_meta*m){m->key=&r->meta;}
static void flow_rule_match_vlan(struct flow_rule*r,struct flow_match_vlan*m){m->key=&r->vlan[0];m->mask=&r->vlan[1];}
static bool airoha_ppe_l2_rule_exact(struct flow_rule*r){return r->exact;}
static struct net*dev_net(struct net_device*d){return d->net;}
static struct net_device*dev_get_by_index_rcu(struct net*n,int i){return n==in.net&&i==in.ifindex?&in:NULL;}
static bool is_vlan_dev(struct net_device*d){return d->vlan;}
static bool netif_is_bridge_port(struct net_device*d){return d->port;}
static struct net_device*airoha_ppe_foe_get_bridge_master_rcu(struct net_device*d){return d->master;}
static bool net_eq(struct net*a,struct net*b){return a==b;}
static bool br_vlan_enabled(struct net_device*d){return d->filter;}
static int br_vlan_get_proto(struct net_device*d,u16*p){*p=d->proto;return 0;}
static int br_vlan_get_pvid_rcu(struct net_device*d,u16*p){*p=d->pvid;return !d->pvid;}
static int br_vlan_get_info_rcu(struct net_device*d,u16 vid,struct bridge_vlan_info*i){i->flags=d->flags;return !d->member||vid!=50;}
static void ether_addr_copy(unsigned char*a,const unsigned char*b){memcpy(a,b,6);}

#define BR_STATE_FORWARDING 3
#define BR_ISOLATED (1UL<<16)
#define BR_PORT_LOCKED (1UL<<21)
#define BR_PORT_MAB (1UL<<22)
#define BR_VLAN_TUNNEL (1UL<<13)
#define BR_PROXYARP (1UL<<8)
#define BR_PROXYARP_WIFI (1UL<<10)
#define BR_NEIGH_SUPPRESS (1UL<<15)
#define BR_NEIGH_VLAN_SUPPRESS (1UL<<23)
#define BR_MRP_AWARE (1UL<<17)
#define BR_FDB_LOCAL 0
#define BR_FDB_LOCKED 1
#define READ_ONCE(x) (x)
#define EXPORT_SYMBOL_GPL(x)
struct net_bridge {int unused;};
struct net_bridge_port {struct net_device *dev;};
struct net_bridge_fdb_entry {unsigned long flags;struct net_bridge_port *dst;bool present,expired;};
static struct net_bridge br;
static struct net_bridge_port srcport,dstport;
static struct net_bridge_fdb_entry entries[2];
static bool netif_running(struct net_device*d){return d->running;}
static bool netif_carrier_ok(struct net_device*d){return d->carrier;}
static unsigned int br_port_get_stp_state(struct net_device*d){return d->state;}
static bool br_port_flag_is_set(struct net_device*d,unsigned long f){return d->policy&f;}
static bool br_mst_enabled(struct net_device*d){return d->mst;}
static bool netif_is_bridge_master(const struct net_device*d){return d==&bridge;}
static bool is_valid_ether_addr(const unsigned char*a){return !(a[0]&1)&&!!memcmp(a,(unsigned char[6]){0},6);}
static struct net_bridge*netdev_priv(const struct net_device*d){(void)d;return &br;}
static bool test_bit(int i,const unsigned long*f){return *f&(1UL<<i);}
static bool has_expired(struct net_bridge*b,struct net_bridge_fdb_entry*f){(void)b;return f->expired;}
static struct net_bridge_fdb_entry*br_fdb_find_rcu(struct net_bridge*b,const unsigned char*a,u16 vid){
 (void)b;
 if((vid!=0&&vid!=50)||a[5]<1||a[5]>2)return NULL;
 struct net_bridge_fdb_entry*f=&entries[a[5]-1];return f->present?f:NULL;
}
struct flow_cls_offload {struct {unsigned int chain_index;void *extack;} common;};
#define NL_SET_ERR_MSG_MOD(a,b) ((void)(a),(void)(b))
bool br_fdb_forward_to_rcu(const struct net_device *br_dev,
                          const struct net_device *port_dev,
                          const unsigned char *addr, u16 vid)
{
 const struct net_bridge_port *dst;
 struct net_bridge_fdb_entry *f;
 struct net_bridge *br;

 if (!netif_is_bridge_master(br_dev) || !is_valid_ether_addr(addr))
  return false;
 br = netdev_priv(br_dev);
 f = br_fdb_find_rcu(br, addr, vid);
 if (!f || test_bit(BR_FDB_LOCAL, &f->flags) ||
     test_bit(BR_FDB_LOCKED, &f->flags) || has_expired(br, f))
  return false;
 dst = READ_ONCE(f->dst);
 return dst && dst->dev == port_dev;
}
static bool airoha_ppe_l2_port_eligible(struct net_device *dev)
{
 const unsigned long unsupported = BR_ISOLATED | BR_PORT_LOCKED | BR_PORT_MAB |
  BR_VLAN_TUNNEL | BR_PROXYARP | BR_PROXYARP_WIFI | BR_NEIGH_SUPPRESS |
  BR_NEIGH_VLAN_SUPPRESS | BR_MRP_AWARE;

 return netif_running(dev) && netif_carrier_ok(dev) &&
        br_port_get_stp_state(dev) == BR_STATE_FORWARDING &&
        !br_port_flag_is_set(dev, unsupported);
}
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
static bool old_context(struct flow_rule *rule,
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
static bool br_vlan_forwarding_rcu(const struct net_device*d,u16 vid){return d->member&&vid==50&&d->vlan_state==BR_STATE_FORWARDING;}
static bool pre_vlan_context(struct flow_rule *rule,
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
     !netif_is_bridge_port(indev) || !netif_is_bridge_port(odev) ||
     !airoha_ppe_l2_port_eligible(indev) ||
     !airoha_ppe_l2_port_eligible(odev))
  goto out;
 master = airoha_ppe_foe_get_bridge_master_rcu(indev);
 if (!master || br_mst_enabled(master) ||
     !net_eq(dev_net(indev), dev_net(odev)) ||
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
 /* A normal bridge preserves PCP/DEI on tagged-to-tagged forwarding.
  * POP/PUSH with priority zero is a valid explicit TC action, but does not
  * preserve that bridge policy for all packets of a MAC-only template.
  */
 if (tagged && !untagged)
  goto out;
 if (!br_fdb_forward_to_rcu(master, indev, data->eth.h_source, vid) ||
     !br_fdb_forward_to_rcu(master, odev, data->eth.h_dest, vid))
  goto out;
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
     !netif_is_bridge_port(indev) || !netif_is_bridge_port(odev) ||
     !airoha_ppe_l2_port_eligible(indev) ||
     !airoha_ppe_l2_port_eligible(odev))
  goto out;
 master = airoha_ppe_foe_get_bridge_master_rcu(indev);
 if (!master || br_mst_enabled(master) ||
     !net_eq(dev_net(indev), dev_net(odev)) ||
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
      br_vlan_get_info_rcu(odev, vid, &info) ||
      !br_vlan_forwarding_rcu(indev, vid) ||
      !br_vlan_forwarding_rcu(odev, vid))
   goto out;
  untagged = !!(info.flags & BRIDGE_VLAN_INFO_UNTAGGED);
 } else if (tagged) {
  goto out;
 }
 /* A normal bridge preserves PCP/DEI on tagged-to-tagged forwarding.
  * POP/PUSH with priority zero is a valid explicit TC action, but does not
  * preserve that bridge policy for all packets of a MAC-only template.
  */
 if (tagged && !untagged)
  goto out;
 if (!br_fdb_forward_to_rcu(master, indev, data->eth.h_source, vid) ||
     !br_fdb_forward_to_rcu(master, odev, data->eth.h_dest, vid))
  goto out;
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
static int chain_guard(struct flow_cls_offload*f){
	/* FOE has no classifier chain/goto context. */
	if (f->common.chain_index) {
		NL_SET_ERR_MSG_MOD(f->common.extack, "PPE only represents TC chain zero");
		return -EOPNOTSUPP;
	}


return 0;
}

static int checks;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed line %d\n",__LINE__);return 1;}checks++;}while(0)
static struct flow_rule rule;
static struct airoha_flow_data data;
static struct airoha_l2_flow_key key;
static struct flow_action_entry action(int id){return (struct flow_action_entry){.id=id,.dev=&outdev,.vlan={50,htons(ETH_P_8021Q),0}};}
static void reset(void){
 rule=(struct flow_rule){.exact=true,.meta={11}};
 bridge=(struct net_device){.ifindex=10,.net=&ns,.filter=true,.proto=ETH_P_8021Q};
 other_bridge=(struct net_device){.ifindex=20,.net=&ns};
 in=(struct net_device){.ifindex=11,.net=&ns,.master=&bridge,.port=true,.member=true,.pvid=50,.running=true,.carrier=true,.state=BR_STATE_FORWARDING,.vlan_state=BR_STATE_FORWARDING};
 outdev=in;outdev.ifindex=12;outdev.flags=BRIDGE_VLAN_INFO_UNTAGGED;
 rule.vlan[0]=(struct vlan){50,htons(ETH_P_8021Q)};rule.vlan[1]=(struct vlan){VLAN_VID_MASK,htons(0xffff)};
 rule.action.num_entries=1;rule.action.entries[0]=action(FLOW_ACTION_REDIRECT);
 data=(struct airoha_flow_data){.eth={{2,0,0,0,0,2},{2,0,0,0,0,1}}};
 key=(struct airoha_l2_flow_key){0};srcport.dev=&in;dstport.dev=&outdev;
 entries[0]=(struct net_bridge_fdb_entry){.present=true,.dst=&srcport};
 entries[1]=(struct net_bridge_fdb_entry){.present=true,.dst=&dstport};
}
int main(void){
 /* New negative control: port forwards, but ingress/egress VLAN is blocked. */
 for(int side=0;side<2;side++)for(int state=0;state<256;state++){
  reset();struct net_device*d=side?&outdev:&in;d->vlan_state=state;
  CHECK(pre_vlan_context(&rule,&outdev,&data,&key));
  CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key)==(state==BR_STATE_FORWARDING));
 }

 reset();CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(key.vid==50&&key.ingress_tagged==0);
 /* Previous candidate accepts blocked/learning ports and incompatible policy. */
 for(int side=0;side<2;side++)for(int state=0;state<=4;state++){
  reset();struct net_device*d=side?&outdev:&in;d->state=state;
  CHECK(old_context(&rule,&outdev,&data,&key));
  CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key)==(state==BR_STATE_FORWARDING));
 }
 for(int side=0;side<2;side++)for(int bit=0;bit<25;bit++){
  reset();struct net_device*d=side?&outdev:&in;d->policy=1UL<<bit;
  bool unsupported=d->policy&(BR_ISOLATED|BR_PORT_LOCKED|BR_PORT_MAB|BR_VLAN_TUNNEL|BR_PROXYARP|BR_PROXYARP_WIFI|BR_NEIGH_SUPPRESS|BR_NEIGH_VLAN_SUPPRESS|BR_MRP_AWARE);
  CHECK(old_context(&rule,&outdev,&data,&key));CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key)==!unsupported);
 }
 for(int side=0;side<2;side++)for(int fault=0;fault<7;fault++){
  reset();struct net_bridge_fdb_entry*f=&entries[side];
  switch(fault){case 0:f->present=false;break;case 1:f->flags=1UL<<BR_FDB_LOCAL;break;
   case 2:f->flags=1UL<<BR_FDB_LOCKED;break;case 3:f->expired=true;break;
   case 4:f->dst=NULL;break;case 5:f->dst=side?&srcport:&dstport;break;
   case 6:(side?data.eth.h_dest:data.eth.h_source)[0]=1;break;}
  CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 }
 for(int side=0;side<2;side++)for(int carrier=0;carrier<2;carrier++){
  reset();struct net_device*d=side?&outdev:&in;if(carrier)d->carrier=false;else d->running=false;
  CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 }
 reset();bridge.mst=true;CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 reset();rule.tagged=true;rule.action.num_entries=2;rule.action.entries[0]=action(FLOW_ACTION_VLAN_POP);rule.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(key.ingress_tagged==1&&data.vlan.num==0);
 outdev.flags=0;rule.action.num_entries=3;rule.action.entries[1]=action(FLOW_ACTION_VLAN_PUSH);rule.action.entries[2]=action(FLOW_ACTION_REDIRECT);
 CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 /* Canonical action equivalence alone did not imply bridge PCP preservation. */
 for(int pcp=0;pcp<8;pcp++)for(int dei=0;dei<2;dei++){int bridge_tci=(pcp<<13)|(dei<<12)|50;
  int explicit_pop_push_tci=50;CHECK((bridge_tci==explicit_pop_push_tci)==(!pcp&&!dei));}
 reset();outdev.flags=0;rule.action.num_entries=2;rule.action.entries[0]=action(FLOW_ACTION_VLAN_PUSH);rule.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(data.vlan.num==1&&data.vlan.hdr[0].id==50);
 for(int fault=0;fault<13;fault++){
  reset();switch(fault){case 0:in.member=false;break;case 1:outdev.member=false;break;case 2:in.pvid=0;break;
   case 3:in.pvid=51;break;case 4:bridge.proto=0x88a8;break;case 5:outdev.master=&other_bridge;break;
   case 6:outdev.net=&other_ns;break;case 7:in.port=false;break;case 8:outdev.port=false;break;
   case 9:in.vlan=true;break;case 10:outdev.vlan=true;break;case 11:rule.exact=false;break;case 12:rule.meta.ingress_ifindex=99;break;}
  CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 }
 reset();bridge.filter=false;CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(key.vid==0);
 struct flow_cls_offload f={0};CHECK(chain_guard(&f)==0);
 for(unsigned int i=1;i<65536;i++){f.common.chain_index=i;CHECK(chain_guard(&f)==-EOPNOTSUPP);}
 f.common.chain_index=UINT32_MAX;CHECK(chain_guard(&f)==-EOPNOTSUPP);
 printf("%d checks; prior context negatives reproduced; new FDB/STP/policy/tag/chain guards passed\n",checks);return 0;
}
