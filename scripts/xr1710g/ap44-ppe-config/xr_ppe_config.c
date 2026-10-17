// SPDX-License-Identifier: GPL-2.0-only
/* Fixed, read-only configuration snapshot on the owner's EN7581 board.
 * Register offsets are hardware facts cross-checked against target SDK
 * headers and upstream driver definitions; no vendor implementation copied.
 * No flow contents, packet payload, register writes or address parameters.
 */
#include <linux/capability.h>
#include <linux/debugfs.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/seq_file.h>

static struct dentry *directory;
static const u16 offsets[] = {
    0x200, 0x204, 0x208, 0x21c, 0x250, 0x288, 0x28c,
    0x290, 0x294, 0x298, 0x29c, 0x2a0, 0x2a4,
    0x2d0, 0x2d4, 0x2d8, 0x2dc, 0x2e0, 0x2e4, 0x2e8, 0x2ec
};

static int config_show(struct seq_file *s, void *unused)
{
    struct device *dev;
    struct resource *res;
    void __iomem *map;
    unsigned int ppe, i;
    int err = -ENODEV;

    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    if (!of_machine_is_compatible("gemtek,xr1710g"))
        return -ENODEV;
    dev = bus_find_device_by_name(&platform_bus_type, NULL, "1fb50000.ethernet");
    if (!dev)
        return -ENODEV;
    if (!device_trylock(dev)) {
        err = -EAGAIN;
        goto put;
    }
    if (!dev->driver || strcmp(dev->driver->name, "airoha_eth") ||
        !of_device_is_compatible(dev->of_node, "airoha,en7581-eth"))
        goto unlock;
    res = platform_get_resource_byname(to_platform_device(dev), IORESOURCE_MEM, "fe");
    if (!res || res->start != 0x1fb50000 || resource_size(res) != 0x2600)
        goto unlock;
    map = ioremap(res->start, resource_size(res));
    if (!map) {
        err = -ENOMEM;
        goto unlock;
    }
    seq_puts(s, "schema=1 atomic=0 readonly=1\n");
    for (ppe = 0; ppe < 2; ppe++)
        for (i = 0; i < ARRAY_SIZE(offsets); i++)
            seq_printf(s, "ppe=%u offset=0x%03x value=0x%08x\n",
                       ppe, offsets[i], readl(map + 0xc00 + ppe * 0x1000 + offsets[i]));
    iounmap(map);
    err = 0;
unlock:
    device_unlock(dev);
put:
    put_device(dev);
    return err;
}

DEFINE_SHOW_ATTRIBUTE(config);
static int __init config_init(void)
{
    struct dentry *file;
    directory = debugfs_create_dir("xr_ppe_config", NULL);
    if (IS_ERR(directory))
        return PTR_ERR(directory);
    file = debugfs_create_file("snapshot", 0400, directory, NULL, &config_fops);
    if (IS_ERR(file)) {
        debugfs_remove_recursive(directory);
        return PTR_ERR(file);
    }
    return 0;
}
static void __exit config_exit(void) { debugfs_remove_recursive(directory); }
module_init(config_init);
module_exit(config_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("XR1710G fixed read-only PPE configuration observer");
