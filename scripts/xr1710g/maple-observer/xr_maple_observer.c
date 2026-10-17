// SPDX-License-Identifier: GPL-2.0-only
/* Passive, exact-binary-bound observer for one historical Maple fault site.
 * No register/stack repair, DMA/MMIO, payload reads or NPU activation.
 */
#include <linux/atomic.h>
#include <linux/capability.h>
#include <linux/debugfs.h>
#include <linux/kdebug.h>
#include <linux/maple_tree.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/sched/task_stack.h>
#include <linux/seq_file.h>
#include <linux/uaccess.h>

#ifndef XR_MAPLE_VM
#include "xr_maple_binding.h"
#endif

#define XR_FAULT_OFFSET 0xd4

struct xr_frame {
	unsigned long pc, sp, mas, node_reg, pivot_old, pivot_new;
	bool user;
};

struct xr_record {
	struct xr_frame frame;
	unsigned long stack_node[2];
	int read_status[2];
	bool stack_range_valid;
};

static struct xr_record xr_record;
static atomic_t xr_seen = ATOMIC_INIT(0);
static bool xr_ready;
static struct dentry *xr_file;

/* A notifier runs synchronously in the faulting task. Only read the node
 * scalar from that task's own active stack; never follow the node pointer.
 */
static bool xr_stack_range(const struct xr_frame *f)
{
	unsigned long start = (unsigned long)task_stack_page(current);
	unsigned long end = start + THREAD_SIZE;

	return start && f->sp >= start && f->sp < end &&
	       f->mas >= f->sp && f->mas <= end - sizeof(struct ma_state) &&
	       IS_ALIGNED(f->mas, sizeof(unsigned long));
}

static int xr_observe(const struct xr_frame *f)
{
	unsigned long at;
	int i;

	if (f->user || f->pc != (unsigned long)mas_empty_area_rev + XR_FAULT_OFFSET)
		return NOTIFY_DONE;
	if (atomic_cmpxchg(&xr_seen, 0, 1))
		return NOTIFY_DONE;

	xr_record.frame = *f;
	xr_record.stack_range_valid = xr_stack_range(f);
	for (i = 0; i < ARRAY_SIZE(xr_record.stack_node); i++) {
		xr_record.read_status[i] = -ERANGE;
		if (!xr_record.stack_range_valid)
			continue;
		at = f->mas + offsetof(struct ma_state, node);
		xr_record.read_status[i] = copy_from_kernel_nofault(
			&xr_record.stack_node[i], (void *)at, sizeof(unsigned long));
	}
	smp_store_release(&xr_ready, true);
	/* Two sequential samples, not an atomic snapshot or writer attribution. */
	pr_err("XR_MAPLE_SNAPSHOT schema=1 off=d4 mas=%lx sp=%lx reg=%lx old=%lx new=%lx\n",
	       f->mas, f->sp, f->node_reg, f->pivot_old, f->pivot_new);
	pr_err("XR_MAPLE_STACK valid=%u rc0=%d rc1=%d node0=%lx node1=%lx\n",
	       xr_record.stack_range_valid, xr_record.read_status[0],
	       xr_record.read_status[1], xr_record.stack_node[0], xr_record.stack_node[1]);
	return NOTIFY_DONE;
}

static int xr_die(struct notifier_block *nb, unsigned long event, void *data)
{
	struct die_args *args = data;
	struct pt_regs *r;
	struct xr_frame f;

	if (event != DIE_OOPS || !args || !args->regs)
		return NOTIFY_DONE;
	r = args->regs;
#ifdef XR_MAPLE_VM
	/* Disposable x86 guest: adapt register names. The registered callback's
	 * filter/read/one-shot/lifetime logic runs in the real kernel. */
	f.pc = r->ip; f.sp = r->sp; f.mas = r->r15;
	f.node_reg = r->ax; f.pivot_old = r->bx; f.pivot_new = r->cx;
#else
	f.pc = r->pc; f.sp = r->sp; f.mas = r->regs[15];
	f.node_reg = r->regs[9]; f.pivot_old = r->regs[2]; f.pivot_new = r->regs[3];
#endif
	f.user = user_mode(r);
	return xr_observe(&f);
}

static struct notifier_block xr_nb = { .notifier_call = xr_die };

static int xr_show(struct seq_file *s, void *unused)
{
	const struct xr_frame *f = &xr_record.frame;

	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	if (!smp_load_acquire(&xr_ready)) {
		seq_puts(s, "schema=1 captured=0\n");
		return 0;
	}
	seq_printf(s, "schema=1 captured=1 atomic_snapshot=0 off=d4 mas=%lx sp=%lx reg=%lx old=%lx new=%lx valid=%u rc0=%d rc1=%d node0=%lx node1=%lx\n",
		   f->mas, f->sp, f->node_reg, f->pivot_old, f->pivot_new,
		   xr_record.stack_range_valid, xr_record.read_status[0],
		   xr_record.read_status[1], xr_record.stack_node[0], xr_record.stack_node[1]);
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(xr);

#ifdef XR_MAPLE_VM
#include "xr_maple_vm_tests.h"
#endif

static int __init xr_init(void)
{
	int err;

	BUILD_BUG_ON(offsetof(struct ma_state, node) != 24);
#ifndef XR_MAPLE_VM
	if (!of_machine_is_compatible("gemtek,xr1710g"))
		return -ENODEV;
	/* Prevent applying the historical register interpretation to different
	 * compiler output. Relocations are already resolved in the saved Image. */
	if (memcmp((void *)mas_empty_area_rev, xr_maple_expected,
		   sizeof(xr_maple_expected)))
		return -ESTALE;
#endif
	xr_file = debugfs_create_file("xr_maple_observer", 0400, NULL, NULL, &xr_fops);
	if (IS_ERR(xr_file))
		return PTR_ERR(xr_file);
	err = register_die_notifier(&xr_nb);
	if (err)
		goto remove;
#ifdef XR_MAPLE_VM
	err = xr_vm_tests();
	if (err) {
		unregister_die_notifier(&xr_nb);
		goto remove;
	}
#endif
	pr_info("XR_MAPLE_OBSERVER ready exact_site=d4 passive=1\n");
	return 0;
remove:
	debugfs_remove(xr_file);
	return err;
}

static void __exit xr_exit(void)
{
	unregister_die_notifier(&xr_nb);
	debugfs_remove(xr_file);
	pr_info("XR_MAPLE_OBSERVER removed\n");
}
module_init(xr_init);
module_exit(xr_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("XR1710G passive one-shot Maple fault scalar observer");
