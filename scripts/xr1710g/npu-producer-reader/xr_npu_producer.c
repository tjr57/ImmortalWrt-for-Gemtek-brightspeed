// SPDX-License-Identifier: GPL-2.0-only
/* Fixed, read-only scalar trace reader; no NPU control or arbitrary addresses. */
#include <linux/capability.h>
#include <linux/debugfs.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_reserved_mem.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/regmap.h>
#include <linux/seq_file.h>
#include <linux/slab.h>
#include "candidate.h"

#define XR_BASE 0x84000000ULL
#define XR_REGION_SIZE 0xa00000ULL
#define XR_MAP_SIZE 0x45000
#define XR_TRACE 0x41000
#define XR_STRIDE 2048
#define XR_HARTS 8
#define XR_CAPACITY 32
#define XR_WORDS 12
#define XR_MAGIC 0x32505258

struct xr_backend {
#ifdef XR_DIAG_VM_FIXTURE
	struct regmap *map;
#else
	void __iomem *map;
#endif
};
struct xr_snapshot {
	u32 count[XR_HARTS];
	u32 words[XR_HARTS][XR_CAPACITY][XR_WORDS];
};
static struct dentry *xr_dir;

static int xr_read(struct xr_backend *b, u32 offset, u32 *value)
{
	if ((offset & 3) || offset > XR_MAP_SIZE - sizeof(*value))
		return -EINVAL;
#ifdef XR_DIAG_VM_FIXTURE
	return regmap_read(b->map, offset, value);
#else
	*value = ioread32(b->map + offset);
	return 0;
#endif
}

static bool xr_identity(struct device *dev)
{
#ifdef XR_DIAG_VM_FIXTURE
	const char *board, *chip;
	return !device_property_read_string(dev, "xr-board", &board) &&
	       !device_property_read_string(dev, "xr-chip", &chip) &&
	       !strcmp(board, "gemtek,xr1710g") &&
	       !strcmp(chip, "airoha,en7581-npu");
#else
	return of_machine_is_compatible("gemtek,xr1710g") &&
	       of_device_is_compatible(dev->of_node, "airoha,en7581-npu");
#endif
}

static bool xr_reserved_region(struct device *dev)
{
	u64 start, size;
#ifdef XR_DIAG_VM_FIXTURE
	if (device_property_read_u64(dev, "xr-mem-start", &start) ||
	    device_property_read_u64(dev, "xr-mem-size", &size) ||
	    !device_property_read_bool(dev, "xr-nomap"))
		return false;
#else
	struct resource res;
	struct device_node *np;
	bool nomap;
	if (of_reserved_mem_region_to_resource(dev->of_node, 0, &res))
		return false;
	np = of_parse_phandle(dev->of_node, "memory-region", 0);
	if (!np)
		return false;
	nomap = of_property_read_bool(np, "no-map") &&
		!of_property_read_bool(np, "reusable");
	of_node_put(np);
	if (!nomap)
		return false;
	start = res.start;
	size = resource_size(&res);
#endif
	return start == XR_BASE && size == XR_REGION_SIZE;
}

static int xr_collect(struct xr_backend *b, struct xr_snapshot *v)
{
	u32 value, h, r, w, first, last, count_after, offset;
	int err;

	/* Exact compiled candidate instructions, including aligned hook words.
	 * Reject original firmware before accessing the appended trace region. */
	for (w = 0; w < ARRAY_SIZE(xr_candidate_words); w++) {
		err = xr_read(b, xr_candidate_words[w].offset, &value);
		if (err)
			return err;
		if (value != xr_candidate_words[w].value)
			return -ENOEXEC;
	}
	for (h = 0; h < XR_HARTS; h++) {
		u32 header[4];
		offset = XR_TRACE + h * XR_STRIDE;
		for (w = 0; w < ARRAY_SIZE(header); w++) {
			err = xr_read(b, offset + w * 4, &header[w]);
			if (err)
				return err;
		}
		if (header[0] > XR_CAPACITY || header[1] != XR_MAGIC ||
		    header[2] != XR_CAPACITY || header[3] != h)
			return -EBADMSG;
		v->count[h] = header[0];
		for (r = 0; r < header[0]; r++) {
			u32 row = offset + 16 + r * XR_WORDS * 4;
			err = xr_read(b, row + 44, &first);
			if (err)
				return err;
			if (first != r + 1)
				return -EAGAIN;
			for (w = 0; w < XR_WORDS; w++) {
				err = xr_read(b, row + w * 4, &v->words[h][r][w]);
				if (err)
					return err;
			}
			err = xr_read(b, row + 44, &last);
			if (err)
				return err;
			if (last != first || v->words[h][r][11] != first)
				return -EAGAIN;
			if (v->words[h][r][10])
				return -EBADMSG;
		}
		err = xr_read(b, offset, &count_after);
		if (err)
			return err;
		if (count_after < header[0] || count_after > XR_CAPACITY)
			return -EAGAIN;
	}
	return 0;
}

static int xr_show(struct seq_file *s, void *unused)
{
	struct xr_snapshot *v;
	struct xr_backend b;
	struct device *dev;
	struct resource *res;
	u32 h, r, w;
	int err = -ENODEV;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	dev = bus_find_device_by_name(&platform_bus_type, NULL, "1e900000.npu");
	if (!dev)
		return -ENODEV;
	if (!device_trylock(dev)) {
		err = -EAGAIN;
		goto put;
	}
	if (!dev->driver || strcmp(dev->driver->name, "airoha-npu") ||
	    !xr_identity(dev) || !xr_reserved_region(dev))
		goto unlock;
	res = platform_get_resource(to_platform_device(dev), IORESOURCE_MEM, 0);
	if (!res || res->start != 0x1e900000 || resource_size(res) != 0x313000)
		goto unlock;
	v = kzalloc(sizeof(*v), GFP_KERNEL);
	if (!v) { err = -ENOMEM; goto unlock; }
#ifdef XR_DIAG_VM_FIXTURE
	b.map = dev_get_regmap(dev, NULL);
#else
	/* Same Device mapping type as airoha_npu_run_firmware. The exact DT
	 * no-map reservation is checked, and driver lifetime is locked above. */
	b.map = ioremap(XR_BASE, XR_MAP_SIZE);
#endif
	if (!b.map) { err = -ENODEV; goto free; }
	err = xr_collect(&b, v);
#ifndef XR_DIAG_VM_FIXTURE
	iounmap(b.map);
#endif
	if (err)
		goto free;
	seq_puts(s, "schema=2 atomic=0 source=producer-scalar record_words=12\n");
	for (h = 0; h < XR_HARTS; h++) {
		seq_printf(s, "hart=%u count=%u\n", h, v->count[h]);
		for (r = 0; r < v->count[h]; r++) {
			seq_printf(s, "hart=%u record=%u", h, r);
			for (w = 0; w < XR_WORDS; w++)
				seq_printf(s, " w%u=%08x", w, v->words[h][r][w]);
			seq_putc(s, '\n');
		}
	}
free:
	kfree(v);
unlock:
	device_unlock(dev);
put:
	put_device(dev);
	return err;
}

static int xr_open(struct inode *inode, struct file *file)
{
	return single_open(file, xr_show, NULL);
}
static const struct file_operations xr_fops = {
	.owner = THIS_MODULE, .open = xr_open, .read = seq_read,
	.llseek = seq_lseek, .release = single_release,
};
static int __init xr_init(void)
{
	struct dentry *file;
	xr_dir = debugfs_create_dir("xr_npu_producer", NULL);
	if (IS_ERR(xr_dir))
		return PTR_ERR(xr_dir);
	file = debugfs_create_file("snapshot", 0400, xr_dir, NULL, &xr_fops);
	if (IS_ERR(file)) {
		debugfs_remove_recursive(xr_dir);
		return PTR_ERR(file);
	}
	return 0;
}
static void __exit xr_exit(void) { debugfs_remove_recursive(xr_dir); }
module_init(xr_init);
module_exit(xr_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("XR1710G fixed scalar NPU producer trace; read-only opt-in");
