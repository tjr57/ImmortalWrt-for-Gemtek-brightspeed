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
#include <linux/ipv6.h>
#include <linux/slab.h>
#include <net/ipv6.h>
#include <net/dsfield.h>
#include <linux/udp.h>
#include <linux/bitmap.h>
#include <linux/of.h>
#include <net/net_namespace.h>

#define NPHASE 12
#define NSEQ 400
static const u8 expected[NPHASE] = {0,184,40,0,1,2,3,0,185,186,187,184};
static const u8 pc[ETH_ALEN] = {0x98,0xb7,0x85,0x1e,0xd5,0xdf};
static const u8 phone[ETH_ALEN] = {0x0c,0xbd,0x75,0x21,0xb0,0xdd};
static const u8 pc6[16]={0xfd,0xdd,0x2e,0x15,0x72,0xb6,0,0,0,0,0,0,0,0,1,0x3f};
static const u8 phone6[16]={0xfd,0xdd,0x2e,0x15,0x72,0xb6,0,0,0xd5,0xa2,0xe0,0x32,0xcd,0x57,0xad,0x72};
struct xr_count {
 u32 copies, unique, ds_bad, ttl_bad, first_hash, last_hash;
 u32 first_dev, last_dev, tagged;
};
static struct xr_count counts[6][NPHASE];
static unsigned long seen[6][NPHASE][BITS_TO_LONGS(NSEQ)];
static u32 malformed;
static DEFINE_SPINLOCK(xr_lock);
static struct dentry *entry;

static int xr_receive(struct sk_buff *skb, struct net_device *dev,
                      struct packet_type *pt, struct net_device *orig_dev)
{
 struct ethhdr eh;
 struct ipv6hdr ip;
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
 if (proto!=htons(ETH_P_IPV6) || skb_copy_bits(skb, off, &ip, sizeof(ip)) ||
     ip.version!=6 || ip.nexthdr!=IPPROTO_UDP ||
     memcmp(ip.saddr.s6_addr, dir ? phone6 : pc6, 16) ||
     memcmp(ip.daddr.s6_addr, dir ? pc6 : phone6, 16)) goto done;
 off+=sizeof(ip);
 if (skb_copy_bits(skb,off,&udp,sizeof(udp)) ||
     skb_copy_bits(skb,off+sizeof(udp),mark,sizeof(mark)) ||
     mark[0]!=htonl(0x58524453)) goto done;
 run=ntohl(mark[1]);phase=ntohl(mark[2]);seq=ntohl(mark[3]);
 if (run<45601 || run>45606) goto done;
 run-=45601;
 if ((run & 1)!=dir ||
     udp.source!=htons(41080 + run*2 + dir) ||
     udp.dest!=htons(41080 + run*2 + !dir)) goto done;
 spin_lock_bh(&xr_lock);
 if (phase>=NPHASE || seq>=NSEQ) {malformed++;goto unlock;}
 c=&counts[run][phase];
 if (!c->copies) {c->first_hash=READ_ONCE(skb->hash);c->first_dev=dev->ifindex;}
 c->last_hash=READ_ONCE(skb->hash);c->last_dev=dev->ifindex;c->copies++;
 c->tagged+=!!depth || skb_vlan_tag_present(skb);
 if (!test_and_set_bit(seq,seen[run][phase])) {
  c->unique++;c->ds_bad+=ipv6_get_dsfield(&ip)!=expected[phase];c->ttl_bad+=ip.hop_limit!=64;
 }
unlock:spin_unlock_bh(&xr_lock);
done:consume_skb(skb);return NET_RX_SUCCESS;
}
static struct packet_type tap={.type=cpu_to_be16(ETH_P_ALL),.func=xr_receive,.af_packet_net=&init_net};
static int xr_show(struct seq_file *s,void *unused)
{
 struct xr_count (*copy)[NPHASE];
 u32 bad;unsigned int r,p;
 if (!capable(CAP_NET_ADMIN)) return -EPERM;
 copy=kmalloc(sizeof(counts),GFP_KERNEL);if (!copy) return -ENOMEM;
 spin_lock_bh(&xr_lock);memcpy(copy,counts,sizeof(counts));bad=malformed;spin_unlock_bh(&xr_lock);
 seq_printf(s,"schema=1 scope=owned_generated_udp cpu_input=1 outgoing=0 payload_saved=0 malformed=%u\n",bad);
 for(r=0;r<6;r++) for(p=0;p<NPHASE;p++) {
  struct xr_count *c=&copy[r][p];
  seq_printf(s,"run=%u phase=%u expected=%u unique=%u copies=%u ds_bad=%u ttl_bad=%u first_hash=%08x last_hash=%08x first_dev=%u last_dev=%u tagged=%u\n",
      45601+r,p,expected[p],c->unique,c->copies,c->ds_bad,c->ttl_bad,
      c->first_hash,c->last_hash,c->first_dev,c->last_dev,c->tagged);
 }
 kfree(copy);return 0;
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

MODULE_DESCRIPTION("Owned XR1710G generated-probe CPU observer; explicit init netns");
