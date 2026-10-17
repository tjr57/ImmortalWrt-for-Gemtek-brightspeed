/* SPDX-License-Identifier: GPL-2.0-only */
/* Bounded, opt-in Mesh RX drop metadata. No packet bytes or key material. */
#ifndef XR_MESH_RX_AUDIT_H
#define XR_MESH_RX_AUDIT_H

#include <linux/moduleparam.h>
#include <linux/ktime.h>

#define XR_MESH_RX_RECORDS 32
struct xr_mesh_rx_drop {
	u64 serial;
	u64 monotonic_ms;
	u32 reason;
	u32 length;
	u32 ifindex;
	u32 fast_path;
};

static bool xr_mesh_rx_drop_audit;
module_param_named(mesh_rx_drop_audit, xr_mesh_rx_drop_audit, bool, 0600);
MODULE_PARM_DESC(mesh_rx_drop_audit, "Opt-in bounded Mesh RX drop metadata");
static DEFINE_SPINLOCK(xr_mesh_rx_drop_lock);
static struct xr_mesh_rx_drop xr_mesh_rx_drops[XR_MESH_RX_RECORDS];
static u64 xr_mesh_rx_drop_total;

static void xr_mesh_rx_drop_record(struct ieee80211_rx_data *rx,
				  u32 reason, bool fast_path)
{
	struct xr_mesh_rx_drop *entry;
	unsigned long flags;
	u64 serial;

	if (!READ_ONCE(xr_mesh_rx_drop_audit) || !rx->sdata || !rx->skb ||
	    !ieee80211_vif_is_mesh(&rx->sdata->vif))
		return;

	spin_lock_irqsave(&xr_mesh_rx_drop_lock, flags);
	serial = ++xr_mesh_rx_drop_total;
	entry = &xr_mesh_rx_drops[(serial - 1) % XR_MESH_RX_RECORDS];
	entry->serial = serial;
	entry->monotonic_ms = div_u64(ktime_get_mono_fast_ns(), NSEC_PER_MSEC);
	entry->reason = reason;
	entry->length = rx->skb->len;
	entry->ifindex = rx->sdata->dev->ifindex;
	entry->fast_path = fast_path;
	spin_unlock_irqrestore(&xr_mesh_rx_drop_lock, flags);
}

static int xr_mesh_rx_drop_get(char *buffer, const struct kernel_param *kp)
{
	struct xr_mesh_rx_drop snapshot[XR_MESH_RX_RECORDS];
	unsigned long flags;
	u64 total, first, serial;
	int used;

	(void)kp;
	spin_lock_irqsave(&xr_mesh_rx_drop_lock, flags);
	total = xr_mesh_rx_drop_total;
	memcpy(snapshot, xr_mesh_rx_drops, sizeof(snapshot));
	spin_unlock_irqrestore(&xr_mesh_rx_drop_lock, flags);

	first = total > XR_MESH_RX_RECORDS ? total - XR_MESH_RX_RECORDS + 1 : 1;
	used = scnprintf(buffer, PAGE_SIZE,
		"schema=1 enabled=%u total=%llu retained=%u\n"
		"serial monotonic_ms reason length ifindex fast_path\n",
		READ_ONCE(xr_mesh_rx_drop_audit), (unsigned long long)total,
		(unsigned int)min_t(u64, total, XR_MESH_RX_RECORDS));
	for (serial = first; serial <= total && used < PAGE_SIZE - 128; serial++) {
		const struct xr_mesh_rx_drop *entry =
			&snapshot[(serial - 1) % XR_MESH_RX_RECORDS];

		used += scnprintf(buffer + used, PAGE_SIZE - used,
			"%llu %llu 0x%08x %u %u %u\n",
			(unsigned long long)entry->serial,
			(unsigned long long)entry->monotonic_ms,
			entry->reason, entry->length, entry->ifindex,
			entry->fast_path);
	}
	return used;
}

static const struct kernel_param_ops xr_mesh_rx_drop_ops = {
	.get = xr_mesh_rx_drop_get,
};
module_param_cb(mesh_rx_drop_events, &xr_mesh_rx_drop_ops, NULL, 0400);
MODULE_PARM_DESC(mesh_rx_drop_events,
		 "Last 32 Mesh drops; reason 0 means unspecified fast-path drop");
#endif
