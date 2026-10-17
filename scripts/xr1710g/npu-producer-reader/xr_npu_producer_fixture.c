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

#include "candidate.h"
static u32 count_reads[8], commit_reads[8][32];
static int fixture_read(void *context, unsigned int reg, unsigned int *val)
{
 unsigned int i, rel, hart, off, row, word, count;
 for (i=0; i<ARRAY_SIZE(xr_candidate_words); i++) {
  if (reg != xr_candidate_words[i].offset) continue;
  reads++;
  if (mode==6) return -EIO;
  *val=xr_candidate_words[i].value;
  if ((mode==11 && reg==0xb160) || (mode==22 && reg==0x40000)) *val^=1;
  return 0;
 }
 if (reg < 0x41000 || reg >= 0x45000 || (reg&3)) goto invalid;
 rel=reg-0x41000;hart=rel/2048;off=rel%2048;
 count=mode==17?32:mode==21?0:2;
 if (off<16) {
  reads++;
  if (off==0) { *val=mode==13?0xffffffff:count;
    if (mode==19 && count_reads[hart]++) *val=count-1; }
  else if (off==4) *val=mode==12?0:mode==20?0x54505258:0x32505258;
  else if (off==8) *val=mode==14?31:32;
  else *val=mode==15?hart+1:hart;
  return 0;
 }
 row=(off-16)/48;word=((off-16)%48)/4;
 if (row>=count) goto invalid;
 reads++;
 switch(word) {
 case 0:*val=row;break;
 case 1:case 2:*val=0xc0140000;break;
 case 3:*val=0x300a005c;break;
 case 4:*val=5;break;
 case 5:case 6:*val=0x8a000080+row*2048;break;
 case 7:*val=0x30010014;break;
 case 8:*val=0x420ce000+row*16;break;
 case 9:*val=0;break;
 case 10:*val=mode==18?1:0;break;
 case 11:*val=mode==7?0:row+1;
   if (mode==16 && ++commit_reads[hart][row]%3==0) *val=0;
   break;
 default:goto invalid;
 }
 return 0;
invalid:
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
	.max_register = 0x44ffc,
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

        PROPERTY_ENTRY_U64("xr-mem-start", mode==8?0x84001000:0x84000000),
        PROPERTY_ENTRY_U64("xr-mem-size", mode==9?0x45000:0xa00000),
        PROPERTY_ENTRY_BOOL(mode==10?"xr-no-nomap":"xr-nomap"),
        { },
    };
    int err;

	if (mode < 0 || mode > 22)
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
