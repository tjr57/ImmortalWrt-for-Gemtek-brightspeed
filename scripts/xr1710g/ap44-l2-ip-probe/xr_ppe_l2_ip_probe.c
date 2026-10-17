// SPDX-License-Identifier: GPL-2.0-only
/* One-shot, fixed EN7581 classification experiment. The controller must hold
 * the qualified recovery guard, classifier-only mode, WLAN NPU/bindings off.
 * Hardware facts from the pinned EN7581 reference, no vendor code copied.
 * Change only IPv4/IPv6 EtherType blacklist enables, restore on unload.
 */
#include <linux/capability.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

static struct device *owner;
static void __iomem *mapping;
static u32 original[2];
static bool applied;

static void __iomem *reg(unsigned int ppe, unsigned int off)
{
    return mapping + 0xc00 + ppe * 0x1000 + off;
}

static void restore(void)
{
    unsigned int i;
    for (i = 0; i < 2; i++) {
        /* Do not overwrite another owner's unexpected configuration. */
        if (readl(reg(i, 0x28c)) == (original[i] & ~0x18U)) {
            writel(original[i], reg(i, 0x28c));
            if (readl(reg(i, 0x28c)) != original[i])
                pr_err("xr_l2_ip: restore readback failed ppe=%u\n", i);
        } else if (readl(reg(i, 0x28c)) != original[i]) {
            pr_err("xr_l2_ip: changed externally ppe=%u; no overwrite\n", i);
        }
    }
}

static int __init probe_init(void)
{
    struct resource *res;
    unsigned int i;
    int err = -ENODEV;
    if (!capable(CAP_SYS_RAWIO) || !of_machine_is_compatible("gemtek,xr1710g"))
        return -EPERM;
    owner = bus_find_device_by_name(&platform_bus_type, NULL, "1fb50000.ethernet");
    if (!owner)
        return -ENODEV;
    if (!device_trylock(owner)) {
        err = -EAGAIN;
        goto put;
    }
    if (!owner->driver || strcmp(owner->driver->name, "airoha_eth") ||
        !of_device_is_compatible(owner->of_node, "airoha,en7581-eth"))
        goto unlock;
    res = platform_get_resource_byname(to_platform_device(owner), IORESOURCE_MEM, "fe");
    if (!res || res->start != 0x1fb50000 || resource_size(res) != 0x2600)
        goto unlock;
    mapping = ioremap(res->start, resource_size(res));
    if (!mapping) {
        err = -ENOMEM;
        goto unlock;
    }
    /* Check BOTH engines before touching either. Only the observed mode-1
     * profile is admissible; no writable address/mask/config parameters.
     * Slots 0/1 remain enabled: 802.1Q/802.1ad restrictions are unchanged.
     */
    for (i = 0; i < 2; i++) {
        original[i] = readl(reg(i, 0x28c));
        if (readl(reg(i, 0x288)) != 0x001d077f || original[i] != 0x1b ||
            readl(reg(i, 0x204)) != 0x00198000 ||
            readl(reg(i, 0x2d0)) != 0x88a88100 ||
            readl(reg(i, 0x2d4)) != 0x08000000 ||
            readl(reg(i, 0x2d8)) != 0x000086dd) {
            err = -EINVAL;
            goto unmap;
        }
    }
    for (i = 0; i < 2; i++) {
        writel(original[i] & ~0x18U, reg(i, 0x28c));
        if (readl(reg(i, 0x28c)) != (original[i] & ~0x18U)) {
            restore();
            err = -EIO;
            goto unmap;
        }
    }
    applied = true;
    pr_info("xr_l2_ip: classification-only IPv4/IPv6 blacklist probe applied\n");
    device_unlock(owner);
    return 0;
unmap:
    iounmap(mapping);
    mapping = NULL;
unlock:
    device_unlock(owner);
put:
    put_device(owner);
    owner = NULL;
    return err;
}

static void __exit probe_exit(void)
{
    device_lock(owner);
    if (applied && owner->driver && !strcmp(owner->driver->name, "airoha_eth"))
        restore();
    device_unlock(owner);
    iounmap(mapping);
    put_device(owner);
    pr_info("xr_l2_ip: fixed blacklist probe removed\n");
}
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("XR1710G fixed classifier-only IP blacklist probe");
