/* Only included in the isolated guest module, never in the ARM artifact. */
#define XR_CHECK(c, label) do { if (!(c)) { \
	pr_err("XR_MAPLE_TEST_FAIL %s\n", label); return -EINVAL; \
} pr_info("XR_MAPLE_TEST_PASS %s\n", label); } while (0)

static void xr_vm_reset(void)
{
	xr_ready = false;
	atomic_set(&xr_seen, 0);
	memset(&xr_record, 0, sizeof(xr_record));
}

/* notify_die is not exported. Exercise the registered callback with explicit
 * frames; registration/unregistration use the real kernel notifier APIs. */
static int xr_vm_notify(struct pt_regs *r)
{
	struct die_args args = { .regs = r };
	return xr_die(&xr_nb, DIE_OOPS, &args);
}

static int xr_vm_tests(void)
{
	struct ma_state mas = {};
	struct pt_regs r = {};
	struct die_args args = { .regs = &r };
	struct xr_record saved;
	unsigned long good = 0xffffff8001a2a40cUL;
	unsigned long bad = good & ~(1UL << 63);
	unsigned long end = (unsigned long)task_stack_page(current) + THREAD_SIZE;
	int rc;

	r.ip = (unsigned long)mas_empty_area_rev + XR_FAULT_OFFSET;
	r.sp = (unsigned long)&mas;
	r.r15 = (unsigned long)&mas;
	r.ax = bad;
	r.bx = (good & ~255UL) + 8;
	r.cx = (bad & ~255UL) + 8;
	r.cs = 0x10;
	mas.node = (void *)bad;
	XR_CHECK(xr_die(&xr_nb, DIE_OOPS + 1, &args) == NOTIFY_DONE && !xr_ready, "other_event");
	XR_CHECK(xr_die(&xr_nb, DIE_OOPS, NULL) == NOTIFY_DONE && !xr_ready, "null_args");
	args.regs = NULL;
	XR_CHECK(xr_die(&xr_nb, DIE_OOPS, &args) == NOTIFY_DONE && !xr_ready, "null_regs");
	args.regs = &r;
	r.ip++;
	rc = xr_vm_notify(&r);
	XR_CHECK(rc == NOTIFY_DONE && !xr_ready, "other_pc_callback");
	r.ip--;
	r.cs = 0x33;
	rc = xr_vm_notify(&r);
	XR_CHECK(rc == NOTIFY_DONE && !xr_ready, "user_mode_callback");
	r.cs = 0x10;
	rc = xr_vm_notify(&r);
	XR_CHECK(rc == NOTIFY_DONE && xr_ready && xr_record.stack_range_valid &&
		 !xr_record.read_status[0] && !xr_record.read_status[1] &&
		 xr_record.stack_node[0] == bad && xr_record.stack_node[1] == bad,
		 "corrupt_stack_scalar");
	XR_CHECK(r.ax == bad && mas.node == (void *)bad, "no_register_or_memory_repair");
	saved = xr_record;
	mas.node = (void *)good;
	xr_vm_notify(&r);
	XR_CHECK(!memcmp(&saved, &xr_record, sizeof(saved)), "first_fault_retained");
	xr_vm_reset();
	xr_vm_notify(&r);
	XR_CHECK(xr_record.frame.node_reg == bad && xr_record.stack_node[0] == good &&
		 !xr_record.read_status[0], "register_stack_disagreement");
	xr_vm_reset();
	r.r15 = 0;
	xr_vm_notify(&r);
	XR_CHECK(xr_ready && !xr_record.stack_range_valid && xr_record.read_status[0] == -ERANGE,
		 "null_mas_no_read");
	xr_vm_reset();
	r.r15 = (unsigned long)&mas & ~(1UL << 63);
	xr_vm_notify(&r);
	XR_CHECK(!xr_record.stack_range_valid && xr_record.read_status[0] == -ERANGE,
		 "noncanonical_mas_no_read");
	xr_vm_reset();
	r.r15 = end - sizeof(struct ma_state) + 8;
	xr_vm_notify(&r);
	XR_CHECK(!xr_record.stack_range_valid && xr_record.read_status[0] == -ERANGE,
		 "stack_end_no_read");
	xr_vm_reset();
	r.r15 = (unsigned long)&mas + 1;
	xr_vm_notify(&r);
	XR_CHECK(!xr_record.stack_range_valid, "unaligned_no_read");
	xr_vm_reset();
	r.r15 = (unsigned long)&mas;
	r.sp = end;
	xr_vm_notify(&r);
	XR_CHECK(!xr_record.stack_range_valid, "bad_sp_no_read");
	xr_vm_reset();
	pr_info("XR_MAPLE_TEST_ALL_PASS\n");
	return 0;
}
