// SPDX-License-Identifier: GPL-2.0-only
/*
 * xr_iabt_observer - default-off, bounded, RAM-loaded observer for the recurring
 * arm64 IABT on this target.
 *
 * Historical failures included noncanonical IABT PC/LR and later DABT data
 * pointers whose shape is consistent with bit63 being clear. This observer
 * does not establish the corrupting writer, prove a saved-LR memory write,
 * or establish hardware causality. Interpret captures against frozen ELF.
 *
 * Design rule: the device side stays dumb and architecture-independent. It
 * records raw words, physical identities and scalar metadata; interpretation of
 * frame records happens offline against the verified frozen ELF. The kernel
 * text range is therefore supplied as a module parameter taken from that
 * verified ELF, because this kernel exports neither core_kernel_text() nor
 * _stext/_etext to modules.
 *
 * Capabilities, all default off:
 *   scan       rejected: deployed kernel cannot safely export stack ownership
 *              to this module; previous RCU-only stack access was unsafe
 *   diecap     die-notifier capture of pt_regs, a bounded raw word window at sp,
 *              the bit63 analysis of pc/lr, and the physical identity of the
 *              stack page. Oops context: no sleeping, no allocation, no locks
 *              held by driver subsystems.
 *   kint_mib   kernel-side pattern write/verify on a vmalloc buffer, which
 *              covers kernel-mode accesses and vmalloc-region pages (the class
 *              that VMAP_STACK kernel stacks belong to) and can report physical
 *              addresses - something userspace cannot do on this target because
 *              /proc/self/pagemap does not exist there.
 *
 * Hard limits: a module-internal deadline stops every activity; record arrays
 * are fixed size with an explicit dropped counter; nothing autoloads; scanning
 * is rejected on this target; die capture takes a verified text range.
 *
 * This is a diagnostic. It is not a repair, not a benefit measurement and not
 * an acceptance result.
 */
#include <linux/atomic.h>
#include <linux/bitops.h>
#include <linux/capability.h>
#include <linux/debugfs.h>
#include <linux/delay.h>
#include <linux/kdebug.h>
#include <linux/ktime.h>
#include <linux/kthread.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/sched/clock.h>
#include <linux/sched/task_stack.h>
#include <linux/seq_file.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include <linux/interrupt.h>
#ifdef CONFIG_ARM64
#include <asm/sysreg.h>
#endif
#include <linux/spinlock.h>
#include <linux/vmalloc.h>

#define XR_MAX_RECORDS 256u
#define XR_MAX_DIE_WORDS 64u
#define XR_MAX_TARGETS 8u
#define XR_COMM_LEN 16
#define XR_BIT63 BIT_ULL(63)

/* ---- parameters ---- */
static unsigned long text_start;
static unsigned long text_end;
static bool scan_enable;
static char *scan_prefix = "napi/";
static unsigned int scan_interval_ms = 200;
static unsigned int scan_max = 20000;
static bool diecap_enable;
static bool die_log_enable;
static unsigned long qdisc_fault_pc;
static unsigned int die_window_words = 48;
static unsigned int die_before_words = 24;
static unsigned int kint_mib;
static unsigned int kint_seconds = 60;
static unsigned int deadline_s = 600;
static unsigned int max_records = 64;

module_param(text_start, ulong, 0444);
module_param(text_end, ulong, 0444);
/* Kept to explicitly reject old unsafe invocation scripts. */
module_param(scan_enable, bool, 0444);
module_param(scan_prefix, charp, 0444);
module_param(scan_interval_ms, uint, 0444);
module_param(scan_max, uint, 0444);
module_param(diecap_enable, bool, 0444);
module_param(die_log_enable, bool, 0444);
module_param(qdisc_fault_pc, ulong, 0444);
module_param(die_window_words, uint, 0444);
module_param(die_before_words, uint, 0444);
module_param(kint_mib, uint, 0444);
module_param(kint_seconds, uint, 0444);
module_param(deadline_s, uint, 0444);
module_param(max_records, uint, 0444);
MODULE_PARM_DESC(text_start, "core kernel text start from the verified frozen ELF");
MODULE_PARM_DESC(text_end, "core kernel text end from the verified frozen ELF");
MODULE_PARM_DESC(scan_enable, "unsupported on deployed kernel: returns EOPNOTSUPP");
MODULE_PARM_DESC(scan_prefix, "target task comm prefix; empty means every task");
MODULE_PARM_DESC(diecap_enable, "register the die notifier capture");
MODULE_PARM_DESC(kint_mib, "kernel-side pattern test buffer size in MiB; 0 disables");
MODULE_PARM_DESC(deadline_s, "hard stop for every activity, in seconds");

/* ---- records ---- */
struct xr_scan_record {
	u64 stamp;
	u64 vaddr;
	u64 value;
	u64 restored;
	u64 paddr;
	u64 reread1;
	u64 reread2;
	u64 offset_in_stack;
	u64 iteration;
	pid_t pid;
	char comm[XR_COMM_LEN];
	int paddr_valid;
	int stable;
};

struct xr_die_record {
	u64 stamp;
	u64 pc;
	u64 lr;
	u64 sp;
	u64 fp;
	u64 pstate;
	u64 sp_paddr;
	u64 pc_restored;
	u64 lr_restored;
	u64 words[XR_MAX_DIE_WORDS];
	u64 word_addr[XR_MAX_DIE_WORDS];
	u64 word_paddr[XR_MAX_DIE_WORDS];
	int word_error[XR_MAX_DIE_WORDS];
	int word_paddr_valid[XR_MAX_DIE_WORDS];
	int sp_in_stack;
	u64 stack_base, stack_end;
	u64 gpr[31];
	u64 esr, far;
	unsigned int cpu, irq_context, gpr_count;
	u64 slot_addr, slot_value1, slot_value2, slot_paddr;
	int slot_attempted, slot_error1, slot_error2, slot_paddr_valid;
	u64 regs_base, regs_end;
	int word_overlaps_regs[XR_MAX_DIE_WORDS];
	unsigned int word_count;
	int pc_is_candidate;
	int lr_is_candidate;
	int pc_in_text;
	int lr_in_text;
	int sp_paddr_valid;
	char comm[XR_COMM_LEN];
	pid_t pid;
};

struct xr_kint_counters {
	u64 words_filled;
	u64 words_checked;
	u64 sub_passes;
	u64 mismatches;
	u64 bit_hist[64];
	u64 first_bad_vaddr;
	u64 first_bad_value;
	u64 first_bad_expected;
	u64 first_bad_paddr;
	u64 buffer_vaddr;
	u64 buffer_paddr;
	int buffer_paddr_valid;
	int completed;
	int ran;
};

static struct xr_scan_record scan_records[XR_MAX_RECORDS];
static unsigned int scan_record_count;
static u64 scan_dropped;
static u64 scan_iterations;
static u64 scan_tasks_seen;
static u64 scan_candidates;

static struct xr_die_record die_record;
static atomic_t die_claimed = ATOMIC_INIT(0);
static atomic64_t die_events = ATOMIC64_INIT(0);

static struct xr_kint_counters kint;
static DEFINE_SPINLOCK(kint_lock);
static DEFINE_SPINLOCK(scan_lock);
/* 0 empty, 1 writer owns it, 2 immutable record published. */
#define XR_DIE_READY 2

static u64 xr_deadline_ns;
static struct dentry *xr_dir;
static struct task_struct *kint_thread;
static struct notifier_block xr_die_nb;

/* ---- small helpers ---- */

static bool xr_in_text(unsigned long v)
{
	return text_end > text_start && v >= text_start && v < text_end;
}

/* The exact recorded signature: bit63 clear, and setting it yields text. */
static bool xr_is_candidate(u64 w)
{
	if (w & XR_BIT63)
		return false;
	return xr_in_text((unsigned long)(w | XR_BIT63));
}

static u64 xr_stamp(void)
{
	return sched_clock();
}

static bool xr_expired(void)
{
	return xr_deadline_ns && ktime_get_ns() >= xr_deadline_ns;
}

/* Physical identity of a kernel address. Returns 0 and sets *ok = 0 when the
 * mapping cannot be resolved; never fails the caller. */
static u64 xr_phys_of(const void *v, int *ok)
{
	unsigned long addr = (unsigned long)v;
	unsigned long pfn;

	*ok = 0;
	if (is_vmalloc_addr((void *)addr)) {
		struct page *vpage = vmalloc_to_page((void *)addr);

		if (!vpage)
			return 0;
		pfn = page_to_pfn(vpage);
	} else {
		struct page *page;

		if (!virt_addr_valid((void *)addr))
			return 0;
		page = virt_to_page((void *)addr);
		if (!page)
			return 0;
		pfn = page_to_pfn(page);
	}
	if (!pfn)
		return 0;
	*ok = 1;
	return ((u64)pfn << PAGE_SHIFT) + (addr & ~PAGE_MASK);
}

/* ---- scan capability ---- */

static void __maybe_unused xr_record_candidate(struct task_struct *p, unsigned long addr,
				u64 value, u64 offset, u64 iteration)
{
	struct xr_scan_record *r;
	u64 r1, r2;
	unsigned long flags;
	int ok = 0;

	scan_candidates++;
	/* NOCHECK re-reads of the same cross-frame stack word as the scan loop. */
	if (copy_from_kernel_nofault(&r1, (void *)addr, sizeof(r1)) ||
	    copy_from_kernel_nofault(&r2, (void *)addr, sizeof(r2)))
		return;
	spin_lock_irqsave(&scan_lock, flags);
	if (scan_record_count >= max_records ||
	    scan_record_count >= XR_MAX_RECORDS) {
		scan_dropped++;
		spin_unlock_irqrestore(&scan_lock, flags);
		return;
	}
	r = &scan_records[scan_record_count++];
	memset(r, 0, sizeof(*r));
	r->stamp = xr_stamp();
	r->vaddr = addr;
	r->value = value;
	r->restored = value | XR_BIT63;
	r->paddr = xr_phys_of((const void *)addr, &ok);
	r->paddr_valid = ok;
	r->reread1 = r1;
	r->reread2 = r2;
	r->offset_in_stack = offset;
	r->iteration = iteration;
	r->pid = p ? p->pid : 0;
	if (p)
		strscpy(r->comm, p->comm, sizeof(r->comm));
	r->stable = (r1 == value && r2 == value);
	spin_unlock_irqrestore(&scan_lock, flags);
}

/* Extracted so the guest fixture can exercise the exact detection loop over a
 * synthetic buffer. The ARM artifact uses this same code path. */
static int __maybe_unused xr_scan_range(struct task_struct *p, unsigned long base, size_t len,
			 u64 iteration)
{
	unsigned long addr, end = base + len;
	int hits = 0;

	for (addr = base; addr + sizeof(u64) <= end; addr += sizeof(u64)) {
		/* NOCHECK: this deliberately reads the whole stack region, which
		 * includes KASAN redzones between other frames' locals. The
		 * kernel's own dump_backtrace() uses the same accessor for the
		 * same reason. Bounds are enforced by the loop, not by KASAN. */
		u64 w;

		if (copy_from_kernel_nofault(&w, (void *)addr, sizeof(w)))
			continue;

		if (xr_is_candidate(w)) {
			xr_record_candidate(p, addr, w, addr - base, iteration);
			hits++;
		}
	}
	return hits;
}

/* Cross-task raw stack scanning cannot be offered by a module on the
 * deployed kernel: put_task_stack is not exported. RCU protects task_struct,
 * not its independently released VMAP_STACK allocation. Fail closed at init.
 */

/* ---- die-notifier capability ---- */

/* The one proven load site from the deployed ELF is:
 * __qdisc_run+0x44: ldr x20,[x19,#72]; +0x58: ldr x1,[x20,#272].
 * Snapshot only the source pointer word, never repair it or follow its value.
 * qdisc_fault_pc defaults to zero and must match a verified deployed ELF.
 */
static void xr_qdisc_slot(struct xr_die_record *r)
{
	unsigned long addr;
	if (!qdisc_fault_pc || r->pc != qdisc_fault_pc)
		return;
	if (!r->gpr[19] || r->gpr[19] > ULONG_MAX - 80)
		return;
	addr = r->gpr[19] + 72;
	r->slot_addr = addr;
	if ((addr & 7) || (!virt_addr_valid((void *)addr) && !is_vmalloc_addr((void *)addr)))
		return;
	r->slot_attempted = 1;
	r->slot_error1 = copy_from_kernel_nofault(&r->slot_value1, (void *)addr, 8);
	r->slot_error2 = copy_from_kernel_nofault(&r->slot_value2, (void *)addr, 8);
	if (!r->slot_error1 && !r->slot_error2)
		r->slot_paddr = xr_phys_of((void *)addr, &r->slot_paddr_valid);
}

/* Bounded scalar export to the already-running /dev/kmsg collector.
 * __die logs its Oops header before calling the notifier on arm64. The
 * collector therefore retains these subsequent lines in its fault tail.
 * Never print a claim that these are pre-exception saved-LR contents.
 */
static void xr_die_log(const struct xr_die_record *r)
{
	unsigned int i;
	if (!die_log_enable)
		return;
	pr_info("XR_IABT_DIE_BEGIN schema=4 stamp=%llu pid=%d pc=0x%llx lr=0x%llx sp=0x%llx fp=0x%llx pstate=0x%llx words=%u\n",
		r->stamp, r->pid, r->pc, r->lr, r->sp, r->fp, r->pstate, r->word_count);
	pr_info("XR_IABT_CONTEXT cpu=%u irq=%u esr=0x%llx far=0x%llx regs=%u\n",
		r->cpu, r->irq_context, r->esr, r->far, r->gpr_count);
	for (i = 0; i < r->gpr_count; i++)
		pr_info("XR_IABT_REG i=%u value=0x%016llx\n", i, r->gpr[i]);
	if (qdisc_fault_pc && r->pc == qdisc_fault_pc)
		pr_info("XR_IABT_POINTER va=0x%llx attempted=%d first=0x%016llx err1=%d second=0x%016llx err2=%d pa=0x%llx pa_valid=%d\n",
			r->slot_addr, r->slot_attempted, r->slot_value1, r->slot_error1,
			r->slot_value2, r->slot_error2, r->slot_paddr, r->slot_paddr_valid);
	pr_info("XR_IABT_STACK base=0x%llx end=0x%llx sp_valid=%d sp_pa=0x%llx pa_valid=%d regs=[0x%llx,0x%llx)\n",
		r->stack_base, r->stack_end, r->sp_in_stack, r->sp_paddr,
		r->sp_paddr_valid, r->regs_base, r->regs_end);
	for (i = 0; i < r->word_count; i++)
		pr_info("XR_IABT_WORD i=%u va=0x%llx value=0x%016llx err=%d pa=0x%llx pa_valid=%d regs_overlap=%d\n",
			i, r->word_addr[i], r->words[i], r->word_error[i],
			r->word_paddr[i], r->word_paddr_valid[i], r->word_overlaps_regs[i]);
	pr_info("XR_IABT_DIE_END words=%u\n", r->word_count);
}

static int xr_die_handler(struct notifier_block *nb, unsigned long val,
			  void *data)
{
	struct die_args *args = data;
	struct pt_regs *regs;
	struct xr_die_record *r = &die_record;
	unsigned long sp, base, end, start;
	unsigned int i, want;
	int ok = 0;

	(void)nb;
	if (val != DIE_OOPS || !args || !args->regs || xr_expired())
		return NOTIFY_DONE;
	atomic64_inc(&die_events);
	/* First fault only. Claimed with a single atomic so no lock is taken in
	 * oops context, where the faulting path may already hold it. */
	/* try_module_get fails after GOING, closing the unload/pin race. */
	if (!try_module_get(THIS_MODULE))
		return NOTIFY_DONE;
	if (atomic_cmpxchg(&die_claimed, 0, 1) != 0) {
		module_put(THIS_MODULE);
		return NOTIFY_DONE;
	}
	/* Pin the module for the rest of this boot. The notifier callback lives
	 * in this module, so allowing rmmod after a capture would leave the die
	 * chain pointing at freed code. Refusing unload is the safe behaviour;
	 * the captured evidence stays readable and the epoch is recovered by
	 * reboot, which a faulted epoch requires anyway. */

	regs = args->regs;
	memset(r, 0, sizeof(*r));
	r->regs_base = (unsigned long)regs;
	r->regs_end = r->regs_base + sizeof(*regs);
	r->stamp = xr_stamp();
	r->cpu = raw_smp_processor_id();
	r->irq_context = in_interrupt();
	r->esr = args->err;
	r->pc = instruction_pointer(regs);
	r->sp = regs->sp;
	r->pid = current->pid;
	strscpy(r->comm, current->comm, sizeof(r->comm));
#ifdef CONFIG_ARM64
	memcpy(r->gpr, regs->regs, sizeof(r->gpr));
	r->gpr_count = 31;
	r->far = read_sysreg(far_el1);
	r->lr = regs->regs[30];
	r->fp = regs->regs[29];
	r->pstate = regs->pstate;
#else
	/* Guest-only shape: the ARM artifact is the one that matters, but the
	 * checks must exercise the same handler body on x86. */
	r->lr = 0;
	r->fp = 0;
	r->pstate = regs->flags;
#endif
	xr_qdisc_slot(r);
	r->pc_in_text = xr_in_text(r->pc);
	r->lr_in_text = xr_in_text(r->lr);
	r->pc_is_candidate = xr_is_candidate(r->pc);
	r->lr_is_candidate = xr_is_candidate(r->lr);
	r->pc_restored = r->pc | XR_BIT63;
	r->lr_restored = r->lr | XR_BIT63;
	/* Current task is alive for this callback. Do not interpret a random
	 * vmalloc address as a valid stack or touch its page tables. */
	base = (unsigned long)task_stack_page(current);
	end = base + THREAD_SIZE;
	r->stack_base = base;
	r->stack_end = end;
	sp = r->sp & ~(sizeof(u64) - 1);
	if (base && end > base && sp >= base && sp < end) {
		r->sp_in_stack = 1;
		r->sp_paddr = xr_phys_of((void *)sp, &ok);
		r->sp_paddr_valid = ok;
		want = min(die_window_words, XR_MAX_DIE_WORDS);
		start = sp - min_t(unsigned long, sp - base,
				     (unsigned long)die_before_words * sizeof(u64));
		for (i = 0; i < want && end - start >= sizeof(u64); i++) {
			r->word_addr[i] = start;
			r->word_overlaps_regs[i] = start < r->regs_end &&
				start + sizeof(u64) > r->regs_base;
			r->word_error[i] = copy_from_kernel_nofault(
				&r->words[i], (void *)start, sizeof(u64));
			if (!r->word_error[i])
				r->word_paddr[i] = xr_phys_of((void *)start,
					&r->word_paddr_valid[i]);
			r->word_count = i + 1;
			start += sizeof(u64);
		}
	}
	/* Readers must not expose the record until every field is complete. */
	atomic_set_release(&die_claimed, XR_DIE_READY);
	xr_die_log(r);
	return NOTIFY_DONE;
}

/* ---- kernel-side pattern test ---- */

static u64 xr_splitmix64(u64 x)
{
	x += 0x9e3779b97f4a7c15ull;
	x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ull;
	x = (x ^ (x >> 27)) * 0x94d049bb133111ebull;
	return x ^ (x >> 31);
}

/* sub < 0 selects a non-walking pattern; otherwise it is the walking bit. */
static u64 xr_kint_value(int kind, int sub, u64 index, u64 vaddr)
{
	switch (kind) {
	case 0:
		return 0;
	case 1:
		return ~0ull;
	case 2:
		return 1ull << (sub & 63);
	case 3:
		return ~(1ull << (sub & 63));
	case 4:
		return vaddr ^ xr_splitmix64(index);
	default:
		return 0;
	}
}

static int xr_kint_sub_count(int kind)
{
	if (kind == 2 || kind == 3)
		return 64;
	return 1;
}

static void xr_kint_note(u64 expected, u64 actual, u64 vaddr)
{
	u64 xr = expected ^ actual;
	int i;
	unsigned long flags;

	spin_lock_irqsave(&kint_lock, flags);
	kint.mismatches++;
	if (!kint.first_bad_vaddr) {
		int ok = 0;

		kint.first_bad_vaddr = vaddr;
		kint.first_bad_value = actual;
		kint.first_bad_expected = expected;
		kint.first_bad_paddr = xr_phys_of((const void *)(unsigned long)vaddr,
						  &ok);
	}
	for (i = 0; i < 64; i++)
		if (xr & BIT_ULL(i))
			kint.bit_hist[i]++;
	spin_unlock_irqrestore(&kint_lock, flags);
}

static u64 xr_kint_deadline_ns;

static bool xr_kint_expired(void)
{
	return xr_expired() ||
	       (xr_kint_deadline_ns && ktime_get_ns() >= xr_kint_deadline_ns);
}

static int xr_kint_thread(void *data)
{
	size_t bytes = (size_t)kint_mib << 20;
	u64 words = bytes / sizeof(u64);
	u64 *buf;
	int kind, sub, pass, ok = 0;
	unsigned long flags;

	if (!words)
		return 0;
	xr_kint_deadline_ns = ktime_get_ns() + (u64)kint_seconds * NSEC_PER_SEC;
	buf = vmalloc(bytes);
	if (!buf) {
		spin_lock_irqsave(&kint_lock, flags);
		kint.ran = -ENOMEM;
		spin_unlock_irqrestore(&kint_lock, flags);
		return 0;
	}
	spin_lock_irqsave(&kint_lock, flags);
	kint.ran = 1;
	kint.buffer_vaddr = (u64)(unsigned long)buf;
	kint.buffer_paddr = xr_phys_of(buf, &ok);
	kint.buffer_paddr_valid = ok;
	spin_unlock_irqrestore(&kint_lock, flags);

	for (pass = 0; pass < 4 && !kthread_should_stop() && !xr_kint_expired();
	     pass++) {
		for (kind = 0; kind < 5 && !kthread_should_stop() &&
		     !xr_kint_expired(); kind++) {
			for (sub = 0; sub < xr_kint_sub_count(kind); sub++) {
				u64 i;

				for (i = 0; i < words; i++) {
					buf[i] = xr_kint_value(kind, sub, i,
							       (u64)(unsigned long)&buf[i]);
					if ((i & 0xffff) == 0 &&
					    (xr_kint_expired() || kthread_should_stop()))
						goto done;
				}
				spin_lock_irqsave(&kint_lock, flags);
				kint.words_filled += words;
				spin_unlock_irqrestore(&kint_lock, flags);
				for (i = 0; i < words; i++) {
					u64 expected = xr_kint_value(kind, sub, i,
						(u64)(unsigned long)&buf[i]);
					u64 actual = READ_ONCE(buf[i]);

					if (actual != expected)
						xr_kint_note(expected, actual,
							     (u64)(unsigned long)&buf[i]);
					if ((i & 0xffff) == 0) {
						if (kthread_should_stop() || xr_kint_expired())
							goto done;
						cond_resched();
					}
				}
				spin_lock_irqsave(&kint_lock, flags);
				kint.words_checked += words;
				kint.sub_passes++;
				spin_unlock_irqrestore(&kint_lock, flags);
			}
		}
	}
done:
	vfree(buf);
	spin_lock_irqsave(&kint_lock, flags);
	kint.completed = !xr_kint_expired() && !kthread_should_stop();
	kint.buffer_vaddr = 0;
	spin_unlock_irqrestore(&kint_lock, flags);
	/* Idle instead of returning. A kthread whose threadfn() exits on its own
	 * has its task_struct released, and xr_exit() would then call
	 * kthread_stop() on freed memory - a slab-use-after-free that the guest
	 * KASAN run caught. Stopping activity at the deadline while keeping the
	 * thread parked preserves the bounded-work guarantee and makes
	 * kthread_stop() unambiguous. */
	while (!kthread_should_stop())
		msleep(200);
	return 0;
}

static void xr_kint_snapshot(struct xr_kint_counters *out)
{
	unsigned long flags;
	spin_lock_irqsave(&kint_lock, flags);
	*out = kint;
	spin_unlock_irqrestore(&kint_lock, flags);
}

/* ---- debugfs reporting ---- */

static int xr_status_show(struct seq_file *s, void *unused)
{
	struct xr_kint_counters snap;
	xr_kint_snapshot(&snap);
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	seq_printf(s, "schema=1 armed=%d deadline_s=%u expired=%d\n",
		   (diecap_enable && !xr_expired() && !atomic_read(&die_claimed)) ? 1 : 0,
		   deadline_s, xr_expired() ? 1 : 0);
	seq_printf(s, "text_start=0x%lx text_end=0x%lx\n", text_start, text_end);
	seq_printf(s, "scan=%d prefix=%s interval_ms=%u max=%u iterations=%llu tasks_seen=%llu candidates=%llu records=%u dropped=%llu\n",
		   scan_enable ? 1 : 0, scan_prefix, scan_interval_ms, scan_max,
		   scan_iterations, scan_tasks_seen, scan_candidates,
		   scan_record_count, scan_dropped);
	seq_printf(s, "diecap=%d events=%llu claimed=%d window_words=%u\n",
		   diecap_enable ? 1 : 0, (u64)atomic64_read(&die_events),
		   atomic_read(&die_claimed), die_window_words);
	seq_printf(s, "kint_mib=%u ran=%d completed=%d sub_passes=%llu words_checked=%llu mismatches=%llu\n",
		   kint_mib, snap.ran, snap.completed, snap.sub_passes,
		   snap.words_checked, snap.mismatches);
	return 0;
}

static int xr_scan_show(struct seq_file *s, void *unused)
{
	unsigned int i;
	unsigned long flags;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	seq_printf(s, "schema=1 iterations=%llu tasks_seen=%llu candidates=%llu records=%u dropped=%llu\n",
		   scan_iterations, scan_tasks_seen, scan_candidates,
		   scan_record_count, scan_dropped);
	for (i = 0; i < scan_record_count; i++) {
		struct xr_scan_record local, *r = &local;

		spin_lock_irqsave(&scan_lock, flags);
		local = scan_records[i];
		spin_unlock_irqrestore(&scan_lock, flags);

		seq_printf(s, "rec=%u stamp=%llu pid=%d comm=%.16s offset=%llu vaddr=0x%llx value=0x%016llx restored=0x%016llx paddr=0x%llx paddr_valid=%d reread1=0x%016llx reread2=0x%016llx stable=%d iteration=%llu\n",
			   i, r->stamp, r->pid, r->comm, r->offset_in_stack,
			   r->vaddr, r->value, r->restored, r->paddr,
			   r->paddr_valid, r->reread1, r->reread2, r->stable,
			   r->iteration);
	}
	return 0;
}

static int xr_die_show(struct seq_file *s, void *unused)
{
	struct xr_die_record *r = &die_record;
	unsigned int i;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (atomic_read_acquire(&die_claimed) != XR_DIE_READY) {
		seq_printf(s, "schema=4 captured=0 events=%llu\n", (u64)atomic64_read(&die_events));
		return 0;
	}
	seq_printf(s, "schema=4 captured=1 events=%llu stamp=%llu pid=%d comm=%.16s\n",
		   (u64)atomic64_read(&die_events), r->stamp, r->pid, r->comm);
	seq_printf(s, "pc=0x%llx lr=0x%llx sp=0x%llx fp=0x%llx pstate=0x%llx\n",
		   r->pc, r->lr, r->sp, r->fp, r->pstate);
	seq_printf(s, "pc_in_text=%d lr_in_text=%d pc_is_candidate=%d lr_is_candidate=%d pc_restored=0x%llx lr_restored=0x%llx\n",
		   r->pc_in_text, r->lr_in_text, r->pc_is_candidate,
		   r->lr_is_candidate, r->pc_restored, r->lr_restored);
	seq_printf(s, "stack_base=0x%llx stack_end=0x%llx sp_in_stack=%d\n",
		   r->stack_base, r->stack_end, r->sp_in_stack);
	seq_printf(s, "sp_paddr=0x%llx sp_paddr_valid=%d word_count=%u\n",
		   r->sp_paddr, r->sp_paddr_valid, r->word_count);
	for (i = 0; i < r->word_count; i++)
		seq_printf(s, "word[%u] addr=0x%llx value=0x%016llx error=%d paddr=0x%llx paddr_valid=%d regs_overlap=%d candidate=%d in_text=%d\n",
			   i, r->word_addr[i], r->words[i], r->word_error[i],
			   r->word_paddr[i], r->word_paddr_valid[i], r->word_overlaps_regs[i],
			   (!r->word_error[i] && xr_is_candidate(r->words[i])) ? 1 : 0,
			   (!r->word_error[i] && xr_in_text(r->words[i])) ? 1 : 0);
	return 0;
}

static int xr_kint_show(struct seq_file *s, void *unused)
{
	int i;
	struct xr_kint_counters snap;
	xr_kint_snapshot(&snap);

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	seq_printf(s, "schema=1 mib=%u ran=%d completed=%d sub_passes=%llu words_filled=%llu words_checked=%llu mismatches=%llu\n",
		   kint_mib, snap.ran, snap.completed, snap.sub_passes,
		   snap.words_filled, snap.words_checked, snap.mismatches);
	seq_printf(s, "buffer_vaddr=0x%llx buffer_paddr=0x%llx buffer_paddr_valid=%d\n",
		   snap.buffer_vaddr, snap.buffer_paddr, snap.buffer_paddr_valid);
	if (snap.first_bad_vaddr)
		seq_printf(s, "first_bad vaddr=0x%llx expected=0x%016llx actual=0x%016llx paddr=0x%llx\n",
			   snap.first_bad_vaddr, snap.first_bad_expected,
			   snap.first_bad_value, snap.first_bad_paddr);
	seq_printf(s, "bit_hist=");
	for (i = 0; i < 64; i++)
		seq_printf(s, "%s%d:%llu", i ? "," : "", i, snap.bit_hist[i]);
	seq_printf(s, "\n");
	return 0;
}

static int xr_open_status(struct inode *inode, struct file *file)
{
	return single_open(file, xr_status_show, NULL);
}

static int xr_open_scan(struct inode *inode, struct file *file)
{
	return single_open(file, xr_scan_show, NULL);
}

static int xr_open_die(struct inode *inode, struct file *file)
{
	return single_open(file, xr_die_show, NULL);
}

static int xr_open_kint(struct inode *inode, struct file *file)
{
	return single_open(file, xr_kint_show, NULL);
}

static const struct file_operations xr_status_fops = {
	.owner = THIS_MODULE, .open = xr_open_status, .read = seq_read,
	.llseek = seq_lseek, .release = single_release,
};
static const struct file_operations xr_scan_fops = {
	.owner = THIS_MODULE, .open = xr_open_scan, .read = seq_read,
	.llseek = seq_lseek, .release = single_release,
};
static const struct file_operations xr_die_fops = {
	.owner = THIS_MODULE, .open = xr_open_die, .read = seq_read,
	.llseek = seq_lseek, .release = single_release,
};
static const struct file_operations xr_kint_fops = {
	.owner = THIS_MODULE, .open = xr_open_kint, .read = seq_read,
	.llseek = seq_lseek, .release = single_release,
};

#ifdef XR_IABT_VM
/* Included only in the isolated guest module, never in the ARM artifact. */
#include "xr_iabt_vm_tests.h"
static bool vm_tests;
module_param(vm_tests, bool, 0444);
MODULE_PARM_DESC(vm_tests, "guest-only: run the qualification checks at init");
#endif

/* ---- lifecycle ---- */

static int __init xr_init(void)
{
	int err = -EINVAL;

	if (scan_interval_ms < 20)
		scan_interval_ms = 20;
	if (die_window_words > XR_MAX_DIE_WORDS)
		die_window_words = XR_MAX_DIE_WORDS;
	if (die_before_words >= die_window_words)
		die_before_words = die_window_words ? die_window_words - 1 : 0;
	if (max_records > XR_MAX_RECORDS)
		max_records = XR_MAX_RECORDS;
	if (kint_mib > 128) {
		pr_err("xr_iabt_observer: kint_mib %u exceeds the 128 MiB cap\n",
		       kint_mib);
		return -EINVAL;
	}
	if (!deadline_s) {
		pr_err("xr_iabt_observer: deadline_s must be non-zero\n");
		return -EINVAL;
	}
	if (scan_enable) {
		pr_err("xr_iabt_observer: cross-task scan unavailable: safe stack release is not exported\n");
		return -EOPNOTSUPP;
	}

	if (diecap_enable && !(text_end > text_start && text_start))
		pr_warn("xr_iabt_observer: diecap without a text range cannot classify candidates\n");

	xr_deadline_ns = ktime_get_ns() + (u64)deadline_s * NSEC_PER_SEC;

	xr_dir = debugfs_create_dir("xr_iabt_observer", NULL);
	if (IS_ERR_OR_NULL(xr_dir))
		return xr_dir ? PTR_ERR(xr_dir) : -ENODEV;
	{
		struct dentry *d;
#define XR_FILE(name, ops) do { \
	d = debugfs_create_file(name, 0400, xr_dir, NULL, ops); \
	if (IS_ERR_OR_NULL(d)) { err = d ? PTR_ERR(d) : -ENOMEM; goto out_dir; } \
} while (0)
		XR_FILE("status", &xr_status_fops);
		XR_FILE("scan", &xr_scan_fops);
		XR_FILE("die", &xr_die_fops);
		XR_FILE("kint", &xr_kint_fops);
#undef XR_FILE
	}

#ifdef XR_IABT_VM
	/* Run before arming anything: the checks call the handlers directly, so
	 * a failure leaves nothing to unwind beyond debugfs. */
	if (vm_tests) {
		err = xr_iabt_vm_tests();
		if (err)
			goto out_dir;
	}
#endif


	if (kint_mib) {
		kint_thread = kthread_create(xr_kint_thread, NULL,
					     "xr_iabt_kint");
		if (IS_ERR(kint_thread)) {
			err = PTR_ERR(kint_thread);
			kint_thread = NULL;
			goto out_die;
		}
		get_task_struct(kint_thread);
		wake_up_process(kint_thread);
	}


	if (diecap_enable) {
		xr_die_nb.notifier_call = xr_die_handler;
		xr_die_nb.priority = INT_MAX;
		err = register_die_notifier(&xr_die_nb);
		if (err) {
			pr_err("xr_iabt_observer: register_die_notifier failed %d\n",
			       err);
			goto out_kint;
		}
	}

	pr_info("xr_iabt_observer: armed scan=%d diecap=%d kint=%uMiB deadline=%us text=[0x%lx,0x%lx)\n",
		scan_enable ? 1 : 0, diecap_enable ? 1 : 0, kint_mib,
		deadline_s, text_start, text_end);
	return 0;

out_kint:
	if (kint_thread) {
		kthread_stop(kint_thread);
		put_task_struct(kint_thread);
		kint_thread = NULL;
	}
out_die:
out_dir:
	debugfs_remove_recursive(xr_dir);
	xr_dir = NULL;
	return err;
}

static void __exit xr_exit(void)
{
	if (kint_thread) {
		kthread_stop(kint_thread);
		put_task_struct(kint_thread);
		kint_thread = NULL;
	}
	/* Always unregister on the way out. Skipping this after a capture (an
	 * earlier design) would leave the die chain referencing freed module
	 * code, i.e. a use-after-free on the next oops. A captured fault pins
	 * the module via __module_get instead, so this path only runs when no
	 * fault was claimed. */
	if (diecap_enable)
		unregister_die_notifier(&xr_die_nb);
	debugfs_remove_recursive(xr_dir);
	xr_dir = NULL;
	pr_info("xr_iabt_observer: removed (scan_iterations=%llu candidates=%llu die_events=%llu kint_mismatches=%llu)\n",
		scan_iterations, scan_candidates, (u64)atomic64_read(&die_events), kint.mismatches);
}

module_init(xr_init);
module_exit(xr_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("XR1710G bounded bit63 saved-LR observer; opt-in only");
