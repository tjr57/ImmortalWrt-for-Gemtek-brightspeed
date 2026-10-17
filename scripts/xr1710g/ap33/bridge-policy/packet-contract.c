
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
 bool port,vlan,filter,member;u16 pvid,proto,flags;};
struct ethhdr {unsigned char h_dest[6],h_source[6];u16 h_proto;};
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
static void airoha_ppe_flow_mangle_eth(struct flow_action_entry*a,struct ethhdr*b){(void)a;(void)b;}
static int old_interpret(struct flow_rule*rule,struct airoha_flow_data*result){
 struct airoha_flow_data data={0};struct net_device*odev=NULL;
 int offload_type=PPE_PKT_TYPE_BRIDGE,i;struct flow_action_entry*act;
	flow_action_for_each(i, act, &rule->action) {
		switch (act->id) {
		case FLOW_ACTION_MANGLE:
			if (offload_type == PPE_PKT_TYPE_BRIDGE)
				return -EOPNOTSUPP;

			if (act->mangle.htype == FLOW_ACT_MANGLE_HDR_TYPE_ETH)
				airoha_ppe_flow_mangle_eth(act, &data.eth);
			break;
		case FLOW_ACTION_REDIRECT:
			odev = act->dev;
			break;
		case FLOW_ACTION_CSUM:
			break;
		case FLOW_ACTION_VLAN_PUSH:
			if (data.vlan.num == 2 ||
			    act->vlan.proto != htons(ETH_P_8021Q))
				return -EOPNOTSUPP;

			data.vlan.hdr[data.vlan.num].id = act->vlan.vid;
			data.vlan.hdr[data.vlan.num].proto = act->vlan.proto;
			data.vlan.num++;
			break;
		case FLOW_ACTION_VLAN_POP:
			break;
		case FLOW_ACTION_PPPOE_PUSH:
			if (data.pppoe.num == 1 || data.vlan.num == 2)
				return -EOPNOTSUPP;

			data.pppoe.sid = act->pppoe.sid;
			data.pppoe.num++;
			break;
		default:
			return -EOPNOTSUPP;
		}
	}

 (void)odev;*result=data;return 0;
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


typedef uint8_t u8;
#define ETH_HLEN 14
#define VLAN_ETH_HLEN 18
#define ETH_P_IP 0x0800
struct iphdr {unsigned char ihl:4,version:4;u8 tos;u16 tot_len,id,frag_off;u8 ttl,protocol;u16 check;uint32_t saddr,daddr;};
struct vlan_ethhdr {u8 dest[6],source[6];u16 h_vlan_proto,h_vlan_TCI,h_vlan_encapsulated_proto;};
struct sk_buff {struct net_device*dev;u8*head,*mac,*tail;bool has_mac,has_tag;u16 vlan_proto,vlan_tci;uint32_t mark;};
static bool ppe_bridge_bind_enable=true;
static bool skb_mac_header_was_set(struct sk_buff*s){return s->has_mac;}
static struct ethhdr*eth_hdr(struct sk_buff*s){return (void*)s->mac;}
static u8*skb_tail_pointer(struct sk_buff*s){return s->tail;}
static bool is_valid_ether_addr(const u8*m){return !(m[0]&1)&&(m[0]|m[1]|m[2]|m[3]|m[4]|m[5]);}
static bool eth_type_vlan(u16 p){return p==htons(ETH_P_8021Q)||p==htons(0x88a8);}
static bool skb_vlan_tag_present(struct sk_buff*s){return s->has_tag;}
static u16 skb_vlan_tag_get_id(struct sk_buff*s){return s->vlan_tci&VLAN_VID_MASK;}
static u16 vlan_dev_vlan_proto(struct net_device*d){(void)d;return htons(ETH_P_8021Q);}
static u16 vlan_dev_vlan_id(struct net_device*d){return d->pvid;}
static bool ip_is_fragment(const struct iphdr*i){return !!(i->frag_off&htons(0x3fff));}
static bool old_packet_key(struct sk_buff *skb,
                               struct airoha_l2_flow_key *key)
{
	struct net_device *master;
	const struct ethhdr *eh;
	const struct iphdr *iph;
	const struct vlan_ethhdr *veh;
	u16 vid = 0, proto = ETH_P_8021Q;
	unsigned int offset = ETH_HLEN;
	bool valid = false;

	memset(key, 0, sizeof(*key));
	if (!ppe_bridge_bind_enable || !skb->dev || skb->mark ||
	    !skb_mac_header_was_set(skb))
		return false;
	eh = eth_hdr(skb);
	if ((u8 *)eh < skb->head || (u8 *)(eh + 1) > skb_tail_pointer(skb) ||
	    !is_valid_ether_addr(eh->h_source) || !is_valid_ether_addr(eh->h_dest))
		return false;
	if (eth_type_vlan(eh->h_proto)) {
		if (skb_vlan_tag_present(skb) || is_vlan_dev(skb->dev) ||
		    eh->h_proto != htons(ETH_P_8021Q) ||
		    (u8 *)eh + VLAN_ETH_HLEN > skb_tail_pointer(skb))
			return false;
		veh = (const void *)eh;
		vid = ntohs(veh->h_vlan_TCI) & VLAN_VID_MASK;
		if (veh->h_vlan_encapsulated_proto != htons(ETH_P_IP))
			return false;
		offset = VLAN_ETH_HLEN;
	} else if (eh->h_proto != htons(ETH_P_IP)) {
		return false;
	} else if (skb_vlan_tag_present(skb)) {
		if (is_vlan_dev(skb->dev) || skb->vlan_proto != htons(ETH_P_8021Q))
			return false;
		vid = skb_vlan_tag_get_id(skb);
	} else if (is_vlan_dev(skb->dev)) {
		if (vlan_dev_vlan_proto(skb->dev) != htons(ETH_P_8021Q))
			return false;
		vid = vlan_dev_vlan_id(skb->dev);
	}
	iph = (const void *)((const u8 *)eh + offset);
	if ((u8 *)(iph + 1) > skb_tail_pointer(skb) || iph->version != 4 ||
	    iph->ihl < 5 || (u8 *)iph + iph->ihl * 4 > skb_tail_pointer(skb) ||
	    ip_is_fragment(iph) ||
	    (iph->protocol != IPPROTO_TCP && iph->protocol != IPPROTO_UDP))
		return false;
	rcu_read_lock();
	master = airoha_ppe_foe_get_bridge_master_rcu(skb->dev);
	if (!master)
		goto out;
	if (br_vlan_enabled(master)) {
		struct bridge_vlan_info vinfo;
		if (!vid && (!netif_is_bridge_port(skb->dev) ||
		    br_vlan_get_pvid_rcu(skb->dev, &vid)))
			goto out;
		if (!vid || br_vlan_get_proto(master, &proto) || proto != ETH_P_8021Q ||
		    br_vlan_get_info_rcu(skb->dev, vid, &vinfo))
			goto out;
	} else if (vid) {
		/* Tagged packets on a nonfiltering bridge have no isolated VID. */
		goto out;
	}
	key->net_cookie = dev_net(skb->dev)->net_cookie;
	key->ingress_ifindex = skb->dev->ifindex;
	key->bridge_ifindex = master->ifindex;
	key->vid = vid;
	key->vlan_proto = htons(proto);
	ether_addr_copy(key->dest, eh->h_dest);
	ether_addr_copy(key->source, eh->h_source);
	valid = true;
out:
	rcu_read_unlock();
	return valid;
}
static bool vlan_forwarding=true;
static bool br_vlan_forwarding_rcu(const struct net_device*d,u16 vid){return d->member&&vid==50&&vlan_forwarding;}
static bool pre_vlan_packet_key(struct sk_buff *skb,
                               struct airoha_l2_flow_key *key)
{
	struct net_device *master;
	const struct ethhdr *eh;
	const struct iphdr *iph;
	const struct vlan_ethhdr *veh;
	u16 vid = 0, proto = ETH_P_8021Q;
	unsigned int offset = ETH_HLEN;
	bool valid = false, tagged = false;

	memset(key, 0, sizeof(*key));
	if (!ppe_bridge_bind_enable || !skb->dev || is_vlan_dev(skb->dev) || skb->mark ||
	    !skb_mac_header_was_set(skb))
		return false;
	eh = eth_hdr(skb);
	if ((u8 *)eh < skb->head || (u8 *)(eh + 1) > skb_tail_pointer(skb) ||
	    !is_valid_ether_addr(eh->h_source) || !is_valid_ether_addr(eh->h_dest))
		return false;
	if (eth_type_vlan(eh->h_proto)) {
		if (skb_vlan_tag_present(skb) || is_vlan_dev(skb->dev) ||
		    eh->h_proto != htons(ETH_P_8021Q) ||
		    (u8 *)eh + VLAN_ETH_HLEN > skb_tail_pointer(skb))
			return false;
		veh = (const void *)eh;
		vid = ntohs(veh->h_vlan_TCI) & VLAN_VID_MASK;
		tagged = true;
		if (veh->h_vlan_encapsulated_proto != htons(ETH_P_IP))
			return false;
		offset = VLAN_ETH_HLEN;
	} else if (eh->h_proto != htons(ETH_P_IP)) {
		return false;
	} else if (skb_vlan_tag_present(skb)) {
		if (is_vlan_dev(skb->dev) || skb->vlan_proto != htons(ETH_P_8021Q))
			return false;
		vid = skb_vlan_tag_get_id(skb);
		tagged = true;
	} else if (is_vlan_dev(skb->dev)) {
		if (vlan_dev_vlan_proto(skb->dev) != htons(ETH_P_8021Q))
			return false;
		vid = vlan_dev_vlan_id(skb->dev);
	}
	if (tagged && (!vid || vid >= VLAN_VID_MASK))
		return false;
	iph = (const void *)((const u8 *)eh + offset);
	if ((u8 *)(iph + 1) > skb_tail_pointer(skb) || iph->version != 4 ||
	    iph->ihl < 5 || (u8 *)iph + iph->ihl * 4 > skb_tail_pointer(skb) ||
	    ip_is_fragment(iph) ||
	    (iph->protocol != IPPROTO_TCP && iph->protocol != IPPROTO_UDP))
		return false;
	rcu_read_lock();
	master = airoha_ppe_foe_get_bridge_master_rcu(skb->dev);
	if (!master)
		goto out;
	if (br_vlan_enabled(master)) {
		struct bridge_vlan_info vinfo;
		if (!vid && (!netif_is_bridge_port(skb->dev) ||
		    br_vlan_get_pvid_rcu(skb->dev, &vid)))
			goto out;
		if (!vid || br_vlan_get_proto(master, &proto) || proto != ETH_P_8021Q ||
		    br_vlan_get_info_rcu(skb->dev, vid, &vinfo))
			goto out;
	} else if (vid) {
		/* Tagged packets on a nonfiltering bridge have no isolated VID. */
		goto out;
	}
	key->net_cookie = dev_net(skb->dev)->net_cookie;
	key->ingress_ifindex = skb->dev->ifindex;
	key->bridge_ifindex = master->ifindex;
	key->vid = vid;
	key->vlan_proto = htons(proto);
	key->ingress_tagged = tagged;
	ether_addr_copy(key->dest, eh->h_dest);
	ether_addr_copy(key->source, eh->h_source);
	valid = true;
out:
	rcu_read_unlock();
	return valid;
}
static bool airoha_ppe_skb_l2_key(struct sk_buff *skb,
                               struct airoha_l2_flow_key *key)
{
	struct net_device *master;
	const struct ethhdr *eh;
	const struct iphdr *iph;
	const struct vlan_ethhdr *veh;
	u16 vid = 0, proto = ETH_P_8021Q;
	unsigned int offset = ETH_HLEN;
	bool valid = false, tagged = false;

	memset(key, 0, sizeof(*key));
	if (!ppe_bridge_bind_enable || !skb->dev || is_vlan_dev(skb->dev) || skb->mark ||
	    !skb_mac_header_was_set(skb))
		return false;
	eh = eth_hdr(skb);
	if ((u8 *)eh < skb->head || (u8 *)(eh + 1) > skb_tail_pointer(skb) ||
	    !is_valid_ether_addr(eh->h_source) || !is_valid_ether_addr(eh->h_dest))
		return false;
	if (eth_type_vlan(eh->h_proto)) {
		if (skb_vlan_tag_present(skb) || is_vlan_dev(skb->dev) ||
		    eh->h_proto != htons(ETH_P_8021Q) ||
		    (u8 *)eh + VLAN_ETH_HLEN > skb_tail_pointer(skb))
			return false;
		veh = (const void *)eh;
		vid = ntohs(veh->h_vlan_TCI) & VLAN_VID_MASK;
		tagged = true;
		if (veh->h_vlan_encapsulated_proto != htons(ETH_P_IP))
			return false;
		offset = VLAN_ETH_HLEN;
	} else if (eh->h_proto != htons(ETH_P_IP)) {
		return false;
	} else if (skb_vlan_tag_present(skb)) {
		if (is_vlan_dev(skb->dev) || skb->vlan_proto != htons(ETH_P_8021Q))
			return false;
		vid = skb_vlan_tag_get_id(skb);
		tagged = true;
	} else if (is_vlan_dev(skb->dev)) {
		if (vlan_dev_vlan_proto(skb->dev) != htons(ETH_P_8021Q))
			return false;
		vid = vlan_dev_vlan_id(skb->dev);
	}
	if (tagged && (!vid || vid >= VLAN_VID_MASK))
		return false;
	iph = (const void *)((const u8 *)eh + offset);
	if ((u8 *)(iph + 1) > skb_tail_pointer(skb) || iph->version != 4 ||
	    iph->ihl < 5 || (u8 *)iph + iph->ihl * 4 > skb_tail_pointer(skb) ||
	    ip_is_fragment(iph) ||
	    (iph->protocol != IPPROTO_TCP && iph->protocol != IPPROTO_UDP))
		return false;
	rcu_read_lock();
	master = airoha_ppe_foe_get_bridge_master_rcu(skb->dev);
	if (!master)
		goto out;
	if (br_vlan_enabled(master)) {
		struct bridge_vlan_info vinfo;
		if (!vid && (!netif_is_bridge_port(skb->dev) ||
		    br_vlan_get_pvid_rcu(skb->dev, &vid)))
			goto out;
		if (!vid || br_vlan_get_proto(master, &proto) || proto != ETH_P_8021Q ||
		    br_vlan_get_info_rcu(skb->dev, vid, &vinfo) ||
		    !br_vlan_forwarding_rcu(skb->dev, vid))
			goto out;
	} else if (vid) {
		/* Tagged packets on a nonfiltering bridge have no isolated VID. */
		goto out;
	}
	key->net_cookie = dev_net(skb->dev)->net_cookie;
	key->ingress_ifindex = skb->dev->ifindex;
	key->bridge_ifindex = master->ifindex;
	key->vid = vid;
	key->vlan_proto = htons(proto);
	key->ingress_tagged = tagged;
	ether_addr_copy(key->dest, eh->h_dest);
	ether_addr_copy(key->source, eh->h_source);
	valid = true;
out:
	rcu_read_unlock();
	return valid;
}
static int checks,accepted;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed line %d\n",__LINE__);return 1;}checks++;}while(0)
static struct flow_action_entry action(int id){struct flow_action_entry a={0};a.id=id;a.dev=&outdev;a.vlan.vid=50;a.vlan.proto=htons(ETH_P_8021Q);a.pppoe.sid=7;return a;}
/* Independent packet-stack evaluator, including terminal redirect semantics. */
static bool software(struct flow_rule*r,bool tagged,int priority,int*depth,int*vid,int*prio){
 int vs[8]={50},ps[8]={priority},n=tagged?1:0;
 for(int i=0;i<r->action.num_entries;i++){
  struct flow_action_entry*a=&r->action.entries[i];
  if(a->id==FLOW_ACTION_VLAN_PUSH){for(int j=n;j>0;j--){vs[j]=vs[j-1];ps[j]=ps[j-1];}vs[0]=a->vlan.vid;ps[0]=a->vlan.prio;n++;}
  else if(a->id==FLOW_ACTION_VLAN_POP){if(!n)return false;for(int j=0;j<n-1;j++){vs[j]=vs[j+1];ps[j]=ps[j+1];}n--;}
  else if(a->id==FLOW_ACTION_REDIRECT){if(!a->dev)return false;*depth=n;*vid=n?vs[0]:0;*prio=n?ps[0]:0;return true;}
  else return false;
 }
 return false;
}
static void reset(struct flow_rule*r){
 memset(r,0,sizeof(*r));*r=(struct flow_rule){.exact=true,.meta={11}};
 bridge=(struct net_device){.ifindex=10,.net=&ns,.filter=true,.proto=ETH_P_8021Q};
 other_bridge=(struct net_device){.ifindex=20,.net=&ns};
 in=(struct net_device){.ifindex=11,.net=&ns,.master=&bridge,.port=true,.member=true,.pvid=50};
 outdev=(struct net_device){.ifindex=12,.net=&ns,.master=&bridge,.port=true,.member=true,.pvid=50,.flags=BRIDGE_VLAN_INFO_UNTAGGED};
 r->vlan[0]=(struct vlan){50,htons(ETH_P_8021Q)};r->vlan[1]=(struct vlan){VLAN_VID_MASK,htons(0xffff)};
 r->action.num_entries=1;r->action.entries[0]=action(FLOW_ACTION_REDIRECT);
}

static int packet_cases(void){
 _Alignas(8) unsigned char buffer[80]={0};unsigned char*buf=buffer+2;
 struct flow_rule rule;struct sk_buff skb={.dev=&in,.head=buf,.mac=buf,.tail=buf+34,.has_mac=true};
 struct ethhdr*eth=(void*)buf;struct iphdr*ip=(void*)(buf+14);
 struct airoha_l2_flow_key old_plain,old_tag,new_plain,new_tag,meta_tag;
 reset(&rule);eth->h_source[0]=2;eth->h_dest[0]=4;eth->h_proto=htons(ETH_P_IP);
 ip->version=4;ip->ihl=5;ip->protocol=IPPROTO_UDP;
 CHECK(old_packet_key(&skb,&old_plain));CHECK(airoha_ppe_skb_l2_key(&skb,&new_plain));
 vlan_forwarding=false;CHECK(pre_vlan_packet_key(&skb,&new_plain));CHECK(!airoha_ppe_skb_l2_key(&skb,&new_plain));
 vlan_forwarding=true;CHECK(airoha_ppe_skb_l2_key(&skb,&new_plain));

 skb.has_tag=true;skb.vlan_tci=50;skb.vlan_proto=htons(ETH_P_8021Q);
 CHECK(old_packet_key(&skb,&old_tag));CHECK(airoha_ppe_skb_l2_key(&skb,&new_tag));
 CHECK(!memcmp(&old_plain,&old_tag,sizeof(old_plain)));
 CHECK(memcmp(&new_plain,&new_tag,sizeof(new_plain)));
 CHECK(new_plain.vid==50&&new_tag.vid==50&&!new_plain.ingress_tagged&&new_tag.ingress_tagged);
 meta_tag=new_tag;
 for(int prio=0;prio<8;prio++){skb.vlan_tci=50|(prio<<13);CHECK(airoha_ppe_skb_l2_key(&skb,&new_tag));CHECK(!memcmp(&meta_tag,&new_tag,sizeof(new_tag)));}
 skb.vlan_tci=0;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_tci=4095;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_tci=51;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_tci=50;skb.vlan_proto=htons(0x88a8);CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_proto=htons(ETH_P_8021Q);skb.has_tag=false;
 memmove(buf+18,buf+14,20);skb.tail=buf+38;
 struct vlan_ethhdr*vh=(void*)buf;vh->h_vlan_proto=htons(ETH_P_8021Q);vh->h_vlan_TCI=htons(50);vh->h_vlan_encapsulated_proto=htons(ETH_P_IP);
 CHECK(airoha_ppe_skb_l2_key(&skb,&new_tag));CHECK(!memcmp(&meta_tag,&new_tag,sizeof(new_tag)));
 skb.has_tag=true;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));skb.has_tag=false;
 vh->h_vlan_TCI=0;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));vh->h_vlan_TCI=htons(50);
 vh->h_vlan_encapsulated_proto=htons(ETH_P_8021Q);CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));vh->h_vlan_encapsulated_proto=htons(ETH_P_IP);
 for(int len=0;len<38;len++){skb.tail=buf+len;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));}skb.tail=buf+38;
 ip=(void*)(buf+18);ip->frag_off=htons(0x2000);CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));ip->frag_off=0;
 ip->protocol=IPPROTO_ICMP;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));ip->protocol=IPPROTO_TCP;
 skb.mark=1;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));skb.mark=0;
 in.vlan=true;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));in.vlan=false;
 bridge.filter=false;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 return 0;
}

int main(void){
 CHECK(packet_cases()==0);
 struct flow_rule r;struct airoha_flow_data data;struct airoha_l2_flow_key key,untagged_key;
 reset(&r);data=(struct airoha_flow_data){0};key=(struct airoha_l2_flow_key){0};
 CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(key.vid==50&&key.ingress_tagged==0&&data.vlan.num==0);untagged_key=key;
 r.tagged=true;r.action.num_entries=2;r.action.entries[0]=action(FLOW_ACTION_VLAN_POP);r.action.entries[1]=action(FLOW_ACTION_REDIRECT);key=(struct airoha_l2_flow_key){0};
 CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(key.ingress_tagged==1&&memcmp(&key,&untagged_key,sizeof(key)));
 outdev.flags=0;CHECK(!airoha_ppe_l2_context(&r,&outdev,&data,&key));
 r.action.num_entries=3;r.action.entries[1]=action(FLOW_ACTION_VLAN_PUSH);r.action.entries[2]=action(FLOW_ACTION_REDIRECT);
 CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(data.vlan.num==1&&data.vlan.hdr[0].id==50);
 for(int mutation=0;mutation<13;mutation++){
  reset(&r);
  switch(mutation){
   case 0:in.member=false;break;case 1:outdev.member=false;break;case 2:in.pvid=0;break;
   case 3:in.pvid=51;break;case 4:bridge.proto=0x88a8;break;case 5:outdev.master=&other_bridge;break;
   case 6:outdev.net=&other_ns;break;case 7:in.port=false;break;case 8:outdev.port=false;break;
   case 9:in.vlan=true;break;case 10:outdev.vlan=true;break;case 11:r.exact=false;break;case 12:r.meta.ingress_ifindex=99;break;
  }
  CHECK(!airoha_ppe_l2_context(&r,&outdev,&data,&key));
 }
 reset(&r);CHECK(!airoha_ppe_l2_context(&r,&in,&data,&key));CHECK(!airoha_ppe_l2_context(&r,NULL,&data,&key));
 reset(&r);bridge.filter=false;CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(key.vid==0);r.tagged=true;CHECK(!airoha_ppe_l2_context(&r,&outdev,&data,&key));
 /* Old production parser ignores priority and executes actions after redirect. */
 reset(&r);r.action.num_entries=2;r.action.entries[0]=action(FLOW_ACTION_VLAN_PUSH);r.action.entries[0].vlan.prio=7;r.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(old_interpret(&r,&data)==0&&data.vlan.hdr[0].id==50);CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 r.action.entries[0]=action(FLOW_ACTION_REDIRECT);r.action.entries[1]=action(FLOW_ACTION_VLAN_PUSH);
 CHECK(old_interpret(&r,&data)==0&&data.vlan.num==1);CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 r.action.entries[0]=action(FLOW_ACTION_VLAN_POP);r.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(old_interpret(&r,&data)==0);CHECK(!airoha_ppe_l2_actions(&r,50,false,true,&data));
 /* Enumerate short action programs; every accepted case must produce the
  * same concrete packet stack as software, for every ingress priority. */
 for(int len=0;len<=5;len++){
  int total=1;for(int j=0;j<len;j++)total*=7;
  for(int code=0;code<total;code++){
   reset(&r);r.action.num_entries=len;int v=code;
   for(int j=0;j<len;j++){r.action.entries[j]=action(v%7);v/=7;}
   for(int tagged=0;tagged<2;tagged++)for(int untagged=0;untagged<2;untagged++){
    data=(struct airoha_flow_data){0};
    bool ok=airoha_ppe_l2_actions(&r,50,tagged,untagged,&data);
    checks++;
    if(!ok)continue;
    accepted++;
    for(int p=0;p<8;p++){int depth,vid,prio;CHECK(software(&r,tagged,p,&depth,&vid,&prio));CHECK(depth==data.vlan.num);CHECK(depth==!untagged);if(depth){CHECK(vid==data.vlan.hdr[0].id);CHECK(prio==0);}}
   }
  }
 }
 CHECK(accepted==4);
 reset(&r);r.action.num_entries=2;r.action.entries[0]=action(FLOW_ACTION_VLAN_PUSH);r.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 for(int p=1;p<8;p++){r.action.entries[0].vlan.prio=p;CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));}
 r.action.entries[0].vlan.prio=0;r.action.entries[0].vlan.vid=51;CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 r.action.entries[0].vlan.vid=50;r.action.entries[0].vlan.proto=htons(0x88a8);CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 reset(&r);CHECK(!airoha_ppe_l2_actions(&r,4095,false,true,&data));r.action.entries[0].dev=NULL;CHECK(!airoha_ppe_l2_actions(&r,0,false,true,&data));
 printf("%d checks; %d canonical programs accepted; packet-stack equivalence and context negatives passed\n",checks,accepted);return 0;
}
