// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (c) 2025 AIROHA Inc
 * Author: Lorenzo Bianconi <lorenzo@kernel.org>
 */

#include <linux/airoha-eth.h>
#include <linux/ip.h>
#include <linux/etherdevice.h>
#include <linux/ipv6.h>
#include <linux/moduleparam.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/rhashtable.h>
#include <net/ipv6.h>
#include <linux/if_bridge.h>
#include <linux/if_vlan.h>
#include <net/pkt_cls.h>
#include <net/route.h>
#include <net/ip.h>
#include <net/switchdev.h>

#include "airoha_regs.h"
#include <linux/netfilter.h>
#include "airoha_eth.h"

/* Serialize airoha_gdm_dev flags, QDMA pointer and PPE CPU port
 * configuration.
 */
DEFINE_MUTEX(flow_offload_mutex);
static DEFINE_SPINLOCK(ppe_lock);

/* Boot-only policy: a live disable would also have to invalidate existing
 * SRAM/DRAM bindings. Do not expose a writable switch that leaves them active.
 * This controls PPE forwarding, not the NPU WLAN DMA/ring transport.
 */
/* Separate explicit opt-in for automatic MAC/FDB bridge cache bindings.
 * Route/TC flow-table eligibility does not prove bridge firewall eligibility.
 */
static bool ppe_bridge_bind_enable;
module_param_named(ppe_bridge_bind_enable, ppe_bridge_bind_enable, bool, 0400);
MODULE_PARM_DESC(ppe_bridge_bind_enable,
		"Allow explicit context-scoped TC bridge templates only; no automatic FDB binding (boot-only)");

static bool ppe_bind_enable = IS_ENABLED(CONFIG_NET_AIROHA_PPE_BIND_DEFAULT);
module_param_named(ppe_bind_enable, ppe_bind_enable, bool, 0400);
MODULE_PARM_DESC(ppe_bind_enable,
                "Allow PPE forwarding bindings (boot-only; NPU WLAN DMA remains available)");

static const struct rhashtable_params airoha_flow_table_params = {
	.head_offset = offsetof(struct airoha_flow_table_entry, node),
	.key_offset = offsetof(struct airoha_flow_table_entry, cookie),
	.key_len = sizeof(unsigned long),
	.automatic_shrinking = true,
};

static const struct rhashtable_params airoha_l2_flow_table_params = {
	.head_offset = offsetof(struct airoha_flow_table_entry, l2_node),
	.key_offset = offsetof(struct airoha_flow_table_entry, l2_key),
	.key_len = sizeof(struct airoha_l2_flow_key),
	.automatic_shrinking = true,
};

static int airoha_ppe_get_num_stats_entries(struct airoha_ppe *ppe)
{
	if (!IS_ENABLED(CONFIG_NET_AIROHA_FLOW_STATS))
		return -EOPNOTSUPP;

	if (airoha_is_7583(ppe->eth))
		return -EOPNOTSUPP;

	return PPE_STATS_NUM_ENTRIES;
}

static int airoha_ppe_get_total_num_stats_entries(struct airoha_ppe *ppe)
{
	int num_stats = airoha_ppe_get_num_stats_entries(ppe);

	if (num_stats > 0) {
		struct airoha_eth *eth = ppe->eth;

		num_stats = num_stats * eth->soc->num_ppe;
	}

	return num_stats;
}

static u32 airoha_ppe_get_total_sram_num_entries(struct airoha_ppe *ppe)
{
	struct airoha_eth *eth = ppe->eth;

	return PPE_SRAM_NUM_ENTRIES * eth->soc->num_ppe;
}

u32 airoha_ppe_get_total_num_entries(struct airoha_ppe *ppe)
{
	u32 sram_num_entries = airoha_ppe_get_total_sram_num_entries(ppe);

	return sram_num_entries + PPE_DRAM_NUM_ENTRIES;
}

bool airoha_ppe_is_enabled(struct airoha_eth *eth, int index)
{
	if (index >= eth->soc->num_ppe)
		return false;

	return airoha_fe_rr(eth, REG_PPE_GLO_CFG(index)) & PPE_GLO_CFG_EN_MASK;
}

static u32 airoha_ppe_get_timestamp(struct airoha_ppe *ppe)
{
	return airoha_fe_get(ppe->eth, REG_FE_FOE_TS,
			     AIROHA_FOE_IB1_BIND_TIMESTAMP);
}

void airoha_ppe_set_cpu_port(struct airoha_gdm_dev *dev, u8 ppe_id, u8 fport)
{
	struct airoha_qdma *qdma = airoha_qdma_deref(dev);
	struct airoha_eth *eth = dev->eth;
	u8 qdma_id = qdma - &eth->qdma[0];
	u32 fe_cpu_port;

	fe_cpu_port = qdma_id ? FE_PSE_PORT_CDM2 : FE_PSE_PORT_CDM1;
	airoha_fe_rmw(eth, REG_PPE_DFT_CPORT(ppe_id, fport),
		      DFT_CPORT_MASK(fport),
		      __field_prep(DFT_CPORT_MASK(fport), fe_cpu_port));
}

void airoha_ppe_set_mtu(struct airoha_gdm_dev *dev)
{
	struct airoha_gdm_port *port = dev->port;
	struct airoha_eth *eth = dev->eth;
	struct airoha_qdma *qdma;
	int i, ppe_id, index;
	u32 len = 0;

	qdma = airoha_qdma_deref(dev);
	for (i = 0; i < ARRAY_SIZE(port->devs); i++) {
		struct airoha_gdm_dev *d = port->devs[i];
		struct net_device *netdev;
		struct airoha_qdma *q;

		if (!d)
			continue;

		q = airoha_qdma_deref(d);
		if (q != qdma)
			continue;

		netdev = netdev_from_priv(d);
		if (netif_running(netdev))
			len = max_t(u32, len, netdev->mtu);
	}

	len += VLAN_ETH_HLEN;
	ppe_id = !airoha_is_lan_gdm_dev(dev) && airoha_ppe_is_enabled(eth, 1);
	index = port->id == AIROHA_GDM4_IDX ? 7 : port->id;
	airoha_fe_rmw(eth, REG_PPE_MTU(ppe_id, index),
		      FP_EGRESS_MTU_MASK(index),
		      __field_prep(FP_EGRESS_MTU_MASK(index), len));
}

static void airoha_ppe_hw_init(struct airoha_ppe *ppe)
{
	u32 sram_ppe_num_data_entries = PPE_SRAM_NUM_ENTRIES, sram_num_entries;
	u32 sram_tb_size, dram_num_entries;
	struct airoha_eth *eth = ppe->eth;
	int i, sram_num_stats_entries;

	sram_num_entries = airoha_ppe_get_total_sram_num_entries(ppe);
	sram_tb_size = sram_num_entries * sizeof(struct airoha_foe_entry);
	dram_num_entries = PPE_RAM_NUM_ENTRIES_SHIFT(PPE_DRAM_NUM_ENTRIES);

	sram_num_stats_entries = airoha_ppe_get_num_stats_entries(ppe);
	if (sram_num_stats_entries > 0)
		sram_ppe_num_data_entries -= sram_num_stats_entries;
	sram_ppe_num_data_entries =
		PPE_RAM_NUM_ENTRIES_SHIFT(sram_ppe_num_data_entries);

	for (i = 0; i < eth->soc->num_ppe; i++) {
		airoha_fe_wr(eth, REG_PPE_TB_BASE(i),
			     ppe->foe_dma + sram_tb_size);

		airoha_fe_rmw(eth, REG_PPE_BND_AGE0(i),
			      PPE_BIND_AGE0_DELTA_NON_L4 |
			      PPE_BIND_AGE0_DELTA_UDP,
			      FIELD_PREP(PPE_BIND_AGE0_DELTA_NON_L4, 60) |
			      FIELD_PREP(PPE_BIND_AGE0_DELTA_UDP, 60));
		airoha_fe_rmw(eth, REG_PPE_BND_AGE1(i),
			      PPE_BIND_AGE1_DELTA_TCP_FIN |
			      PPE_BIND_AGE1_DELTA_TCP,
			      FIELD_PREP(PPE_BIND_AGE1_DELTA_TCP_FIN, 1) |
			      FIELD_PREP(PPE_BIND_AGE1_DELTA_TCP, 60));

		airoha_fe_rmw(eth, REG_PPE_TB_HASH_CFG(i),
			      PPE_SRAM_TABLE_EN_MASK |
			      PPE_SRAM_HASH1_EN_MASK |
			      PPE_DRAM_TABLE_EN_MASK |
			      PPE_SRAM_HASH0_MODE_MASK |
			      PPE_SRAM_HASH1_MODE_MASK |
			      PPE_DRAM_HASH0_MODE_MASK |
			      PPE_DRAM_HASH1_MODE_MASK,
			      FIELD_PREP(PPE_SRAM_TABLE_EN_MASK, 1) |
			      FIELD_PREP(PPE_SRAM_HASH1_EN_MASK, 1) |
			      FIELD_PREP(PPE_SRAM_HASH1_MODE_MASK, 1) |
			      FIELD_PREP(PPE_DRAM_HASH1_MODE_MASK, 3));

		airoha_fe_rmw(eth, REG_PPE_TB_CFG(i),
			      PPE_TB_CFG_SEARCH_MISS_MASK |
			      PPE_SRAM_TB_NUM_ENTRY_MASK |
			      PPE_DRAM_TB_NUM_ENTRY_MASK |
			      PPE_TB_CFG_KEEPALIVE_MASK |
			      PPE_TB_ENTRY_SIZE_MASK,
			      FIELD_PREP(PPE_TB_CFG_SEARCH_MISS_MASK, 3) |
			      FIELD_PREP(PPE_TB_ENTRY_SIZE_MASK, 0) |
			      FIELD_PREP(PPE_SRAM_TB_NUM_ENTRY_MASK,
					 sram_ppe_num_data_entries) |
			      FIELD_PREP(PPE_DRAM_TB_NUM_ENTRY_MASK,
					 dram_num_entries));

		airoha_fe_rmw(eth, REG_PPE_BIND_RATE(i),
			      PPE_BIND_RATE_L2B_BIND_MASK |
			      PPE_BIND_RATE_BIND_MASK,
			      FIELD_PREP(PPE_BIND_RATE_L2B_BIND_MASK, 0x1e) |
			      FIELD_PREP(PPE_BIND_RATE_BIND_MASK, 0x1e));

		airoha_fe_wr(eth, REG_PPE_HASH_SEED(i), PPE_HASH_SEED);
		airoha_fe_clear(eth, REG_PPE_PPE_FLOW_CFG(i),
				PPE_FLOW_CFG_IP6_6RD_MASK);
	}

	for (i = 0; i < ARRAY_SIZE(eth->ports); i++) {
		struct airoha_gdm_port *port = eth->ports[i];
		int j;

		if (!port)
			continue;

		for (j = 0; j < ARRAY_SIZE(port->devs); j++) {
			struct airoha_gdm_dev *dev = port->devs[j];
			int ppe_id;
			u8 fport;

			if (!dev)
				continue;

			ppe_id = !airoha_is_lan_gdm_dev(dev) &&
				 airoha_ppe_is_enabled(eth, 1);
			fport = airoha_get_fe_port(dev);
			airoha_ppe_set_cpu_port(dev, ppe_id, fport);
			airoha_ppe_set_mtu(dev);
		}
	}
}

static void airoha_ppe_flow_mangle_eth(const struct flow_action_entry *act, void *eth)
{
	void *dest = eth + act->mangle.offset;
	const void *src = &act->mangle.val;

	if (act->mangle.offset > 8)
		return;

	if (act->mangle.mask == 0xffff) {
		src += 2;
		dest += 2;
	}

	memcpy(dest, src, act->mangle.mask ? 2 : 4);
}

static int airoha_ppe_flow_mangle_ports(const struct flow_action_entry *act,
					struct airoha_flow_data *data)
{
	u32 val = be32_to_cpu((__force __be32)act->mangle.val);

	switch (act->mangle.offset) {
	case 0:
		if ((__force __be32)act->mangle.mask == ~cpu_to_be32(0xffff))
			data->dst_port = cpu_to_be16(val);
		else
			data->src_port = cpu_to_be16(val >> 16);
		break;
	case 2:
		data->dst_port = cpu_to_be16(val);
		break;
	default:
		return -EINVAL;
	}

	return 0;
}

static int airoha_ppe_flow_mangle_ipv4(const struct flow_action_entry *act,
				       struct airoha_flow_data *data)
{
	__be32 *dest;

	switch (act->mangle.offset) {
	case offsetof(struct iphdr, saddr):
		dest = &data->v4.src_addr;
		break;
	case offsetof(struct iphdr, daddr):
		dest = &data->v4.dst_addr;
		break;
	default:
		return -EINVAL;
	}

	memcpy(dest, &act->mangle.val, sizeof(u32));

	return 0;
}

static int airoha_ppe_get_wdma_info(struct net_device *dev, const u8 *addr,
				    struct airoha_wdma_info *info)
{
	struct net_device_path_stack stack;
	struct net_device_path *path;
	int err;

	if (!dev)
		return -ENODEV;

	rcu_read_lock();
	err = dev_fill_forward_path(dev, addr, &stack);
	rcu_read_unlock();
	if (err)
		return err;

	path = &stack.path[stack.num_paths - 1];
	if (path->type != DEV_PATH_MTK_WDMA)
		return -EINVAL;

	info->idx = path->mtk_wdma.wdma_idx;
	info->bss = path->mtk_wdma.bss;
	info->wcid = path->mtk_wdma.wcid;

	return 0;
}

static int airoha_get_dsa_port(struct net_device **dev)
{
#if IS_ENABLED(CONFIG_NET_DSA)
	struct dsa_port *dp = dsa_port_from_netdev(*dev);

	if (IS_ERR(dp))
		return -ENODEV;

	*dev = dsa_port_to_conduit(dp);
	return dp->index;
#else
	return -ENODEV;
#endif
}

static void airoha_ppe_foe_set_bridge_addrs(struct airoha_foe_bridge *br,
					    struct ethhdr *eh)
{
	br->dest_mac_hi = get_unaligned_be32(eh->h_dest);
	br->dest_mac_lo = get_unaligned_be16(eh->h_dest + 4);
	br->src_mac_hi = get_unaligned_be16(eh->h_source);
	br->src_mac_lo = get_unaligned_be32(eh->h_source + 2);
}

static u32
airoha_ppe_pon_lookup_tag(const struct airoha_pon_flow_table *table,
			  u16 vlan_id, u8 pbit)
{
	const struct airoha_pon_flow_entry *fallback = NULL;
	unsigned int i;

	for (i = 0; i < table->count; i++) {
		const struct airoha_pon_flow_entry *entry = &table->entries[i];

		if (!(entry->pbit_mask & BIT(pbit)))
			continue;
		if (entry->vlan_id == vlan_id)
			return entry->tag;
		if (entry->vlan_id == AIROHA_PON_VID_ANY && !fallback)
			fallback = entry;
	}

	return fallback ? fallback->tag : 0;
}

static int airoha_ppe_pon_select_flow(struct airoha_gdm_dev *dev,
				      const struct airoha_flow_data *data,
				      u32 *pon_tag)
{
	const struct airoha_pon_flow_table *table;
	u32 tag, first_tag = 0;
	u16 vlan_id;
	u8 pbit;

	lockdep_assert_held(&flow_offload_mutex);

	/* EPON uses the fixed LLID channel configured by the line controller. */
	tag = READ_ONCE(dev->pon_qdma_tag);
	if (tag & AIROHA_PON_QDMA_VALID) {
		*pon_tag = tag;
		return 0;
	}

	table = rcu_dereference_protected(dev->pon_flow_table,
					  lockdep_is_held(&flow_offload_mutex));
	if (!table)
		return -EOPNOTSUPP;

	/* nf_flow_table orders VLAN_PUSH from upper devices toward hardware.
	 * The final VLAN is the outer service tag seen by pon0; untagged packets
	 * use VID_ANY and P-bit 0, matching ndo_start_xmit classification.
	 */
	vlan_id = data->vlan.num ?
		data->vlan.hdr[data->vlan.num - 1].id : AIROHA_PON_VID_ANY;
	if (!data->vlan.num) {
		tag = airoha_ppe_pon_lookup_tag(table, vlan_id, 0);
		if (!(tag & AIROHA_PON_QDMA_VALID))
			return -EOPNOTSUPP;
		*pon_tag = tag;
		return 0;
	}

	/* nf_flow_table VLAN actions provide VID while dynamic PCP remains in skb.
	 * Offload is valid when all eight P-bits resolve to one GEM/T-CONT;
	 * split mappings retain per-packet classification on the software path.
	 */
	for (pbit = 0; pbit < 8; pbit++) {
		tag = airoha_ppe_pon_lookup_tag(table, vlan_id, pbit);
		if (!(tag & AIROHA_PON_QDMA_VALID))
			return -EOPNOTSUPP;
		tag &= AIROHA_PON_QDMA_VALID | AIROHA_PON_QDMA_EPON |
		       AIROHA_PON_QDMA_TCONT_MASK | AIROHA_PON_QDMA_GEM_MASK;
		if (!pbit)
			first_tag = tag;
		else if (tag != first_tag)
			return -EOPNOTSUPP;
	}

	*pon_tag = first_tag;
	return 0;
}

static int airoha_ppe_foe_entry_prepare(struct airoha_eth *eth,
					struct airoha_foe_entry *hwe,
					struct net_device *netdev, int type,
					struct airoha_flow_data *data,
					int l4proto, u8 dsfield,
					struct airoha_gdm_dev **egress_dev)
{
	u32 qdata = FIELD_PREP(AIROHA_FOE_SHAPER_ID, 0x7f), ports_pad, val;
	u32 pon_tag = 0;
	int wlan_etype = -EINVAL, dsa_port;
	struct airoha_foe_mac_info_common *l2;
	u8 smac_id = 0xf;

	*egress_dev = NULL;
	if (!netdev)
		return -EOPNOTSUPP;
	dsa_port = airoha_get_dsa_port(&netdev);
	memset(hwe, 0, sizeof(*hwe));

	val = FIELD_PREP(AIROHA_FOE_IB1_BIND_STATE, AIROHA_FOE_STATE_BIND) |
	      FIELD_PREP(AIROHA_FOE_IB1_BIND_PACKET_TYPE, type) |
	      FIELD_PREP(AIROHA_FOE_IB1_BIND_UDP, l4proto == IPPROTO_UDP) |
	      FIELD_PREP(AIROHA_FOE_IB1_BIND_VLAN_LAYER, data->vlan.num) |
	      FIELD_PREP(AIROHA_FOE_IB1_BIND_VPM, data->vlan.num) |
	      FIELD_PREP(AIROHA_FOE_IB1_BIND_PPPOE, data->pppoe.num) |
	      AIROHA_FOE_IB1_BIND_TTL;
	hwe->ib1 = val;

	val = FIELD_PREP(AIROHA_FOE_IB2_PORT_AG, 0x1f);
	if (netdev) {
		struct airoha_wdma_info info = {};

		if (!airoha_ppe_get_wdma_info(netdev, data->eth.h_dest,
					      &info)) {
			val |= FIELD_PREP(AIROHA_FOE_IB2_NBQ, info.idx) |
			       FIELD_PREP(AIROHA_FOE_IB2_PSE_PORT,
					  FE_PSE_PORT_CDM4);
			qdata |= FIELD_PREP(AIROHA_FOE_ACTDP, info.bss);
			wlan_etype = FIELD_PREP(AIROHA_FOE_MAC_WDMA_BAND,
						info.idx) |
				     FIELD_PREP(AIROHA_FOE_MAC_WDMA_WCID,
						info.wcid);
		} else {
			struct airoha_gdm_dev *dev = netdev_priv(netdev);
			struct airoha_gdm_port *port;
			int err;
			u8 pse_port, channel, priority;

			if (!airoha_is_valid_gdm_dev(eth, dev))
				return -EINVAL;
			*egress_dev = dev;

			port = dev->port;
			if (dsa_port >= 0 || airoha_is_lan_gdm_dev(dev))
				pse_port = port->id == 4 ? FE_PSE_PORT_GDM4
							 : port->id;
			else
				pse_port = 2; /* uplink relies on GDM2
					       * loopback
					       */

			/* For traffic forwarded to DSA devices select QoS
			 * channel according to the DSA user port index, rely
			 * on port id otherwise.
			 */
			if (dev->flags & AIROHA_PRIV_F_PON) {
				err = airoha_ppe_pon_select_flow(dev, data,
								 &pon_tag);
				if (err)
					return err;
				channel = FIELD_GET(AIROHA_PON_QDMA_TCONT_MASK,
						    pon_tag);
			} else {
				channel = dsa_port >= 0 ? dsa_port : port->id;
				channel %= AIROHA_NUM_QOS_CHANNELS;
			}
			priority = rt_tos2priority(dsfield);
			priority = priority % AIROHA_NUM_QOS_QUEUES;
			qdata |= FIELD_PREP(AIROHA_FOE_CHANNEL, channel) |
				 FIELD_PREP(AIROHA_FOE_QID, priority);

			val |= FIELD_PREP(AIROHA_FOE_IB2_PSE_PORT, pse_port) |
			       FIELD_PREP(AIROHA_FOE_IB2_DSCP, dsfield) |
			       AIROHA_FOE_IB2_PSE_QOS;
			/* For downlink traffic consume SRAM memory for hw
			 * forwarding descriptors queue.
			 */
			if (airoha_is_lan_gdm_dev(dev))
				val |= AIROHA_FOE_IB2_FAST_PATH;
			/* GDM3/GDM4 select their external SerDes through NBQ. */
			if (pse_port == FE_PSE_PORT_GDM3 ||
			    pse_port == FE_PSE_PORT_GDM4)
				val |= FIELD_PREP(AIROHA_FOE_IB2_NBQ, dev->nbq);
			if (dsa_port >= 0)
				val |= FIELD_PREP(AIROHA_FOE_IB2_NBQ,
						  dsa_port);
			else if (pon_tag & AIROHA_PON_QDMA_VALID)
				/* PON NBOQ and QDMA CHAN both carry T-CONT or LLID. */
				val |= FIELD_PREP(AIROHA_FOE_IB2_NBQ, channel);

			smac_id = port->id;
		}
	}

	if (is_multicast_ether_addr(data->eth.h_dest))
		val |= AIROHA_FOE_IB2_MULTICAST;

	ports_pad = 0xa5a5a500 | (l4proto & 0xff);
	if (type == PPE_PKT_TYPE_IPV4_ROUTE)
		hwe->ipv4.orig_tuple.ports = ports_pad;
	if (type == PPE_PKT_TYPE_IPV6_ROUTE_3T)
		hwe->ipv6.ports = ports_pad;

	if (type == PPE_PKT_TYPE_BRIDGE) {
		airoha_ppe_foe_set_bridge_addrs(&hwe->bridge, &data->eth);
		hwe->bridge.data = qdata;
		hwe->bridge.ib2 = val;
		l2 = &hwe->bridge.l2.common;
	} else if (type >= PPE_PKT_TYPE_IPV6_ROUTE_3T) {
		hwe->ipv6.data = qdata;
		hwe->ipv6.ib2 = val;
		l2 = &hwe->ipv6.l2;
		l2->etype = ETH_P_IPV6;
	} else {
		hwe->ipv4.data = qdata;
		hwe->ipv4.ib2 = val;
		l2 = &hwe->ipv4.l2.common;
		l2->etype = ETH_P_IP;
	}

	l2->dest_mac_hi = get_unaligned_be32(data->eth.h_dest);
	l2->dest_mac_lo = get_unaligned_be16(data->eth.h_dest + 4);
	if (type <= PPE_PKT_TYPE_IPV4_DSLITE) {
		struct airoha_foe_mac_info *mac_info;

		l2->src_mac_hi = get_unaligned_be32(data->eth.h_source);
		hwe->ipv4.l2.src_mac_lo =
			get_unaligned_be16(data->eth.h_source + 4);

		mac_info = (struct airoha_foe_mac_info *)l2;
		mac_info->pppoe_id = data->pppoe.sid;
	} else {
		l2->src_mac_hi = FIELD_PREP(AIROHA_FOE_MAC_SMAC_ID, smac_id) |
				 FIELD_PREP(AIROHA_FOE_MAC_PPPOE_ID,
					    data->pppoe.sid);
	}

	if (data->vlan.num) {
		l2->vlan1 = data->vlan.hdr[0].id;
		if (data->vlan.num == 2)
			l2->vlan2 = data->vlan.hdr[1].id;
	}

	if (wlan_etype >= 0) {
		l2->etype = wlan_etype;
	} else if (dsa_port >= 0) {
		l2->etype = BIT(dsa_port);
		l2->etype |= !data->vlan.num ? BIT(15) : 0;
	} else if (pon_tag & AIROHA_PON_QDMA_VALID) {
		/* PON MAC interprets FOE etype as GPON GEM Port-ID. EPON selects LLID
		 * through channel and leaves special tag zero. IB1_PPPOE and pppoe_id
		 * carry PPPoE type and session metadata.
		 */
		l2->etype = pon_tag & AIROHA_PON_QDMA_EPON ? 0 :
			FIELD_GET(AIROHA_PON_QDMA_GEM_MASK, pon_tag);
	} else if (data->pppoe.num) {
		l2->etype = ETH_P_PPP_SES;
	}

	return 0;
}

static int airoha_ppe_foe_entry_set_ipv4_tuple(struct airoha_foe_entry *hwe,
					       struct airoha_flow_data *data,
					       bool egress)
{
	int type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe->ib1);
	struct airoha_foe_ipv4_tuple *t;

	switch (type) {
	case PPE_PKT_TYPE_IPV4_HNAPT:
		if (egress) {
			t = &hwe->ipv4.new_tuple;
			break;
		}
		fallthrough;
	case PPE_PKT_TYPE_IPV4_DSLITE:
	case PPE_PKT_TYPE_IPV4_ROUTE:
		t = &hwe->ipv4.orig_tuple;
		break;
	default:
		WARN_ON_ONCE(1);
		return -EINVAL;
	}

	t->src_ip = be32_to_cpu(data->v4.src_addr);
	t->dest_ip = be32_to_cpu(data->v4.dst_addr);

	if (type != PPE_PKT_TYPE_IPV4_ROUTE) {
		t->src_port = be16_to_cpu(data->src_port);
		t->dest_port = be16_to_cpu(data->dst_port);
	}

	return 0;
}

static int airoha_ppe_foe_entry_set_ipv6_tuple(struct airoha_foe_entry *hwe,
					       struct airoha_flow_data *data)

{
	int type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe->ib1);
	u32 *src, *dest;

	switch (type) {
	case PPE_PKT_TYPE_IPV6_ROUTE_5T:
	case PPE_PKT_TYPE_IPV6_6RD:
		hwe->ipv6.src_port = be16_to_cpu(data->src_port);
		hwe->ipv6.dest_port = be16_to_cpu(data->dst_port);
		fallthrough;
	case PPE_PKT_TYPE_IPV6_ROUTE_3T:
		src = hwe->ipv6.src_ip;
		dest = hwe->ipv6.dest_ip;
		break;
	default:
		WARN_ON_ONCE(1);
		return -EINVAL;
	}

	ipv6_addr_be32_to_cpu(src, data->v6.src_addr.s6_addr32);
	ipv6_addr_be32_to_cpu(dest, data->v6.dst_addr.s6_addr32);

	return 0;
}

static u32 airoha_ppe_foe_get_entry_hash(struct airoha_ppe *ppe,
					 struct airoha_foe_entry *hwe)
{
	int type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe->ib1);
	u32 ppe_hash_mask = airoha_ppe_get_total_num_entries(ppe) - 1;
	u32 hash, hv1, hv2, hv3;

	switch (type) {
	case PPE_PKT_TYPE_IPV4_ROUTE:
	case PPE_PKT_TYPE_IPV4_HNAPT:
		hv1 = hwe->ipv4.orig_tuple.ports;
		hv2 = hwe->ipv4.orig_tuple.dest_ip;
		hv3 = hwe->ipv4.orig_tuple.src_ip;
		break;
	case PPE_PKT_TYPE_IPV6_ROUTE_3T:
	case PPE_PKT_TYPE_IPV6_ROUTE_5T:
		hv1 = hwe->ipv6.src_ip[3] ^ hwe->ipv6.dest_ip[3];
		hv1 ^= hwe->ipv6.ports;

		hv2 = hwe->ipv6.src_ip[2] ^ hwe->ipv6.dest_ip[2];
		hv2 ^= hwe->ipv6.dest_ip[0];

		hv3 = hwe->ipv6.src_ip[1] ^ hwe->ipv6.dest_ip[1];
		hv3 ^= hwe->ipv6.src_ip[0];
		break;
	case PPE_PKT_TYPE_BRIDGE: {
		struct airoha_foe_mac_info *l2 = &hwe->bridge.l2;

		hv1 = l2->common.src_mac_hi & 0xffff;
		hv1 = hv1 << 16 | l2->src_mac_lo;

		hv2 = l2->common.dest_mac_lo;
		hv2 = hv2 << 16;
		hv2 = hv2 | ((l2->common.src_mac_hi & 0xffff0000) >> 16);

		hv3 = l2->common.dest_mac_hi;
		break;
	}
	case PPE_PKT_TYPE_IPV4_DSLITE:
	case PPE_PKT_TYPE_IPV6_6RD:
	default:
		WARN_ON_ONCE(1);
		return ppe_hash_mask;
	}

	hash = (hv1 & hv2) | ((~hv1) & hv3);
	hash = (hash >> 24) | ((hash & 0xffffff) << 8);
	hash ^= hv1 ^ hv2 ^ hv3;
	hash ^= hash >> 16;
	hash &= ppe_hash_mask;

	return hash;
}

static int airoha_ppe_foe_get_flow_stats_index(struct airoha_ppe *ppe,
					       u32 hash, u32 *index)
{
	int ppe_num_stats_entries;

	ppe_num_stats_entries = airoha_ppe_get_total_num_stats_entries(ppe);
	if (ppe_num_stats_entries < 0)
		return ppe_num_stats_entries;

	*index = hash >= ppe_num_stats_entries ? hash - PPE_STATS_NUM_ENTRIES
					       : hash;

	return 0;
}

static void airoha_ppe_foe_flow_stat_entry_reset(struct airoha_ppe *ppe,
						 struct airoha_npu *npu,
						 int index)
{
	memset_io(&npu->stats[index], 0, sizeof(*npu->stats));
	memset(&ppe->foe_stats[index], 0, sizeof(*ppe->foe_stats));
}

static void airoha_ppe_foe_flow_stats_reset(struct airoha_ppe *ppe,
					    struct airoha_npu *npu)
{
	int i, ppe_num_stats_entries;

	ppe_num_stats_entries = airoha_ppe_get_total_num_stats_entries(ppe);
	if (ppe_num_stats_entries < 0)
		return;

	for (i = 0; i < ppe_num_stats_entries; i++)
		airoha_ppe_foe_flow_stat_entry_reset(ppe, npu, i);
}

static void airoha_ppe_foe_flow_stats_update(struct airoha_ppe *ppe,
					     struct airoha_npu *npu,
					     struct airoha_foe_entry *hwe,
					     u32 hash)
{
	int type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe->ib1);
	u32 index, pse_port, val, *data, *ib2, *meter;
	int ppe_num_stats_entries;
	u8 nbq;

	/* No verified NPU counter layout for native AN7581 L2B entries. */
	if (airoha_is_7581(ppe->eth) && type == PPE_PKT_TYPE_BRIDGE)
		return;

	ppe_num_stats_entries = airoha_ppe_get_total_num_stats_entries(ppe);
	if (ppe_num_stats_entries < 0)
		return;

	if (airoha_ppe_foe_get_flow_stats_index(ppe, hash, &index))
		return;

	if (index >= ppe_num_stats_entries)
		return;

	if (type == PPE_PKT_TYPE_BRIDGE) {
		data = &hwe->bridge.data;
		ib2 = &hwe->bridge.ib2;
		meter = &hwe->bridge.l2.meter;
	} else if (type >= PPE_PKT_TYPE_IPV6_ROUTE_3T) {
		data = &hwe->ipv6.data;
		ib2 = &hwe->ipv6.ib2;
		meter = &hwe->ipv6.meter;
	} else {
		data = &hwe->ipv4.data;
		ib2 = &hwe->ipv4.ib2;
		meter = &hwe->ipv4.l2.meter;
	}

	pse_port = FIELD_GET(AIROHA_FOE_IB2_PSE_PORT, *ib2);
	if (pse_port == FE_PSE_PORT_CDM4)
		return;

	airoha_ppe_foe_flow_stat_entry_reset(ppe, npu, index);

	val = FIELD_GET(AIROHA_FOE_CHANNEL | AIROHA_FOE_QID, *data);
	*data = (*data & ~AIROHA_FOE_ACTDP) |
		FIELD_PREP(AIROHA_FOE_ACTDP, val);

	val = *ib2 & (AIROHA_FOE_IB2_NBQ | AIROHA_FOE_IB2_PSE_PORT |
		      AIROHA_FOE_IB2_PSE_QOS | AIROHA_FOE_IB2_FAST_PATH);
	*meter |= FIELD_PREP(AIROHA_FOE_TUNNEL_MTU, val);

	nbq = pse_port == 1 ? 6 : 5;
	*ib2 &= ~(AIROHA_FOE_IB2_NBQ | AIROHA_FOE_IB2_PSE_PORT |
		  AIROHA_FOE_IB2_PSE_QOS);
	*ib2 |= FIELD_PREP(AIROHA_FOE_IB2_PSE_PORT, 6) |
		FIELD_PREP(AIROHA_FOE_IB2_NBQ, nbq);
}

static struct airoha_foe_entry *
airoha_ppe_foe_get_entry_locked(struct airoha_ppe *ppe, u32 hash)
{
	u32 sram_num_entries = airoha_ppe_get_total_sram_num_entries(ppe);

	lockdep_assert_held(&ppe_lock);

	if (hash < sram_num_entries) {
		u32 *hwe = ppe->foe + hash * sizeof(struct airoha_foe_entry);
		bool ppe2 = hash >= PPE_SRAM_NUM_ENTRIES;
		struct airoha_eth *eth = ppe->eth;
		u32 val;
		int i;

		airoha_fe_wr(ppe->eth, REG_PPE_RAM_CTRL(ppe2),
			     FIELD_PREP(PPE_SRAM_CTRL_ENTRY_MASK, hash) |
			     PPE_SRAM_CTRL_REQ_MASK);
		if (read_poll_timeout_atomic(airoha_fe_rr, val,
					     val & PPE_SRAM_CTRL_ACK_MASK,
					     10, 100, false, eth,
					     REG_PPE_RAM_CTRL(ppe2)))
			return NULL;

		for (i = 0; i < sizeof(struct airoha_foe_entry) / sizeof(*hwe);
		     i++)
			hwe[i] = airoha_fe_rr(eth,
					      REG_PPE_RAM_ENTRY(ppe2, i));
	}

	return ppe->foe + hash * sizeof(struct airoha_foe_entry);
}

struct airoha_foe_entry *airoha_ppe_foe_get_entry(struct airoha_ppe *ppe,
						  u32 hash)
{
	struct airoha_foe_entry *hwe;

	spin_lock_bh(&ppe_lock);
	hwe = airoha_ppe_foe_get_entry_locked(ppe, hash);
	spin_unlock_bh(&ppe_lock);

	return hwe;
}

static bool airoha_ppe_foe_compare_entry(struct airoha_flow_table_entry *e,
					 struct airoha_foe_entry *hwe)
{
	int type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, e->data.ib1);
	int len;

	if ((hwe->ib1 ^ e->data.ib1) & AIROHA_FOE_IB1_BIND_UDP)
		return false;

	if (type > PPE_PKT_TYPE_IPV4_DSLITE)
		len = offsetof(struct airoha_foe_entry, ipv6.data);
	else
		len = offsetof(struct airoha_foe_entry, ipv4.ib2);

	return !memcmp(&e->data.d, &hwe->d, len - sizeof(hwe->ib1));
}

static int airoha_ppe_foe_commit_sram_entry(struct airoha_ppe *ppe, u32 hash)
{
	struct airoha_foe_entry *hwe = ppe->foe + hash * sizeof(*hwe);
	bool ppe2 = hash >= PPE_SRAM_NUM_ENTRIES;
	u32 *ptr = (u32 *)hwe, val;
	int i;

	for (i = 0; i < sizeof(*hwe) / sizeof(*ptr); i++)
		airoha_fe_wr(ppe->eth, REG_PPE_RAM_ENTRY(ppe2, i), ptr[i]);

	wmb();
	airoha_fe_wr(ppe->eth, REG_PPE_RAM_CTRL(ppe2),
		     FIELD_PREP(PPE_SRAM_CTRL_ENTRY_MASK, hash) |
		     PPE_SRAM_CTRL_WR_MASK | PPE_SRAM_CTRL_REQ_MASK);

	return read_poll_timeout_atomic(airoha_fe_rr, val,
					val & PPE_SRAM_CTRL_ACK_MASK,
					10, 100, false, ppe->eth,
					REG_PPE_RAM_CTRL(ppe2));
}

static int airoha_ppe_foe_commit_entry(struct airoha_ppe *ppe,
				       struct airoha_foe_entry *e,
				       u32 hash, bool rx_wlan)
{
	u32 sram_num_entries = airoha_ppe_get_total_sram_num_entries(ppe);
	struct airoha_foe_entry *hwe = ppe->foe + hash * sizeof(*hwe);
	u32 ts = airoha_ppe_get_timestamp(ppe);
	struct airoha_eth *eth = ppe->eth;
	struct airoha_npu *npu;
	int err = 0;

	/* Final guard covers every bind caller, including direct bridge fallback.
	 * INVALID/unbind writes must remain available for teardown.
	 */
	if (!ppe_bind_enable &&
	    FIELD_GET(AIROHA_FOE_IB1_BIND_STATE, e->ib1) == AIROHA_FOE_STATE_BIND)
		return -EOPNOTSUPP;

	if (airoha_is_7581(eth) &&
	    FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe->ib1) ==
	    PPE_PKT_TYPE_BRIDGE &&
	    FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, e->ib1) ==
	    PPE_PKT_TYPE_BRIDGE) {
		struct airoha_foe_l2b native_l2 = hwe->l2b;

		memcpy(&hwe->d, &e->d, sizeof(*hwe) - sizeof(hwe->ib1));
		/* The generic copy uses the software bridge layout. Restore the
		 * native learned key, while keeping the new forwarding fields. */
		memcpy(&hwe->l2b, &native_l2,
		       offsetof(struct airoha_foe_l2b, data));
	} else {
		memcpy(&hwe->d, &e->d, sizeof(*hwe) - sizeof(hwe->ib1));
	}
	wmb();

	e->ib1 &= ~AIROHA_FOE_IB1_BIND_TIMESTAMP;
	e->ib1 |= FIELD_PREP(AIROHA_FOE_IB1_BIND_TIMESTAMP, ts);
	hwe->ib1 = e->ib1;

	rcu_read_lock();

	npu = rcu_dereference(eth->npu);
	if (!npu) {
		err = -ENODEV;
		goto unlock;
	}

	if (!rx_wlan)
		airoha_ppe_foe_flow_stats_update(ppe, npu, hwe, hash);

	if (hash < sram_num_entries)
		err = airoha_ppe_foe_commit_sram_entry(ppe, hash);
unlock:
	rcu_read_unlock();

	return err;
}

#ifdef CONFIG_AIROHA_PON_COMPAT
#include <linux/airoha_ppe_compat.h>
extern struct airoha_eth *airoha_pon_compat_get_eth(void);

static struct airoha_ppe *airoha_ppe_mc_instance(void)
{
	struct airoha_eth *eth = airoha_pon_compat_get_eth();

	return eth ? READ_ONCE(eth->ppe) : NULL;
}

static void airoha_ppe_mc_group_mac(const struct airoha_ppe_mc_info *info,
					    u8 *mac)
{
	memset(mac, 0, ETH_ALEN);

	if (info->proto == AIROHA_PPE_MC_PROTO_IPV4) {
		mac[0] = 0x01;
		mac[1] = 0x00;
		mac[2] = 0x5e;
		mac[3] = info->grp_addr[1] & 0x7f;
		mac[4] = info->grp_addr[2];
		mac[5] = info->grp_addr[3];
	} else if (info->proto == AIROHA_PPE_MC_PROTO_IPV6) {
		mac[0] = 0x33;
		mac[1] = 0x33;
		memcpy(&mac[2], &info->grp_addr[12], 4);
	}
}

static bool airoha_ppe_mc_match(const struct airoha_foe_entry *hwe,
					const struct airoha_ppe_mc_info *info)
{
	u8 mac[ETH_ALEN];

	if (!(hwe->bridge.ib2 & AIROHA_FOE_IB2_MULTICAST))
		return false;

	airoha_ppe_mc_group_mac(info, mac);
	return hwe->bridge.l2.common.dest_mac_hi == get_unaligned_be32(mac) &&
	       hwe->bridge.l2.common.dest_mac_lo == get_unaligned_be16(mac + 4);
}

static struct airoha_foe_entry *
airoha_ppe_mc_find_locked(struct airoha_ppe *ppe,
				  const struct airoha_ppe_mc_info *info,
				  u32 foe_index, u32 *hash)
{
	u32 total = airoha_ppe_get_total_num_entries(ppe);
	u32 i;

	if (foe_index < total) {
		struct airoha_foe_entry *hwe;

		hwe = airoha_ppe_foe_get_entry_locked(ppe, foe_index);
		if (hwe && airoha_ppe_mc_match(hwe, info)) {
			*hash = foe_index;
			return hwe;
		}
	}

	for (i = 0; i < total; i++) {
		struct airoha_foe_entry *hwe;

		if (i == foe_index)
			continue;
		hwe = airoha_ppe_foe_get_entry_locked(ppe, i);
		if (hwe && airoha_ppe_mc_match(hwe, info)) {
			*hash = i;
			return hwe;
		}
	}

	return NULL;
}

static int airoha_ppe_mc_apply(struct airoha_ppe *ppe,
				 struct airoha_foe_entry *hwe, u32 hash,
				 u32 port_mask)
{
	int err;

	/* SDK bits 0-3 are the only unambiguous EN7581 LAN mapping. */
	if (port_mask & ~0x0fU)
		return -EOPNOTSUPP;

	hwe->bridge.ib2 &= ~AIROHA_FOE_IB2_PORT_AG;
	hwe->bridge.ib2 |= FIELD_PREP(AIROHA_FOE_IB2_PORT_AG, port_mask);
	err = airoha_ppe_foe_commit_entry(ppe, hwe, hash, false);

	return err;
}

int airoha_ppe_mc_update(const struct airoha_ppe_mc_info *info,
			 u32 update_mode, u32 op_type, u32 port_mask, u32 local)
{
	struct airoha_ppe *ppe;
	struct airoha_foe_entry *hwe;
	u32 hash;
	int err;

	if (!info || (info->proto != AIROHA_PPE_MC_PROTO_IPV4 &&
		      info->proto != AIROHA_PPE_MC_PROTO_IPV6))
		return -EINVAL;
	if (update_mode & (AIROHA_PPE_MC_UPDATE_VLAN |
			   AIROHA_PPE_MC_UPDATE_SRCIP))
		return -EOPNOTSUPP;
	if (op_type != 0 || local)
		return -EOPNOTSUPP;

	ppe = airoha_ppe_mc_instance();
	if (!ppe)
		return -ENODEV;

	spin_lock_bh(&ppe_lock);
	hwe = airoha_ppe_mc_find_locked(ppe, info, 0xffff, &hash);
	if (!hwe)
		err = -ENOENT;
	else if (!port_mask)
		err = -ENOENT;
	else
		err = airoha_ppe_mc_apply(ppe, hwe, hash, port_mask);
	spin_unlock_bh(&ppe_lock);

	return err;
}
EXPORT_SYMBOL_GPL(airoha_ppe_mc_update);

int airoha_ppe_mc_clear(void)
{
	struct airoha_ppe *ppe = airoha_ppe_mc_instance();
	u32 total, sram, i;

	if (!ppe)
		return -ENODEV;

	total = airoha_ppe_get_total_num_entries(ppe);
	sram = airoha_ppe_get_total_sram_num_entries(ppe);
	spin_lock_bh(&ppe_lock);
	for (i = 0; i < total; i++) {
		struct airoha_foe_entry *hwe;

		hwe = airoha_ppe_foe_get_entry_locked(ppe, i);
		if (!hwe || !(hwe->bridge.ib2 & AIROHA_FOE_IB2_MULTICAST))
			continue;
		hwe->ib1 &= ~AIROHA_FOE_IB1_BIND_STATE;
		hwe->ib1 |= FIELD_PREP(AIROHA_FOE_IB1_BIND_STATE,
					AIROHA_FOE_STATE_INVALID);
		if (i < sram)
			airoha_ppe_foe_commit_sram_entry(ppe, i);
	}
	spin_unlock_bh(&ppe_lock);

	return 0;
}
EXPORT_SYMBOL_GPL(airoha_ppe_mc_clear);

int airoha_ppe_mc_get_portmask(const struct airoha_ppe_mc_info *info,
			       u32 foe_index)
{
	struct airoha_ppe *ppe = airoha_ppe_mc_instance();
	struct airoha_foe_entry *hwe;
	u32 hash, port_mask;

	if (!info)
		return -EINVAL;

	if (!ppe)
		return -ENODEV;

	spin_lock_bh(&ppe_lock);
	hwe = airoha_ppe_mc_find_locked(ppe, info, foe_index, &hash);
	port_mask = hwe ? FIELD_GET(AIROHA_FOE_IB2_PORT_AG,
					  hwe->bridge.ib2) : 0;
	spin_unlock_bh(&ppe_lock);

	return hwe ? (port_mask & 0x0f) : -ENOENT;
}
EXPORT_SYMBOL_GPL(airoha_ppe_mc_get_portmask);

int airoha_ppe_mc_subscribe(const struct airoha_ppe_mc_info *info,
			   u32 update_mode)
{
	return info && update_mode ? 0 : -EINVAL;
}
EXPORT_SYMBOL_GPL(airoha_ppe_mc_subscribe);

int airoha_ppe_mc_get_local(const struct airoha_ppe_mc_info *info)
{
	return info ? 0 : -EINVAL;
}
EXPORT_SYMBOL_GPL(airoha_ppe_mc_get_local);

int airoha_ppe_mc_get_origdev(struct airoha_ppe_mc_info *info)
{
	return info ? -EOPNOTSUPP : -EINVAL;
}
EXPORT_SYMBOL_GPL(airoha_ppe_mc_get_origdev);
#endif

static void airoha_ppe_foe_remove_flow(struct airoha_ppe *ppe,
				       struct airoha_flow_table_entry *e)
{
	lockdep_assert_held(&ppe_lock);

	hlist_del_init(&e->list);
	if (e->hash != 0xffff) {
		e->data.ib1 &= ~AIROHA_FOE_IB1_BIND_STATE;
		e->data.ib1 |= FIELD_PREP(AIROHA_FOE_IB1_BIND_STATE,
					  AIROHA_FOE_STATE_INVALID);
		airoha_ppe_foe_commit_entry(ppe, &e->data, e->hash, false);
		e->hash = 0xffff;
	}
	if (e->type == FLOW_TYPE_L2_SUBFLOW) {
		hlist_del_init(&e->l2_subflow_node);
		kfree(e);
	}
}

static void airoha_ppe_foe_remove_l2_flow(struct airoha_ppe *ppe,
					  struct airoha_flow_table_entry *e)
{
	struct hlist_head *head = &e->l2_flows;
	struct hlist_node *n;

	lockdep_assert_held(&ppe_lock);

	if (e->l2_cached) {
		rhashtable_remove_fast(&ppe->l2_flows, &e->l2_node,
				       airoha_l2_flow_table_params);
		list_del_init(&e->l2_gc_node);
		e->l2_cached = false;
	}
	hlist_for_each_entry_safe(e, n, head, l2_subflow_node)
		airoha_ppe_foe_remove_flow(ppe, e);
}

static void airoha_ppe_l2_revoke_locked(struct airoha_ppe *ppe)
{
	struct airoha_flow_table_entry *e, *tmp;
	/* Conservative global revocation is intentional: do not keep a hardware
	 * subflow alive after bridge membership, ifindex lifetime or bearer change.
	 * No flow_offload_mutex acquisition under RTNL; the cache has one spinlock.
	 */
	lockdep_assert_held(&ppe_lock);
	ppe->l2_generation++;
	list_for_each_entry_safe(e, tmp, &ppe->l2_templates, l2_gc_node) {
		airoha_ppe_foe_remove_l2_flow(ppe, e);
		ppe->l2_invalidations++;
	}
}

static void airoha_ppe_l2_revoke(struct airoha_ppe *ppe)
{
	spin_lock_bh(&ppe_lock);
	airoha_ppe_l2_revoke_locked(ppe);
	spin_unlock_bh(&ppe_lock);
}

static int airoha_ppe_l2_bridge_event(struct notifier_block *nb,
				      unsigned long event, void *ptr)
{
	struct airoha_ppe *ppe = container_of(nb, struct airoha_ppe, l2_bridge_nb);
	const struct br_fwd_policy_state *state = ptr;

	spin_lock_bh(&ppe_lock);
	ppe->l2_bridge_writers = state->writers;
	/* INIT also invalidates any pre-registration snapshot. END advances the
	 * generation so a snapshot from inside the mutation cannot be reused.
	 */
	airoha_ppe_l2_revoke_locked(ppe);
	spin_unlock_bh(&ppe_lock);
	return NOTIFY_OK;
}

/* Any bridge filtering policy requires software inspection unless a
 * connection-specific netfilter flow rule can represent it. MAC-only bridge
 * templates cannot express arbitrary IP/port/set/mark policies. Revocation is
 * conservative across namespaces and remains latched until the next probe;
 * removing a hook never silently reauthorizes a revoked hardware cache.
 */
static int airoha_ppe_l2_policy_event(struct notifier_block *nb,
                                    unsigned long event, void *ptr)
{
 struct airoha_ppe *ppe = container_of(nb, struct airoha_ppe, l2_policy_nb);
 struct airoha_flow_table_entry *e, *tmp;
 spin_lock_bh(&ppe_lock);
 ppe->l2_policy_latched = true;
 list_for_each_entry_safe(e, tmp, &ppe->l2_templates, l2_gc_node) {
  airoha_ppe_foe_remove_l2_flow(ppe, e);
  ppe->l2_invalidations++;
 }
 spin_unlock_bh(&ppe_lock);
 return NOTIFY_OK;
}

static int airoha_ppe_l2_netdev_event(struct notifier_block *nb,
                                     unsigned long event, void *ptr)
{
	struct airoha_ppe *ppe = container_of(nb, struct airoha_ppe, l2_netdev_nb);

	switch (event) {
	case NETDEV_DOWN:
	case NETDEV_UNREGISTER:
	case NETDEV_CHANGEUPPER:
	case NETDEV_CHANGEADDR:
	case NETDEV_CHANGEMTU:
	case NETDEV_CHANGE:
		break;
	default:
		return NOTIFY_DONE;
	}
	airoha_ppe_l2_revoke(ppe);
	return NOTIFY_DONE;
}

/* VLAN membership/filtering and FDB changes are switchdev notifications,
 * not reliably netdevice CHANGE events. Revoke before accepting new policy.
 */
static int airoha_ppe_l2_switchdev_event(struct notifier_block *nb,
                                      unsigned long event, void *ptr)
{
	struct airoha_ppe *ppe = container_of(nb, struct airoha_ppe, l2_switchdev_nb);
	if (event == SWITCHDEV_PORT_OBJ_ADD || event == SWITCHDEV_PORT_OBJ_DEL ||
	    event == SWITCHDEV_PORT_ATTR_SET)
		airoha_ppe_l2_revoke(ppe);
	return NOTIFY_DONE;
}
static int airoha_ppe_l2_switchdev_atomic_event(struct notifier_block *nb,
                                             unsigned long event, void *ptr)
{
	struct airoha_ppe *ppe = container_of(nb, struct airoha_ppe, l2_switchdev_atomic_nb);
	if (event == SWITCHDEV_FDB_ADD_TO_DEVICE || event == SWITCHDEV_FDB_DEL_TO_DEVICE)
		airoha_ppe_l2_revoke(ppe);
	return NOTIFY_DONE;
}

static void airoha_ppe_foe_flow_remove_entry(struct airoha_ppe *ppe,
					     struct airoha_flow_table_entry *e)
{
	spin_lock_bh(&ppe_lock);

	if (e->type == FLOW_TYPE_L2)
		airoha_ppe_foe_remove_l2_flow(ppe, e);
	else
		airoha_ppe_foe_remove_flow(ppe, e);

	spin_unlock_bh(&ppe_lock);
}

void airoha_ppe_remove_egress_flows(struct airoha_gdm_dev *dev)
{
	struct airoha_eth *eth = dev->eth;
	struct airoha_flow_table_entry *e, *tmp;
	struct rhashtable_iter iter;
	LIST_HEAD(remove_list);

	lockdep_assert_held(&flow_offload_mutex);

	/* TC replace and destroy callbacks share flow_offload_mutex with this walk.
	 * Collect matching objects before removal so rhashtable iteration continues
	 * through every entry in the current bucket.
	 */
	rhashtable_walk_enter(&eth->flow_table, &iter);
	rhashtable_walk_start(&iter);
	while ((e = rhashtable_walk_next(&iter))) {
		if (IS_ERR(e))
			continue;
		if (e->egress_dev == dev)
			list_add_tail(&e->gc_node, &remove_list);
	}
	rhashtable_walk_stop(&iter);
	rhashtable_walk_exit(&iter);

	/* Bearer changes invalidate GEM/T-CONT/LLID metadata in existing FOEs.
	 * Remove the software index at the same time; netfilter keeps forwarding
	 * and later connections can offload with the new mapping.
	 */
	list_for_each_entry_safe(e, tmp, &remove_list, gc_node) {
		list_del_init(&e->gc_node);
		airoha_ppe_foe_flow_remove_entry(eth->ppe, e);
		rhashtable_remove_fast(&eth->flow_table, &e->node,
				       airoha_flow_table_params);
		kfree(e);
	}
}

static int
airoha_ppe_foe_commit_subflow(struct airoha_ppe *ppe,
			      const struct airoha_foe_entry *bridge,
			      u32 hash, bool rx_wlan)
{
	u32 mask = AIROHA_FOE_IB1_BIND_PACKET_TYPE | AIROHA_FOE_IB1_BIND_UDP;
	struct airoha_foe_entry *hwe_p, hwe;
	int type;

	hwe_p = airoha_ppe_foe_get_entry_locked(ppe, hash);
	if (!hwe_p)
		return -EINVAL;

	memcpy(&hwe, hwe_p, sizeof(*hwe_p));
	hwe.ib1 = (hwe.ib1 & mask) | (bridge->ib1 & ~mask);

	type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe.ib1);
	if (airoha_is_7581(ppe->eth) && type == PPE_PKT_TYPE_BRIDGE) {
		/* Preserve the hardware-learned ingress key, including source MAC. */
		hwe.l2b.data = bridge->bridge.data;
		hwe.l2b.ib2 = bridge->bridge.ib2;
		hwe.l2b.vlan1 = bridge->bridge.l2.common.vlan1;
		hwe.l2b.vlan2 = bridge->bridge.l2.common.vlan2;
		hwe.l2b.etype = bridge->bridge.l2.common.etype;
		goto commit;
	}
	if (type >= PPE_PKT_TYPE_IPV6_ROUTE_3T) {
		memcpy(&hwe.ipv6.l2, &bridge->bridge.l2,
		       sizeof(hwe.ipv6.l2));
		hwe.ipv6.ib2 = bridge->bridge.ib2;
		/* setting smac_id to 0xf instruct the hw to keep original
		 * source mac address
		 */
		hwe.ipv6.l2.src_mac_hi = FIELD_PREP(AIROHA_FOE_MAC_SMAC_ID,
						    0xf);
	} else {
		memcpy(&hwe.bridge.l2, &bridge->bridge.l2,
		       sizeof(hwe.bridge.l2));
		hwe.bridge.ib2 = bridge->bridge.ib2;
		if (type == PPE_PKT_TYPE_IPV4_HNAPT)
			memcpy(&hwe.ipv4.new_tuple, &hwe.ipv4.orig_tuple,
			       sizeof(hwe.ipv4.new_tuple));
	}

	hwe.bridge.data = bridge->bridge.data;
commit:
	return airoha_ppe_foe_commit_entry(ppe, &hwe, hash, rx_wlan);
}

static int
airoha_ppe_foe_commit_subflow_entry(struct airoha_ppe *ppe,
				    struct airoha_flow_table_entry *e,
				    u32 hash, bool rx_wlan)
{
	struct airoha_flow_table_entry *f;
	int err;

	f = kzalloc(sizeof(*f), GFP_ATOMIC);
	if (!f)
		return -ENOMEM;

	err = airoha_ppe_foe_commit_subflow(ppe, &e->data, hash, rx_wlan);
	if (err) {
		kfree(f);
		return err;
	}

	hlist_add_head(&f->l2_subflow_node, &e->l2_flows);
	f->type = FLOW_TYPE_L2_SUBFLOW;
	f->hash = hash;

	return 0;
}

static struct net_device *
airoha_ppe_foe_get_bridge_master_rcu(struct net_device *dev)
{
	struct net_device *master;
	struct net_device *real_dev;

	if (netif_is_bridge_master(dev))
		return dev;

	master = netdev_master_upper_dev_get_rcu(dev);
	if (master && netif_is_bridge_master(master))
		return master;

	if (!is_vlan_dev(dev))
		return NULL;

	real_dev = vlan_dev_real_dev(dev);
	if (!real_dev)
		return NULL;

	if (netif_is_bridge_master(real_dev))
		return real_dev;

	master = netdev_master_upper_dev_get_rcu(real_dev);
	if (master && netif_is_bridge_master(master))
		return master;

	return NULL;
}

/* Resolve actual packet context, never substitute a trunk PVID for a tag.
 * A valid key alone is not authorization: insert_entry requires an exact TC
 * template in the same namespace/ingress/bridge/VID and both boot opt-ins.
 */
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

static bool airoha_ppe_foe_skb_is_local(const struct sk_buff *skb)
{
	struct net_device *master;
	const struct ethhdr *eh;
	bool local;

	/* NPU/WED RX may call PPE before eth_type_trans() has run. Keep
	 * unknown contexts local so a missing MAC header never enables the
	 * bridge fallback on an incompletely initialized skb.
	 */
	if (!skb->dev || !skb_mac_header_was_set(skb))
		return true;

	eh = eth_hdr(skb);
	if (ether_addr_equal_64bits(eh->h_dest, skb->dev->dev_addr))
		return true;

	rcu_read_lock();
	master = airoha_ppe_foe_get_bridge_master_rcu(skb->dev);
	local = master &&
		ether_addr_equal_64bits(eh->h_dest, master->dev_addr);
	rcu_read_unlock();

	return local;
}

/* Capture before reading context; commit verifies under the same cache
 * lock. A VLAN/FDB/netdevice revoke must invalidate in-flight preparation,
 * even if the template list was empty when the notification arrived.
 */
static bool airoha_ppe_l2_snapshot(struct airoha_ppe *ppe, u64 *generation)
{
 bool allowed;
 spin_lock_bh(&ppe_lock);
 allowed = !ppe->l2_policy_latched && !ppe->l2_bridge_writers;
 *generation = ppe->l2_generation;
 spin_unlock_bh(&ppe_lock);
 return allowed;
}

/* Must also validate packet-key preparation: a packet may have read the
 * old bridge/PVID before a writer and arrive at ppe_lock after a new template
 * was published. A current writer count of zero alone misses that race.
 */
static bool airoha_ppe_l2_ready_locked(struct airoha_ppe *ppe, u64 generation)
{
	lockdep_assert_held(&ppe_lock);
	return !ppe->l2_policy_latched && !ppe->l2_bridge_writers &&
	       generation == ppe->l2_generation;
}

static void airoha_ppe_foe_insert_entry(struct airoha_ppe *ppe,
					struct sk_buff *skb,
					u32 hash, bool rx_wlan)
{
	struct airoha_flow_table_entry *e;
	struct airoha_l2_flow_key key = {};
	struct airoha_foe_entry *hwe;
	bool commit_done = false;
	u64 bridge_generation;
	bool bridge_eligible = airoha_ppe_l2_snapshot(ppe, &bridge_generation) &&
		airoha_ppe_skb_l2_key(skb, &key);
	bool native_l2b;
	bool local = airoha_ppe_foe_skb_is_local(skb);
	struct hlist_node *n;
	u32 index, state;

	/* Also block cache hits and bridge fallback before resolving a path. */
	if (!ppe_bind_enable)
		return;

	spin_lock_bh(&ppe_lock);

	hwe = airoha_ppe_foe_get_entry_locked(ppe, hash);
	if (!hwe)
		goto unlock;

	state = FIELD_GET(AIROHA_FOE_IB1_BIND_STATE, hwe->ib1);
	if (state == AIROHA_FOE_STATE_BIND)
		goto unlock;

	native_l2b = airoha_is_7581(ppe->eth) &&
		FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, hwe->ib1) ==
		PPE_PKT_TYPE_BRIDGE;
	if (native_l2b) {
		/* Native L2B does not use the software L4 hash bucket. */
		if (local || !bridge_eligible)
			goto unlock;
		goto l2_lookup;
	}

	index = airoha_ppe_foe_get_entry_hash(ppe, hwe);
	hlist_for_each_entry_safe(e, n, &ppe->foe_flow[index], list) {
		if (e->type == FLOW_TYPE_L2_SUBFLOW) {
			state = FIELD_GET(AIROHA_FOE_IB1_BIND_STATE, hwe->ib1);
			if (state != AIROHA_FOE_STATE_BIND) {
				e->hash = 0xffff;
				airoha_ppe_foe_remove_flow(ppe, e);
			}
			continue;
		}

		if ((e->type == FLOW_TYPE_L2) ||
		    !airoha_ppe_foe_compare_entry(e, hwe))
			continue;

		airoha_ppe_foe_commit_entry(ppe, &e->data, hash, rx_wlan);
		commit_done = true;
		e->hash = hash;
	}

	if (commit_done)
		goto unlock;
	if (local)
		goto unlock;

l2_lookup:
	if (!bridge_eligible ||
	    !airoha_ppe_l2_ready_locked(ppe, bridge_generation))
		goto unlock;
	e = rhashtable_lookup_fast(&ppe->l2_flows, &key,
				   airoha_l2_flow_table_params);
	if (e)
		airoha_ppe_foe_commit_subflow_entry(ppe, e, hash, rx_wlan);

unlock:
	spin_unlock_bh(&ppe_lock);
}

static int
airoha_ppe_foe_l2_flow_commit_entry(struct airoha_ppe *ppe,
                                 struct airoha_flow_table_entry *e)
{
	struct airoha_flow_table_entry *prev;
	int err = 0;

	e->type = FLOW_TYPE_L2;
	INIT_LIST_HEAD(&e->l2_gc_node);
	spin_lock_bh(&ppe_lock);
	if (!airoha_ppe_l2_ready_locked(ppe, e->l2_generation)) {
		spin_unlock_bh(&ppe_lock);
		return -EOPNOTSUPP;
	}
	prev = rhashtable_lookup_get_insert_fast(&ppe->l2_flows, &e->l2_node,
					 airoha_l2_flow_table_params);
	if (prev) {
		err = IS_ERR(prev) ? PTR_ERR(prev) : -EEXIST;
	} else {
		e->l2_cached = true;
		list_add_tail(&e->l2_gc_node, &ppe->l2_templates);
	}
	spin_unlock_bh(&ppe_lock);
	return err;
}

static int airoha_ppe_foe_flow_commit_entry(struct airoha_ppe *ppe,
					    struct airoha_flow_table_entry *e)
{
	int type = FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, e->data.ib1);
	u32 hash;

	if (type == PPE_PKT_TYPE_BRIDGE)
		return airoha_ppe_foe_l2_flow_commit_entry(ppe, e);

	hash = airoha_ppe_foe_get_entry_hash(ppe, &e->data);
	e->type = FLOW_TYPE_L4;
	e->hash = 0xffff;

	spin_lock_bh(&ppe_lock);
	hlist_add_head(&e->list, &ppe->foe_flow[hash]);
	spin_unlock_bh(&ppe_lock);

	return 0;
}

static int airoha_ppe_get_entry_idle_time(struct airoha_ppe *ppe, u32 ib1)
{
	u32 state = FIELD_GET(AIROHA_FOE_IB1_BIND_STATE, ib1);
	u32 ts, ts_mask, now = airoha_ppe_get_timestamp(ppe);
	int idle;

	if (state == AIROHA_FOE_STATE_BIND) {
		ts = FIELD_GET(AIROHA_FOE_IB1_BIND_TIMESTAMP, ib1);
		ts_mask = AIROHA_FOE_IB1_BIND_TIMESTAMP;
	} else {
		ts = FIELD_GET(AIROHA_FOE_IB1_UNBIND_TIMESTAMP, ib1);
		now = FIELD_GET(AIROHA_FOE_IB1_UNBIND_TIMESTAMP, now);
		ts_mask = AIROHA_FOE_IB1_UNBIND_TIMESTAMP;
	}
	idle = now - ts;

	return idle < 0 ? idle + ts_mask + 1 : idle;
}

static void
airoha_ppe_foe_flow_l2_entry_update(struct airoha_ppe *ppe,
				    struct airoha_flow_table_entry *e)
{
	int min_idle = airoha_ppe_get_entry_idle_time(ppe, e->data.ib1);
	struct airoha_flow_table_entry *iter;
	struct hlist_node *n;

	lockdep_assert_held(&ppe_lock);

	hlist_for_each_entry_safe(iter, n, &e->l2_flows, l2_subflow_node) {
		struct airoha_foe_entry *hwe;
		u32 ib1, state;
		int idle;

		hwe = airoha_ppe_foe_get_entry_locked(ppe, iter->hash);
		if (!hwe)
			continue;

		ib1 = READ_ONCE(hwe->ib1);
		state = FIELD_GET(AIROHA_FOE_IB1_BIND_STATE, ib1);
		if (state != AIROHA_FOE_STATE_BIND) {
			iter->hash = 0xffff;
			airoha_ppe_foe_remove_flow(ppe, iter);
			continue;
		}

		idle = airoha_ppe_get_entry_idle_time(ppe, ib1);
		if (idle >= min_idle)
			continue;

		min_idle = idle;
		e->data.ib1 &= ~AIROHA_FOE_IB1_BIND_TIMESTAMP;
		e->data.ib1 |= ib1 & AIROHA_FOE_IB1_BIND_TIMESTAMP;
	}
}

static void airoha_ppe_foe_flow_entry_update(struct airoha_ppe *ppe,
					     struct airoha_flow_table_entry *e)
{
	struct airoha_foe_entry *hwe_p, hwe = {};

	spin_lock_bh(&ppe_lock);

	if (e->type == FLOW_TYPE_L2) {
		airoha_ppe_foe_flow_l2_entry_update(ppe, e);
		goto unlock;
	}

	if (e->hash == 0xffff)
		goto unlock;

	hwe_p = airoha_ppe_foe_get_entry_locked(ppe, e->hash);
	if (!hwe_p)
		goto unlock;

	memcpy(&hwe, hwe_p, sizeof(*hwe_p));
	if (!airoha_ppe_foe_compare_entry(e, &hwe)) {
		e->hash = 0xffff;
		goto unlock;
	}

	e->data.ib1 = hwe.ib1;
unlock:
	spin_unlock_bh(&ppe_lock);
}

static int airoha_ppe_entry_idle_time(struct airoha_ppe *ppe,
				      struct airoha_flow_table_entry *e)
{
	airoha_ppe_foe_flow_entry_update(ppe, e);

	return airoha_ppe_get_entry_idle_time(ppe, e->data.ib1);
}

/* Exact rule subset is independently testable. Unsupported constraints
 * must never become a broader hardware bridge permission.
 */
static bool airoha_ppe_l2_rule_exact(struct flow_rule *rule)
{
	struct flow_match_meta meta;
	struct flow_match_eth_addrs eth;
	struct flow_match_basic basic;
	int i;

	for (i = 0; i < FLOW_DISSECTOR_KEY_MAX; i++) {
		if (!flow_rule_match_key(rule, i))
			continue;
		switch (i) {
		case FLOW_DISSECTOR_KEY_META:
		case FLOW_DISSECTOR_KEY_CONTROL:
		case FLOW_DISSECTOR_KEY_BASIC:
		case FLOW_DISSECTOR_KEY_ETH_ADDRS:
		case FLOW_DISSECTOR_KEY_VLAN:break;
		default:return false;
		}
	}
	if (!flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_META) ||
	    !flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_ETH_ADDRS) ||
	    !flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_BASIC))
		return false;
	flow_rule_match_meta(rule, &meta);
	flow_rule_match_eth_addrs(rule, &eth);
	flow_rule_match_basic(rule, &basic);
	if (meta.mask->ingress_ifindex != U32_MAX || meta.mask->ingress_iftype ||
	    meta.mask->l2_miss || !is_broadcast_ether_addr(eth.mask->src) ||
	    !is_broadcast_ether_addr(eth.mask->dst) || basic.mask->ip_proto ||
	    basic.mask->n_proto != htons(0xffff) ||
	    basic.key->n_proto != htons(ETH_P_IP))
		return false;
	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_CONTROL)) {
		struct flow_match_control control;
		flow_rule_match_control(rule, &control);
		if (control.key->addr_type || control.mask->thoff || control.mask->flags)
			return false;
	}
	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_VLAN)) {
		struct flow_match_vlan vlan;
		flow_rule_match_vlan(rule, &vlan);
		if (vlan.mask->vlan_priority || vlan.mask->vlan_dei ||
		    (vlan.mask->vlan_eth_type &&
		     (vlan.mask->vlan_eth_type != htons(0xffff) ||
		      vlan.key->vlan_eth_type != htons(ETH_P_IP))))
			return false;
	}
	return true;
}

/* A route FOE represents an exact IP/transport tuple, not a wildcard
 * classifier. Match fields which the hardware ABI cannot encode stay in
 * software, including DSCP/TTL/TCP flags, VLAN scopes, marks and tunnels.
 * This deliberately rejects current nf_flow_table DSCP/FIN/RST predicates
 * until their hardware match/trap semantics have been demonstrated.
 */
static bool airoha_ppe_l3_rule_exact(struct flow_rule *rule, u16 family,
                                    struct net_device *odev)
{
 struct flow_match_meta meta;
 struct flow_match_control control;
 struct flow_match_basic basic;
 struct flow_match_ports ports;
 struct net_device *indev;
 bool valid;
 int i;

 for (i=0;i<FLOW_DISSECTOR_KEY_MAX;i++) {
  if (!flow_rule_match_key(rule,i)) continue;
  switch (i) {
  case FLOW_DISSECTOR_KEY_META: case FLOW_DISSECTOR_KEY_CONTROL:
  case FLOW_DISSECTOR_KEY_BASIC: case FLOW_DISSECTOR_KEY_PORTS: break;
  case FLOW_DISSECTOR_KEY_IPV4_ADDRS:
   if (family != FLOW_DISSECTOR_KEY_IPV4_ADDRS) return false;
   break;
  case FLOW_DISSECTOR_KEY_IPV6_ADDRS:
   if (family != FLOW_DISSECTOR_KEY_IPV6_ADDRS) return false;
   break;
  case FLOW_DISSECTOR_KEY_IP: {
   struct flow_match_ip ip;
   flow_rule_match_ip(rule,&ip);
   if (ip.mask->tos || ip.mask->ttl || ip.key->tos) return false;
   break;
  }
  case FLOW_DISSECTOR_KEY_TCP: {
   struct flow_match_tcp tcp;
   flow_rule_match_tcp(rule,&tcp);
   if (tcp.mask->flags) return false;
   break;
  }
  default: return false;
  }
 }
 if (!odev || !flow_rule_match_key(rule,FLOW_DISSECTOR_KEY_META) ||
     !flow_rule_match_key(rule,FLOW_DISSECTOR_KEY_CONTROL) ||
     !flow_rule_match_key(rule,FLOW_DISSECTOR_KEY_BASIC) ||
     !flow_rule_match_key(rule,FLOW_DISSECTOR_KEY_PORTS) ||
     !flow_rule_match_key(rule,family)) return false;
 flow_rule_match_meta(rule,&meta);flow_rule_match_control(rule,&control);
 flow_rule_match_basic(rule,&basic);flow_rule_match_ports(rule,&ports);
 if (meta.mask->ingress_ifindex != U32_MAX || meta.mask->ingress_iftype ||
     meta.mask->l2_miss || meta.key->ingress_ifindex <= 0 ||
     control.mask->addr_type != 0xffff || control.key->addr_type != family ||
     control.mask->thoff || control.mask->flags ||
     basic.mask->n_proto != htons(0xffff) || basic.mask->ip_proto != 0xff ||
     basic.key->n_proto != htons(family == FLOW_DISSECTOR_KEY_IPV4_ADDRS ? ETH_P_IP : ETH_P_IPV6) ||
     (basic.key->ip_proto != IPPROTO_TCP && basic.key->ip_proto != IPPROTO_UDP) ||
     ports.mask->src != htons(0xffff) || ports.mask->dst != htons(0xffff)) return false;
 if (family == FLOW_DISSECTOR_KEY_IPV4_ADDRS) {
  struct flow_match_ipv4_addrs ip4;
  flow_rule_match_ipv4_addrs(rule,&ip4);
  if (ip4.mask->src != cpu_to_be32(U32_MAX) || ip4.mask->dst != cpu_to_be32(U32_MAX)) return false;
 } else {
  struct flow_match_ipv6_addrs ip6;
  flow_rule_match_ipv6_addrs(rule,&ip6);
  if (memchr_inv(&ip6.mask->src,0xff,sizeof(ip6.mask->src)) ||
      memchr_inv(&ip6.mask->dst,0xff,sizeof(ip6.mask->dst))) return false;
 }
 /* Native route keys do not provide the context-complete L2B key. Do not
  * promote bridged, VLAN, or namespace-isolated traffic through this path.
  */
 rcu_read_lock();
 indev=dev_get_by_index_rcu(dev_net(odev),meta.key->ingress_ifindex);
 valid=indev && net_eq(dev_net(indev),&init_net) &&
       net_eq(dev_net(odev),&init_net) &&
       !netif_is_bridge_port(indev) && !netif_is_bridge_port(odev) &&
       !netif_is_bridge_master(indev) && !netif_is_bridge_master(odev) &&
       !is_vlan_dev(indev) && !is_vlan_dev(odev);
 rcu_read_unlock();
 return valid;
}

/* A hardware entry has exactly one egress. Reject absent/null targets early
 * and do not collapse multiple redirects into their final target.
 */
static bool airoha_ppe_rule_has_single_redirect(const struct flow_rule *rule)
{
 const struct flow_action_entry *act;
 bool found = false;
 int i;

 flow_action_for_each(i, act, &rule->action) {
  if (act->id != FLOW_ACTION_REDIRECT)
   continue;
  if (found || !act->dev)
   return false;
  found = true;
 }
 return found;
}

/* FOE VLAN fields describe the final output stack, not a push counter.
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

/* Unsupported per-port policy stays in the software bridge. MST can
 * have a per-VLAN forwarding state distinct from the port STP state.
 */
static bool airoha_ppe_l2_port_eligible(struct net_device *dev)
{
 const unsigned long unsupported = BR_ISOLATED | BR_PORT_LOCKED | BR_PORT_MAB |
  BR_VLAN_TUNNEL | BR_PROXYARP | BR_PROXYARP_WIFI | BR_NEIGH_SUPPRESS |
  BR_NEIGH_VLAN_SUPPRESS | BR_MRP_AWARE;

 return netif_running(dev) && netif_carrier_ok(dev) &&
        br_port_get_stp_state(dev) == BR_STATE_FORWARDING &&
        !br_port_flag_is_set(dev, unsupported);
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


static int airoha_ppe_flow_offload_replace(struct airoha_eth *eth,
					   struct flow_cls_offload *f)
{
	struct flow_rule *rule = flow_cls_offload_flow_rule(f);
	struct airoha_flow_table_entry *e;
	struct airoha_gdm_dev *egress_dev;
	struct airoha_flow_data data = {};
	struct airoha_l2_flow_key l2_key = {};
	u64 l2_generation = 0;
	struct net_device *odev = NULL;
	struct flow_action_entry *act;
	struct airoha_foe_entry hwe;
	u8 dsfield = 0, l4proto = 0;
	int err, i, offload_type;
	u16 addr_type = 0;

	/* FOE has no classifier chain/goto context. */
	if (f->common.chain_index) {
		NL_SET_ERR_MSG_MOD(f->common.extack, "PPE only represents TC chain zero");
		return -EOPNOTSUPP;
	}

	if (!airoha_ppe_rule_has_single_redirect(rule)) {
		NL_SET_ERR_MSG_MOD(f->common.extack,
				   "PPE requires exactly one valid redirect target");
		return -EOPNOTSUPP;
	}

	if (rhashtable_lookup(&eth->flow_table, &f->cookie,
			      airoha_flow_table_params))
		return -EEXIST;

	if (!flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_META))
		return -EOPNOTSUPP;

	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_CONTROL)) {
		struct flow_match_control match;

		flow_rule_match_control(rule, &match);
		addr_type = match.key->addr_type;
		if (flow_rule_has_control_flags(match.mask->flags,
						f->common.extack))
			return -EOPNOTSUPP;
	} else {
		return -EOPNOTSUPP;
	}

	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_BASIC)) {
		struct flow_match_basic match;

		flow_rule_match_basic(rule, &match);
		l4proto = match.key->ip_proto;
	} else {
		return -EOPNOTSUPP;
	}

	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_IP)) {
		struct flow_match_ip match;

		flow_rule_match_ip(rule, &match);
		dsfield = match.key->tos;
	}

	switch (addr_type) {
	case 0:
		offload_type = PPE_PKT_TYPE_BRIDGE;
		if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_ETH_ADDRS)) {
			struct flow_match_eth_addrs match;

			flow_rule_match_eth_addrs(rule, &match);
			memcpy(data.eth.h_dest, match.key->dst, ETH_ALEN);
			memcpy(data.eth.h_source, match.key->src, ETH_ALEN);
		} else {
			return -EOPNOTSUPP;
		}
		break;
	case FLOW_DISSECTOR_KEY_IPV4_ADDRS:
		offload_type = PPE_PKT_TYPE_IPV4_HNAPT;
		break;
	case FLOW_DISSECTOR_KEY_IPV6_ADDRS:
		offload_type = PPE_PKT_TYPE_IPV6_ROUTE_5T;
		break;
	default:
		return -EOPNOTSUPP;
	}

	flow_action_for_each(i, act, &rule->action) {
		/* Derive bridge output after validating its context. */
		if (offload_type == PPE_PKT_TYPE_BRIDGE) {
			if (act->id == FLOW_ACTION_REDIRECT)
				odev = act->dev;
			continue;
		}
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

	if (offload_type != PPE_PKT_TYPE_BRIDGE &&
	    !airoha_ppe_l3_rule_exact(rule, addr_type, odev)) {
		NL_SET_ERR_MSG_MOD(f->common.extack,
		 "PPE cannot represent this exact policy/context; retained in software");
		return -EOPNOTSUPP;
	}

	if (offload_type == PPE_PKT_TYPE_BRIDGE &&
	    (!airoha_ppe_l2_snapshot(eth->ppe, &l2_generation) ||
	     !airoha_ppe_l2_context(rule, odev, &data, &l2_key))) {
		NL_SET_ERR_MSG_MOD(f->common.extack,
			"PPE bridge actions do not match exact VLAN/port context");
		return -EOPNOTSUPP;
	}

	if (!is_valid_ether_addr(data.eth.h_source) ||
	    !is_valid_ether_addr(data.eth.h_dest))
		return -EINVAL;

	err = airoha_ppe_foe_entry_prepare(eth, &hwe, odev, offload_type,
					   &data, l4proto, dsfield,
					   &egress_dev);
	if (err) {
		if (err == -EOPNOTSUPP && egress_dev &&
		    egress_dev->flags & AIROHA_PRIV_F_PON)
			NL_SET_ERR_MSG_MOD(f->common.extack,
					   "PON egress has no unambiguous VLAN/P-bit to GEM mapping");
		return err;
	}

	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_PORTS)) {
		struct flow_match_ports ports;

		if (offload_type == PPE_PKT_TYPE_BRIDGE)
			return -EOPNOTSUPP;

		flow_rule_match_ports(rule, &ports);
		data.src_port = ports.key->src;
		data.dst_port = ports.key->dst;
	} else if (offload_type != PPE_PKT_TYPE_BRIDGE) {
		return -EOPNOTSUPP;
	}

	if (addr_type == FLOW_DISSECTOR_KEY_IPV4_ADDRS) {
		struct flow_match_ipv4_addrs addrs;

		flow_rule_match_ipv4_addrs(rule, &addrs);
		data.v4.src_addr = addrs.key->src;
		data.v4.dst_addr = addrs.key->dst;
		airoha_ppe_foe_entry_set_ipv4_tuple(&hwe, &data, false);
	}

	if (addr_type == FLOW_DISSECTOR_KEY_IPV6_ADDRS) {
		struct flow_match_ipv6_addrs addrs;

		flow_rule_match_ipv6_addrs(rule, &addrs);

		data.v6.src_addr = addrs.key->src;
		data.v6.dst_addr = addrs.key->dst;
		airoha_ppe_foe_entry_set_ipv6_tuple(&hwe, &data);
	}

	flow_action_for_each(i, act, &rule->action) {
		if (act->id != FLOW_ACTION_MANGLE)
			continue;

		if (offload_type == PPE_PKT_TYPE_BRIDGE)
			return -EOPNOTSUPP;

		switch (act->mangle.htype) {
		case FLOW_ACT_MANGLE_HDR_TYPE_TCP:
		case FLOW_ACT_MANGLE_HDR_TYPE_UDP:
			err = airoha_ppe_flow_mangle_ports(act, &data);
			break;
		case FLOW_ACT_MANGLE_HDR_TYPE_IP4:
			err = airoha_ppe_flow_mangle_ipv4(act, &data);
			break;
		case FLOW_ACT_MANGLE_HDR_TYPE_ETH:
			/* handled earlier */
			break;
		default:
			return -EOPNOTSUPP;
		}

		if (err)
			return err;
	}

	if (addr_type == FLOW_DISSECTOR_KEY_IPV4_ADDRS) {
		err = airoha_ppe_foe_entry_set_ipv4_tuple(&hwe, &data, true);
		if (err)
			return err;
	}

	e = kzalloc(sizeof(*e), GFP_KERNEL);
	if (!e)
		return -ENOMEM;

	INIT_LIST_HEAD(&e->gc_node);
	if (offload_type == PPE_PKT_TYPE_BRIDGE) {
		e->l2_key = l2_key;
		e->l2_generation = l2_generation;
	}

	e->cookie = f->cookie;
	e->egress_dev = egress_dev;
	memcpy(&e->data, &hwe, sizeof(e->data));

	err = airoha_ppe_foe_flow_commit_entry(eth->ppe, e);
	if (err)
		goto free_entry;

	err = rhashtable_insert_fast(&eth->flow_table, &e->node,
				     airoha_flow_table_params);
	if (err < 0)
		goto remove_foe_entry;

	return 0;

remove_foe_entry:
	airoha_ppe_foe_flow_remove_entry(eth->ppe, e);
free_entry:
	kfree(e);

	return err;
}

static int airoha_ppe_flow_offload_destroy(struct airoha_eth *eth,
					   struct flow_cls_offload *f)
{
	struct airoha_flow_table_entry *e;

	e = rhashtable_lookup(&eth->flow_table, &f->cookie,
			      airoha_flow_table_params);
	if (!e)
		return -ENOENT;

	airoha_ppe_foe_flow_remove_entry(eth->ppe, e);
	rhashtable_remove_fast(&eth->flow_table, &e->node,
			       airoha_flow_table_params);
	kfree(e);

	return 0;
}

void airoha_ppe_foe_entry_get_stats(struct airoha_ppe *ppe, u32 hash,
				    struct airoha_foe_stats64 *stats)
{
	struct airoha_eth *eth = ppe->eth;
	int ppe_num_stats_entries;
	struct airoha_npu *npu;
	struct airoha_foe_entry *hwe;
	u32 index;

	hwe = ppe->foe + hash * sizeof(*hwe);
	if (airoha_is_7581(eth) &&
	    FIELD_GET(AIROHA_FOE_IB1_BIND_PACKET_TYPE, READ_ONCE(hwe->ib1)) ==
	    PPE_PKT_TYPE_BRIDGE)
		return;

	ppe_num_stats_entries = airoha_ppe_get_total_num_stats_entries(ppe);
	if (ppe_num_stats_entries < 0)
		return;

	if (airoha_ppe_foe_get_flow_stats_index(ppe, hash, &index))
		return;

	if (index >= ppe_num_stats_entries)
		return;

	rcu_read_lock();

	npu = rcu_dereference(eth->npu);
	if (npu) {
		u64 packets = ppe->foe_stats[index].packets;
		u64 bytes = ppe->foe_stats[index].bytes;
		struct airoha_foe_stats npu_stats;

		memcpy_fromio(&npu_stats, &npu->stats[index],
			      sizeof(*npu->stats));
		stats->packets = packets << 32 | npu_stats.packets;
		stats->bytes = bytes << 32 | npu_stats.bytes;
	}

	rcu_read_unlock();
}

static int airoha_ppe_flow_offload_stats(struct airoha_eth *eth,
					 struct flow_cls_offload *f)
{
	struct airoha_flow_table_entry *e;
	u32 idle;

	e = rhashtable_lookup(&eth->flow_table, &f->cookie,
			      airoha_flow_table_params);
	if (!e)
		return -ENOENT;

	idle = airoha_ppe_entry_idle_time(eth->ppe, e);
	f->stats.lastused = jiffies - idle * HZ;

	if (e->hash != 0xffff) {
		struct airoha_foe_stats64 stats = {};

		airoha_ppe_foe_entry_get_stats(eth->ppe, e->hash, &stats);
		f->stats.pkts += (stats.packets - e->stats.packets);
		f->stats.bytes += (stats.bytes - e->stats.bytes);
		e->stats = stats;
	}

	return 0;
}

static int airoha_ppe_flow_offload_cmd(struct airoha_eth *eth,
				       struct flow_cls_offload *f)
{
	switch (f->command) {
	case FLOW_CLS_REPLACE:
		return airoha_ppe_flow_offload_replace(eth, f);
	case FLOW_CLS_DESTROY:
		return airoha_ppe_flow_offload_destroy(eth, f);
	case FLOW_CLS_STATS:
		return airoha_ppe_flow_offload_stats(eth, f);
	default:
		break;
	}

	return -EOPNOTSUPP;
}

static int airoha_ppe_flush_sram_entries(struct airoha_ppe *ppe)
{
	u32 sram_num_entries = airoha_ppe_get_total_sram_num_entries(ppe);
	struct airoha_foe_entry *hwe = ppe->foe;
	int i, err = 0;

	for (i = 0; i < sram_num_entries; i++) {
		int err;

		memset(&hwe[i], 0, sizeof(*hwe));
		err = airoha_ppe_foe_commit_sram_entry(ppe, i);
		if (err)
			break;
	}

	return err;
}

static struct airoha_npu *airoha_ppe_npu_get(struct airoha_eth *eth)
{
	struct airoha_npu *npu = airoha_npu_get(eth->dev);

	if (IS_ERR(npu)) {
		request_module("airoha-npu");
		npu = airoha_npu_get(eth->dev);
	}

	return npu;
}

static int airoha_ppe_wait_for_npu_init(struct airoha_eth *eth)
{
	int err;
	u32 val;

	/* PPE_FLOW_CFG default register value is 0. Since we reset FE
	 * during the device probe we can just check the configured value
	 * is not 0 here.
	 */
	err = read_poll_timeout(airoha_fe_rr, val, val, USEC_PER_MSEC,
				100 * USEC_PER_MSEC, false, eth,
				REG_PPE_PPE_FLOW_CFG(0));
	if (err)
		return err;

	if (airoha_ppe_is_enabled(eth, 1))
		err = read_poll_timeout(airoha_fe_rr, val, val, USEC_PER_MSEC,
					100 * USEC_PER_MSEC, false, eth,
					REG_PPE_PPE_FLOW_CFG(1));

	return err;
}

static int airoha_ppe_offload_setup(struct airoha_eth *eth)
{
	struct airoha_npu *npu = airoha_ppe_npu_get(eth);
	struct airoha_ppe *ppe = eth->ppe;
	int err, ppe_num_stats_entries;

	if (IS_ERR(npu))
		return PTR_ERR(npu);

	err = npu->ops.ppe_init(npu);
	if (err)
		goto error_npu_put;

	/* Wait for NPU PPE configuration to complete */
	err = airoha_ppe_wait_for_npu_init(eth);
	if (err)
		goto error_npu_put;

	ppe_num_stats_entries = airoha_ppe_get_total_num_stats_entries(ppe);
	if (ppe_num_stats_entries > 0) {
		err = npu->ops.ppe_init_stats(npu, ppe->foe_stats_dma,
					      ppe_num_stats_entries);
		if (err)
			goto error_npu_put;
	}

	airoha_ppe_hw_init(ppe);
	airoha_ppe_foe_flow_stats_reset(ppe, npu);

	rcu_assign_pointer(eth->npu, npu);
	synchronize_rcu();

	return 0;

error_npu_put:
	airoha_npu_put(npu);

	return err;
}

int airoha_ppe_setup_tc_block_cb(struct airoha_ppe_dev *dev, void *type_data)
{
	struct airoha_ppe *ppe = dev->priv;
	struct airoha_eth *eth = ppe->eth;
	struct flow_cls_offload *f = type_data;
	int err = 0;

	/* Reject new TC/netfilter HW rules before initializing PPE forwarding.
	 * Keep destroy/stats callbacks available to the existing cleanup path.
	 */
	if (!ppe_bind_enable && f->command == FLOW_CLS_REPLACE)
		return -EOPNOTSUPP;


	/* Netfilter flowtable can try to offload flower rules while not all
	 * the net_devices are registered or initialized. Delay offloading
	 * until all net_devices are registered in the system.
	 */
	if (!test_bit(DEV_STATE_REGISTERED, &eth->state))
		return -EBUSY;

	mutex_lock(&flow_offload_mutex);

	if (!eth->npu)
		err = airoha_ppe_offload_setup(eth);
	if (!err)
		err = airoha_ppe_flow_offload_cmd(eth, type_data);

	mutex_unlock(&flow_offload_mutex);

	return err;
}

void airoha_ppe_check_skb(struct airoha_ppe_dev *dev, struct sk_buff *skb,
			  u16 hash, bool rx_wlan)
{
	struct airoha_ppe *ppe = dev->priv;
	u32 ppe_hash_mask = airoha_ppe_get_total_num_entries(ppe) - 1;
	u16 now, diff;

	if (!ppe_bind_enable)
		return;

	if (hash > ppe_hash_mask)
		return;

	now = (u16)jiffies;
	diff = now - ppe->foe_check_time[hash];
	if (diff < HZ / 10)
		return;

	ppe->foe_check_time[hash] = now;
	airoha_ppe_foe_insert_entry(ppe, skb, hash, rx_wlan);
}

void airoha_ppe_init_upd_mem(struct airoha_gdm_dev *dev, const u8 *addr)
{
	struct airoha_gdm_port *port = dev->port;
	struct airoha_eth *eth = dev->eth;
	u32 val;

	val = (addr[2] << 24) | (addr[3] << 16) | (addr[4] << 8) | addr[5];
	airoha_fe_wr(eth, REG_UPDMEM_DATA(0), val);
	airoha_fe_wr(eth, REG_UPDMEM_CTRL(0),
		     FIELD_PREP(PPE_UPDMEM_ADDR_MASK, port->id) |
		     PPE_UPDMEM_WR_MASK | PPE_UPDMEM_REQ_MASK);

	val = (addr[0] << 8) | addr[1];
	airoha_fe_wr(eth, REG_UPDMEM_DATA(0), val);
	airoha_fe_wr(eth, REG_UPDMEM_CTRL(0),
		     FIELD_PREP(PPE_UPDMEM_ADDR_MASK, port->id) |
		     FIELD_PREP(PPE_UPDMEM_OFFSET_MASK, 1) |
		     PPE_UPDMEM_WR_MASK | PPE_UPDMEM_REQ_MASK);
}

struct airoha_ppe_dev *airoha_ppe_get_dev(struct device *dev)
{
	struct platform_device *pdev;
	struct device_node *np;
	struct airoha_eth *eth;

	np = of_parse_phandle(dev->of_node, "airoha,eth", 0);
	if (!np)
		return ERR_PTR(-ENODEV);

	pdev = of_find_device_by_node(np);
	if (!pdev) {
		dev_err(dev, "cannot find device node %s\n", np->name);
		of_node_put(np);
		return ERR_PTR(-ENODEV);
	}
	of_node_put(np);

	if (!try_module_get(THIS_MODULE)) {
		dev_err(dev, "failed to get the device driver module\n");
		goto error_pdev_put;
	}

	eth = platform_get_drvdata(pdev);
	if (!eth)
		goto error_module_put;

	if (!device_link_add(dev, &pdev->dev, DL_FLAG_AUTOREMOVE_SUPPLIER)) {
		dev_err(&pdev->dev,
			"failed to create device link to consumer %s\n",
			dev_name(dev));
		goto error_module_put;
	}

	return &eth->ppe->dev;

error_module_put:
	module_put(THIS_MODULE);
error_pdev_put:
	platform_device_put(pdev);

	return ERR_PTR(-ENODEV);
}
EXPORT_SYMBOL_GPL(airoha_ppe_get_dev);

void airoha_ppe_put_dev(struct airoha_ppe_dev *dev)
{
	struct airoha_ppe *ppe = dev->priv;
	struct airoha_eth *eth = ppe->eth;

	module_put(THIS_MODULE);
	put_device(eth->dev);
}
EXPORT_SYMBOL_GPL(airoha_ppe_put_dev);

int airoha_ppe_init(struct airoha_eth *eth)
{
	int foe_size, err, ppe_num_stats_entries;
	u32 ppe_num_entries;
	struct airoha_ppe *ppe;

	ppe = devm_kzalloc(eth->dev, sizeof(*ppe), GFP_KERNEL);
	if (!ppe)
		return -ENOMEM;

	ppe->dev.ops.setup_tc_block_cb = airoha_ppe_setup_tc_block_cb;
	ppe->dev.ops.check_skb = airoha_ppe_check_skb;
	ppe->dev.priv = ppe;
	ppe->eth = eth;
	eth->ppe = ppe;

	ppe_num_entries = airoha_ppe_get_total_num_entries(ppe);
	foe_size = ppe_num_entries * sizeof(struct airoha_foe_entry);
	ppe->foe = dmam_alloc_coherent(eth->dev, foe_size, &ppe->foe_dma,
				       GFP_KERNEL);
	if (!ppe->foe)
		return -ENOMEM;

	ppe->foe_flow = devm_kzalloc(eth->dev,
				     ppe_num_entries * sizeof(*ppe->foe_flow),
				     GFP_KERNEL);
	if (!ppe->foe_flow)
		return -ENOMEM;

	ppe_num_stats_entries = airoha_ppe_get_total_num_stats_entries(ppe);
	if (ppe_num_stats_entries > 0) {
		foe_size = ppe_num_stats_entries * sizeof(*ppe->foe_stats);
		ppe->foe_stats = dmam_alloc_coherent(eth->dev, foe_size,
						     &ppe->foe_stats_dma,
						     GFP_KERNEL);
		if (!ppe->foe_stats)
			return -ENOMEM;
	}

	ppe->foe_check_time = devm_kzalloc(eth->dev,
					   ppe_num_entries * sizeof(*ppe->foe_check_time),
					   GFP_KERNEL);
	if (!ppe->foe_check_time)
		return -ENOMEM;

	err = airoha_ppe_flush_sram_entries(ppe);
	if (err)
		return err;

	err = rhashtable_init(&eth->flow_table, &airoha_flow_table_params);
	if (err)
		return err;

	err = rhashtable_init(&ppe->l2_flows, &airoha_l2_flow_table_params);
	if (err)
		goto error_flow_table_destroy;

	INIT_LIST_HEAD(&ppe->l2_templates);
	err = airoha_ppe_debugfs_init(ppe);
	if (err)
		goto error_l2_flow_table_destroy;

	ppe->l2_netdev_nb.notifier_call = airoha_ppe_l2_netdev_event;
	err = register_netdevice_notifier(&ppe->l2_netdev_nb);
	if (err) {
		debugfs_remove(ppe->debugfs_dir);
		goto error_l2_flow_table_destroy;
	}
	ppe->l2_switchdev_nb.notifier_call = airoha_ppe_l2_switchdev_event;
	err = register_switchdev_blocking_notifier(&ppe->l2_switchdev_nb);
	if (err) {
		unregister_netdevice_notifier(&ppe->l2_netdev_nb);
		debugfs_remove(ppe->debugfs_dir);
		goto error_l2_flow_table_destroy;
	}
	ppe->l2_switchdev_atomic_nb.notifier_call = airoha_ppe_l2_switchdev_atomic_event;
	err = register_switchdev_notifier(&ppe->l2_switchdev_atomic_nb);
	if (err) {
		unregister_switchdev_blocking_notifier(&ppe->l2_switchdev_nb);
		unregister_netdevice_notifier(&ppe->l2_netdev_nb);
		debugfs_remove(ppe->debugfs_dir);
		goto error_l2_flow_table_destroy;
	}
	ppe->l2_policy_nb.notifier_call = airoha_ppe_l2_policy_event;
	err = nf_bridge_policy_notifier_register(&ppe->l2_policy_nb);
	if (err) {
		unregister_switchdev_notifier(&ppe->l2_switchdev_atomic_nb);
		unregister_switchdev_blocking_notifier(&ppe->l2_switchdev_nb);
		unregister_netdevice_notifier(&ppe->l2_netdev_nb);
		debugfs_remove(ppe->debugfs_dir);
		goto error_l2_flow_table_destroy;
	}
	ppe->l2_bridge_nb.notifier_call = airoha_ppe_l2_bridge_event;
	err = br_fwd_policy_register(&ppe->l2_bridge_nb);
	if (err) {
		nf_bridge_policy_notifier_unregister(&ppe->l2_policy_nb);
		unregister_switchdev_notifier(&ppe->l2_switchdev_atomic_nb);
		unregister_switchdev_blocking_notifier(&ppe->l2_switchdev_nb);
		unregister_netdevice_notifier(&ppe->l2_netdev_nb);
		debugfs_remove(ppe->debugfs_dir);
		goto error_l2_flow_table_destroy;
	}
	/* Register first, then scan. A racing callback may only latch true. */
	if (nf_bridge_policy_hooks_present())
		airoha_ppe_l2_policy_event(&ppe->l2_policy_nb, 0, NULL);
	debugfs_create_bool("xr_l2_policy_latched", 0400, ppe->debugfs_dir,
			    &ppe->l2_policy_latched);
	debugfs_create_u32("xr_l2_bridge_writers", 0400, ppe->debugfs_dir,
			   &ppe->l2_bridge_writers);
	debugfs_create_u64("xr_l2_generation", 0400, ppe->debugfs_dir,
			   &ppe->l2_generation);
	debugfs_create_u64("xr_l2_invalidations", 0400, ppe->debugfs_dir,
			   &ppe->l2_invalidations);
	return 0;

error_l2_flow_table_destroy:
	rhashtable_destroy(&ppe->l2_flows);
error_flow_table_destroy:
	rhashtable_destroy(&eth->flow_table);

	return err;
}

void airoha_ppe_deinit(struct airoha_eth *eth)
{
	struct airoha_npu *npu;

	/* Quiesce L2 binding before detaching its policy notifiers. A racing
	 * packet or TC callback must not republish during observer teardown.
	 */
	airoha_ppe_l2_policy_event(&eth->ppe->l2_policy_nb, 0, NULL);
	br_fwd_policy_unregister(&eth->ppe->l2_bridge_nb);
	nf_bridge_policy_notifier_unregister(&eth->ppe->l2_policy_nb);
	unregister_switchdev_notifier(&eth->ppe->l2_switchdev_atomic_nb);
	unregister_switchdev_blocking_notifier(&eth->ppe->l2_switchdev_nb);
	unregister_netdevice_notifier(&eth->ppe->l2_netdev_nb);

	mutex_lock(&flow_offload_mutex);

	npu = rcu_replace_pointer(eth->npu, NULL,
				  lockdep_is_held(&flow_offload_mutex));
	if (npu) {
		synchronize_rcu();
		npu->ops.ppe_deinit(npu);
		airoha_npu_put(npu);
	}

	mutex_unlock(&flow_offload_mutex);

	rhashtable_destroy(&eth->ppe->l2_flows);
	rhashtable_destroy(&eth->flow_table);
	debugfs_remove(eth->ppe->debugfs_dir);
}
