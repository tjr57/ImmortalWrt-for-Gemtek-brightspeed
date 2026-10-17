// SPDX-License-Identifier: GPL-2.0-only
/* Temporary fixed runtime-register observer for the AP23 NPU driver.
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
	{ 0x305000, "core0_pc" },
	{ 0x305004, "core0_sp" },
	{ 0x305008, "core0_lr" },
	{ 0x305100, "core1_pc" },
	{ 0x305104, "core1_sp" },
	{ 0x305108, "core1_lr" },
	{ 0x305200, "core2_pc" },
	{ 0x305204, "core2_sp" },
	{ 0x305208, "core2_lr" },
	{ 0x305300, "core3_pc" },
	{ 0x305304, "core3_sp" },
	{ 0x305308, "core3_lr" },
	{ 0x305400, "core4_pc" },
	{ 0x305404, "core4_sp" },
	{ 0x305408, "core4_lr" },
	{ 0x305500, "core5_pc" },
	{ 0x305504, "core5_sp" },
	{ 0x305508, "core5_lr" },
	{ 0x305600, "core6_pc" },
	{ 0x305604, "core6_sp" },
	{ 0x305608, "core6_lr" },
	{ 0x305700, "core7_pc" },
	{ 0x305704, "core7_sp" },
	{ 0x305708, "core7_lr" },
	{ 0x306020, "core0_boot_base" },
	{ 0x306024, "core1_boot_base" },
	{ 0x306028, "core2_boot_base" },
	{ 0x30602c, "core3_boot_base" },
	{ 0x306030, "core4_boot_base" },
	{ 0x306034, "core5_boot_base" },
	{ 0x306038, "core6_boot_base" },
	{ 0x30603c, "core7_boot_base" },
	{ 0x30c168, "heap_dram_base" },
	{ 0x30c16c, "heap_sram_size" },
	{ 0x306004, "boot_core_mask" },

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

	xr_dir = debugfs_create_dir("xr_npu_runtime", NULL);
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
MODULE_DESCRIPTION("XR1710G NPU PC/SP/boot registers; read-only opt-in");
