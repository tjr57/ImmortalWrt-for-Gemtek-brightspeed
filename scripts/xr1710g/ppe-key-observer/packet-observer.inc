/* Read-only packet tap for the owner's exact generated UDP tuple/magic.
 * It consumes only the tap's skb reference, never changes forwarding data.
 * Read skb->hash directly: skb_get_hash() would manufacture a software hash.
 */
#include <linux/jhash.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <linux/if_arp.h>
#include <linux/if_vlan.h>
#include <net/net_namespace.h>

#define XR_PROBE_RUN 43009
struct xr_packet_sample {
    u32 hash, count;
    u16 proto, vlan_tci;
    u8 sw_hash, l4_hash, tos, ttl, vlan_present;
};
static struct xr_packet_sample xr_samples[32];
static unsigned int xr_sample_count, xr_sample_overflow;
static DEFINE_SPINLOCK(xr_sample_lock);
static struct net_device *xr_tap_dev;
static bool xr_tap_registered;

static int xr_packet(struct sk_buff *skb, struct net_device *dev,
                     struct packet_type *pt, struct net_device *orig_dev)
{
    struct xr_packet_sample sample = {};
    struct ethhdr eh;
    struct iphdr iph;
    struct udphdr udp;
    __be32 marker[2];
    u8 arp[28];
    unsigned int i;
    int offset;

    if (skb->pkt_type == PACKET_OUTGOING || !skb_mac_header_was_set(skb) ||
        skb_copy_bits(skb, skb_mac_offset(skb), &eh, sizeof(eh)) ||
        !ether_addr_equal(eh.h_source, wanted_src) ||
        !ether_addr_equal(eh.h_dest, wanted_dst))
        goto done;
    offset = skb_network_offset(skb);
    if (skb->protocol == htons(ETH_P_IP)) {
        if (skb_copy_bits(skb, offset, &iph, sizeof(iph)) ||
            iph.version != 4 || iph.ihl != 5 || iph.protocol != IPPROTO_UDP ||
            (ntohs(iph.frag_off) & 0x3fff) ||
            iph.saddr != htonl(0xc0a80a65) || iph.daddr != htonl(0xc0a80a04))
            goto done;
        if (skb_copy_bits(skb, offset + sizeof(iph), &udp, sizeof(udp)) ||
            udp.source != htons(41081) || udp.dest != htons(41080) ||
            skb_copy_bits(skb, offset + sizeof(iph) + sizeof(udp), marker, sizeof(marker)) ||
            marker[0] != htonl(0x58524453) || marker[1] != htonl(XR_PROBE_RUN))
            goto done;
        sample.tos = iph.tos;
        sample.ttl = iph.ttl;
    } else if (skb->protocol == htons(ETH_P_ARP)) {
        if (skb_copy_bits(skb, offset, arp, sizeof(arp)) ||
            memcmp(arp, "\x00\x01\x08\x00\x06\x04\x00\x02", 8) ||
            memcmp(arp + 14, "\xc0\xa8\x0a\x65", 4) ||
            memcmp(arp + 24, "\xc0\xa8\x0a\x04", 4))
            goto done;
    } else {
        goto done;
    }
    sample.hash = READ_ONCE(skb->hash);
    sample.sw_hash = skb->sw_hash;
    sample.l4_hash = skb->l4_hash;
    sample.proto = ntohs(skb->protocol);
    sample.vlan_present = skb_vlan_tag_present(skb);
    sample.vlan_tci = skb_vlan_tag_get(skb);
    spin_lock_bh(&xr_sample_lock);
    for (i = 0; i < xr_sample_count; i++) {
        struct xr_packet_sample *p = &xr_samples[i];
        if (p->hash == sample.hash && p->sw_hash == sample.sw_hash &&
            p->l4_hash == sample.l4_hash && p->proto == sample.proto &&
            p->tos == sample.tos && p->ttl == sample.ttl &&
            p->vlan_present == sample.vlan_present && p->vlan_tci == sample.vlan_tci)
            break;
    }
    if (i == xr_sample_count && i < ARRAY_SIZE(xr_samples))
        xr_samples[xr_sample_count++] = sample;
    if (i < ARRAY_SIZE(xr_samples))
        xr_samples[i].count++;
    else
        xr_sample_overflow++;
    spin_unlock_bh(&xr_sample_lock);
done:
    consume_skb(skb);
    return NET_RX_SUCCESS;
}
static struct packet_type xr_tap = {
    .type = cpu_to_be16(ETH_P_ALL),
    .func = xr_packet,
};

static int xr_packets_show(struct seq_file *s, void *unused)
{
    struct xr_packet_sample copy[ARRAY_SIZE(xr_samples)];
    unsigned int i, n, overflow;
    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    spin_lock_bh(&xr_sample_lock);
    memcpy(copy, xr_samples, sizeof(copy));
    n = xr_sample_count;
    overflow = xr_sample_overflow;
    spin_unlock_bh(&xr_sample_lock);
    seq_printf(s, "schema=1 run=%u source=raw_skb_hash recompute=0 overflow=%u\n", XR_PROBE_RUN, overflow);
    for (i = 0; i < n; i++) {
        const struct xr_packet_sample *p = &copy[i];
        unsigned int index, matches = 0, last = 0;
        for (index = 0; index < PPE_SRAM_NUM_ENTRIES * 2 + PPE_DRAM_NUM_ENTRIES; index++) {
            if (p->hash && jhash_1word(index, 0) == p->hash) {
                matches++;
                last = index;
            }
        }
        seq_printf(s, "proto=0x%04x count=%u hash=0x%08x sw=%u l4=%u tos=%u ttl=%u vlan_present=%u vlan_tci=%u ppe_index_matches=%u ppe_index=%u\n",
                   p->proto, p->count, p->hash, p->sw_hash, p->l4_hash, p->tos, p->ttl,
                   p->vlan_present, p->vlan_tci, matches, last);
    }
    return 0;
}
DEFINE_SHOW_ATTRIBUTE(xr_packets);
