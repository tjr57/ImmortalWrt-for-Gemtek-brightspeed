// SPDX-License-Identifier: GPL-2.0-only
/* Temporary scalar-only observer for the fingerprinted AP43 NPU firmware.
 * No MMIO writes, address parameters, payload reads, or automatic activation.
 */
#include <linux/capability.h>
#include <linux/debugfs.h>
#include <linux/device.h>
#include <linux/ioport.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/regmap.h>
#include <linux/seq_file.h>

#define XR_START 0x1e900000ULL
#define XR_SIZE  0x313000ULL

static const struct {
	u32 offset;
	const char *name;
 } xr_fields[] = {
    { 0x0046a8, "ppe_mode_global" },
    { 0x0046a4, "ppe_wan_mode_global" },
    { 0x30c030, "mailbox_payload_dma" },
    { 0x30c034, "mailbox_payload_length" },
    { 0x30c038, "mailbox_sequence" },
    { 0x30c03c, "mailbox_status" },
};

static struct dentry *xr_dir;

static bool xr_identity_matches(struct device *dev)
{
#ifdef XR_DIAG_VM_FIXTURE
	/* Only the OF identity boundary is adapted in the disposable x86 guest. */
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

static int xr_show(struct seq_file *s, void *unused)
{
	u32 values[2][ARRAY_SIZE(xr_fields)];
	u64 before, after;
	struct device *dev;
	struct resource *res;
	struct regmap *map;
	unsigned int pass, i;
	int err = -ENODEV;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	dev = bus_find_device_by_name(&platform_bus_type, NULL, "1e900000.npu");
	if (!dev)
		return -ENODEV;
	/* Refuse concurrent probe/remove instead of waiting behind it. */
	if (!device_trylock(dev)) {
		err = -EAGAIN;
		goto put;
	}
	if (!dev->driver || strcmp(dev->driver->name, "airoha-npu") ||
	    !xr_identity_matches(dev))
		goto unlock;
	res = platform_get_resource(to_platform_device(dev), IORESOURCE_MEM, 0);
	if (!res || res->start != XR_START || resource_size(res) != XR_SIZE)
		goto unlock;
	/* Reuse the driver's existing mapping; no private driver struct ABI. */
	map = dev_get_regmap(dev, NULL);
	if (!map)
		goto unlock;
	before = ktime_get_ns();
	for (pass = 0; pass < ARRAY_SIZE(values); pass++) {
		for (i = 0; i < ARRAY_SIZE(xr_fields); i++) {
			err = regmap_read(map, xr_fields[i].offset, &values[pass][i]);
			if (err)
				goto unlock;
		}
	}
	after = ktime_get_ns();
	/* Two sequential samples, not an atomic snapshot of the running NPU. */
	seq_printf(s, "schema=1 atomic=0 start_ns=%llu end_ns=%llu\n", before, after);
	for (i = 0; i < ARRAY_SIZE(xr_fields); i++)
		seq_printf(s, "%s offset=0x%06x first=0x%08x second=0x%08x stable=%u\n",
			   xr_fields[i].name, xr_fields[i].offset, values[0][i],
			   values[1][i], values[0][i] == values[1][i]);
	err = 0;
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
	.owner = THIS_MODULE,
	.open = xr_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = single_release,
};

static int __init xr_init(void)
{
	struct dentry *file;

	xr_dir = debugfs_create_dir("xr_ppe_init_observer", NULL);
	if (IS_ERR(xr_dir))
		return PTR_ERR(xr_dir);
	file = debugfs_create_file("snapshot", 0400, xr_dir, NULL, &xr_fops);
	if (IS_ERR(file)) {
		debugfs_remove_recursive(xr_dir);
		return PTR_ERR(file);
	}
	return 0;
}

static void __exit xr_exit(void)
{
	debugfs_remove_recursive(xr_dir);
}

module_init(xr_init);
module_exit(xr_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("XR1710G fixed scalar PPE initialization observer; opt-in only");
