// SPDX-License-Identifier: GPL-2.0-only
/* Guest-only platform/regmap fixture. Never built into the ARM observer. */
#include <linux/debugfs.h>
#include <linux/delay.h>
#include <linux/module.h>
#include <linux/mod_devicetable.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/regmap.h>
#include <linux/seq_file.h>

static int mode;
module_param(mode, int, 0400);
static unsigned int reads, writes, invalid_reads;
module_param(reads, uint, 0400);
module_param(writes, uint, 0400);
module_param(invalid_reads, uint, 0400);
static struct platform_device *fixture;
static bool locked;
module_param(locked, bool, 0400);

static int hold_set(const char *val, const struct kernel_param *kp)
{
	if (!fixture || strcmp(val, "1\n"))
		return -EINVAL;
	device_lock(&fixture->dev);
	WRITE_ONCE(locked, true);
	msleep(1500);
	WRITE_ONCE(locked, false);
	device_unlock(&fixture->dev);
	return 0;
}

static const struct kernel_param_ops hold_ops = { .set = hold_set };
module_param_cb(hold_lock, &hold_ops, NULL, 0200);

static const unsigned int offsets[] = {
	0x2cf4, 0x3964, 0x396c, 0x3974, 0x470c, 0x4710,
	0x30d180, 0x30d184, 0x30d188, 0x30d18c,
	0x30d190, 0x30d194, 0x30d198, 0x30d19c,
};

static int fixture_read(void *context, unsigned int reg, unsigned int *val)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(offsets); i++) {
		if (offsets[i] != reg)
			continue;
		reads++;
		if (mode == 6 && reg == 0x30d188)
			return -EIO;
		*val = 0x80000000U | reg;
		if (mode == 7 && reg == 0x3974)
			*val += reads;
		return 0;
	}
	invalid_reads++;
	return -EINVAL;
}

static int fixture_write(void *context, unsigned int reg, unsigned int val)
{
	writes++;
	return -EPERM;
}

static const struct regmap_bus fixture_bus = {
	.reg_read = fixture_read,
	.reg_write = fixture_write,
};

static const struct regmap_config fixture_config = {
	.reg_bits = 32,
	.val_bits = 32,
	.reg_stride = 4,
	.max_register = 0x312ffc,
	.cache_type = REGCACHE_NONE,
};

static int fixture_probe(struct platform_device *pdev)
{
	struct regmap *map;

	if (mode == 5)
		return 0;
	map = devm_regmap_init(&pdev->dev, &fixture_bus, NULL, &fixture_config);
	return PTR_ERR_OR_ZERO(map);
}

static const struct platform_device_id fixture_ids[] = {
	{ "1e900000.npu", 0 }, { },
};

static struct platform_driver fixture_driver = {
	.driver.name = "airoha-npu",
	.probe = fixture_probe,
	.id_table = fixture_ids,
};

static int __init fixture_init(void)
{
	struct resource res = {
		.start = 0x1e900000, .end = 0x1ec12fff,
		.flags = IORESOURCE_MEM,
	};
	struct property_entry props[] = {
		PROPERTY_ENTRY_STRING("xr-board", mode == 1 ? "wrong" : "gemtek,xr1710g"),
		PROPERTY_ENTRY_STRING("xr-chip", mode == 2 ? "wrong" : "airoha,en7581-npu"),
		{ },
	};
	int err;

	if (mode < 0 || mode > 7)
		return -EINVAL;
	if (mode == 3) { res.start += 0x1000; res.end += 0x1000; }
	if (mode == 4) res.end -= 0x1000;
	err = platform_driver_register(&fixture_driver);
	if (err)
		return err;
	fixture = platform_device_alloc("1e900000.npu", PLATFORM_DEVID_NONE);
	if (!fixture) { err = -ENOMEM; goto driver; }
	err = platform_device_add_resources(fixture, &res, 1);
	if (err)
		goto put;
	err = device_create_managed_software_node(&fixture->dev, props, NULL);
	if (err)
		goto put;
	err = platform_device_add(fixture);
	if (!err)
		return 0;
put:
	platform_device_put(fixture);
driver:
	platform_driver_unregister(&fixture_driver);
	return err;
}

static void __exit fixture_exit(void)
{
	platform_device_unregister(fixture);
	platform_driver_unregister(&fixture_driver);
}

module_init(fixture_init);
module_exit(fixture_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Isolated VM fixture for XR NPU address observer");
