// SPDX-License-Identifier: GPL-2.0-only
/* Read-only CPU observation of the owner's generated DS-field probes.
 * No filters, packet modification, MMIO writes or arbitrary endpoints.
 */
#include <linux/module.h>
#include <linux/debugfs.h>
#include <linux/seq_file.h>
#include <linux/skbuff.h>
#include <linux/etherdevice.h>
#include <linux/if_vlan.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <linux/bitmap.h>
#include <linux/of.h>

#define NPHASE 12
#define NSEQ 400
static const u8 expected[NPHASE] = {0,184,40,0,1,2,3,0,185,186,187,184};
static const u8 pc[ETH_ALEN] = {0x98,0xb7,0x85,0x1e,0xd5,0xdf};
static const u8 phone[ETH_ALEN] = {0x0c,0xbd,0x75,0x21,0xb0,0xdd};
struct xr_count {
 u32 copies, unique, ds_bad, ttl_bad, first_hash, last_hash;
 u32 first_dev, last_dev, tagged;
};
static struct xr_count counts[3][NPHASE];
static unsigned long seen[3][NPHASE][BITS_TO_LONGS(NSEQ)];
static u32 malformed;
static DEFINE_SPINLOCK(xr_lock);
static struct dentry *entry;

static int xr_receive(struct sk_buff *skb, struct net_device *dev,
                      struct packet_type *pt, struct net_device *orig_dev)
{
 struct ethhdr eh;
 struct iphdr ip;
 struct udphdr udp;
 struct vlan_hdr vh;
 __be32 mark[4];
 __be16 proto;
 unsigned int run, phase, seq, dir, depth=0;
 int off;
 struct xr_count *c;
 if (skb->pkt_type == PACKET_OUTGOING || !skb_mac_header_was_set(skb) ||
     skb_copy_bits(skb, skb_mac_offset(skb), &eh, sizeof(eh))) goto done;
 if (ether_addr_equal(eh.h_source, pc) && ether_addr_equal(eh.h_dest, phone)) dir=0;
 else if (ether_addr_equal(eh.h_source, phone) && ether_addr_equal(eh.h_dest, pc)) dir=1;
 else goto done;
 proto=skb->protocol;off=skb_network_offset(skb);
 while (eth_type_vlan(proto) && depth++ < 2) {
  if (skb_copy_bits(skb, off, &vh, sizeof(vh))) goto done;
  proto=vh.h_vlan_encapsulated_proto;off+=sizeof(vh);
 }
 if (proto!=htons(ETH_P_IP) || skb_copy_bits(skb, off, &ip, sizeof(ip)) ||
     ip.version!=4 || ip.ihl!=5 || ip.protocol!=IPPROTO_UDP ||
     (ntohs(ip.frag_off)&0x3fff) ||
     ip.saddr!=htonl(dir ? 0xc0a80ae0 : 0xc0a80a65) ||
     ip.daddr!=htonl(dir ? 0xc0a80a65 : 0xc0a80ae0)) goto done;
 off+=sizeof(ip);
 if (skb_copy_bits(skb,off,&udp,sizeof(udp)) ||
     skb_copy_bits(skb,off+sizeof(udp),mark,sizeof(mark)) ||
     mark[0]!=htonl(0x58524453)) goto done;
 run=ntohl(mark[1]);phase=ntohl(mark[2]);seq=ntohl(mark[3]);
 if (run<45001 || run>45003) goto done;
 run-=45001;
 if ((run==2)!=dir ||
     udp.source!=htons(run==2 ? 41071 : (run==1 ? 41060 : 41050)) ||
     udp.dest!=htons(run==2 ? 41070 : (run==1 ? 41061 : 41051))) goto done;
 spin_lock_bh(&xr_lock);
 if (phase>=NPHASE || seq>=NSEQ) {malformed++;goto unlock;}
 c=&counts[run][phase];
 if (!c->copies) {c->first_hash=READ_ONCE(skb->hash);c->first_dev=dev->ifindex;}
 c->last_hash=READ_ONCE(skb->hash);c->last_dev=dev->ifindex;c->copies++;
 c->tagged+=!!depth || skb_vlan_tag_present(skb);
 if (!test_and_set_bit(seq,seen[run][phase])) {
  c->unique++;c->ds_bad+=ip.tos!=expected[phase];c->ttl_bad+=ip.ttl!=64;
 }
unlock:spin_unlock_bh(&xr_lock);
done:consume_skb(skb);return NET_RX_SUCCESS;
}
static struct packet_type tap={.type=cpu_to_be16(ETH_P_ALL),.func=xr_receive};
static int xr_show(struct seq_file *s,void *unused)
{
 struct xr_count copy[3][NPHASE];
 u32 bad;unsigned int r,p;
 if (!capable(CAP_NET_ADMIN)) return -EPERM;
 spin_lock_bh(&xr_lock);memcpy(copy,counts,sizeof(copy));bad=malformed;spin_unlock_bh(&xr_lock);
 seq_printf(s,"schema=1 scope=owned_generated_udp cpu_input=1 outgoing=0 payload_saved=0 malformed=%u\n",bad);
 for(r=0;r<3;r++) for(p=0;p<NPHASE;p++) {
  struct xr_count *c=&copy[r][p];
  seq_printf(s,"run=%u phase=%u expected=%u unique=%u copies=%u ds_bad=%u ttl_bad=%u first_hash=%08x last_hash=%08x first_dev=%u last_dev=%u tagged=%u\n",
      45001+r,p,expected[p],c->unique,c->copies,c->ds_bad,c->ttl_bad,
      c->first_hash,c->last_hash,c->first_dev,c->last_dev,c->tagged);
 }
 return 0;
}
DEFINE_SHOW_ATTRIBUTE(xr);
static int __init xr_init(void)
{
 if (!of_machine_is_compatible("gemtek,xr1710g")) return -ENODEV;
 entry=debugfs_create_file("xr_native_cpu",0400,NULL,NULL,&xr_fops);
 if (IS_ERR(entry)) return PTR_ERR(entry);
 dev_add_pack(&tap);return 0;
}
static void __exit xr_exit(void){dev_remove_pack(&tap);debugfs_remove(entry);}
module_init(xr_init);module_exit(xr_exit);MODULE_LICENSE("GPL");
