/* SPDX-License-Identifier: GPL-2.0-only */
/* Only included in the isolated guest module, never in the ARM artifact. */

#define XR_CHECK(c, label) do { if (!(c)) { \
	pr_err("XR_IABT_TEST_FAIL %s\n", label); goto out_free; \
} pr_info("XR_IABT_TEST_PASS %s\n", label); } while (0)

#define XR_TEST_WORDS 64
#define XR_TEST_BYTES (XR_TEST_WORDS * sizeof(u64))

/* The buffer is vmalloc'd on purpose. On x86_64 the module mapping space is
 * outside VMALLOC_START..VMALLOC_END, so a module static would report
 * paddr_valid=0 here even though the target's VMAP_STACK kernel stacks and the
 * kint buffer resolve fine on arm64. Testing vmalloc'd memory exercises the
 * same mapping class the target actually uses. */
static u64 *xr_test_area;

/* notify_die is not exported, so the registered callback is exercised directly
 * with explicit frames. Registration/unregistration use the real kernel API. */
static int xr_vm_notify(unsigned long event, struct pt_regs *r)
{
	struct die_args args = { .regs = r };

	return xr_die_handler(&xr_die_nb, event, &args);
}

static void xr_vm_set_ip(struct pt_regs *r, u64 v)
{
#ifdef CONFIG_ARM64
	r->pc = v;
#else
	r->ip = v;
#endif
}

static int xr_iabt_vm_tests(void)
{
	unsigned long saved_ts = text_start, saved_te = text_end;
	unsigned int saved_max = max_records;
	u64 saved_deadline = xr_deadline_ns;
	u64 in_text, candidate, below, above, area1;
	struct pt_regs r;
	u64 die_area[64];
	int i, ok = 0, rc = -EINVAL;

	memset(&r, 0, sizeof(r));
	XR_CHECK(text_end > text_start, "text_range_supplied_by_parameter");

	xr_test_area = vmalloc(PAGE_SIZE);
	if (!xr_test_area) {
		pr_err("XR_IABT_TEST_FAIL test_area_allocates\n");
		return -ENOMEM;
	}

	in_text = text_start + 0x100;
	candidate = in_text & ~XR_BIT63;
	below = (text_start - 8) & ~XR_BIT63;
	above = (text_end + 0x1000) & ~XR_BIT63;
	area1 = (u64)(unsigned long)&xr_test_area[1];

	/* --- candidate predicate: the exact recorded signature --- */
	XR_CHECK(xr_in_text(in_text) && !xr_in_text(text_end) &&
			 !xr_is_candidate(in_text),
		 "predicate_rejects_valid_text_address");
	XR_CHECK(xr_is_candidate(candidate),
		 "predicate_accepts_bit63_cleared_text_address");
	XR_CHECK(!xr_is_candidate(below) && !xr_is_candidate(above),
		 "predicate_rejects_addresses_outside_text");
	XR_CHECK(!xr_is_candidate(0) && !xr_is_candidate(0x5a5a5a5a5a5a5a5aULL),
		 "predicate_rejects_non_pointer_words");

	text_end = text_start;
	XR_CHECK(!xr_is_candidate(candidate),
		 "predicate_disabled_when_range_empty");
	text_end = saved_te;

	/* --- scan: detection, exact fields, physical identity --- */
	scan_record_count = 0;
	scan_dropped = 0;
	scan_candidates = 0;
	memset(xr_test_area, 0, XR_TEST_BYTES);
	xr_test_area[5] = candidate;
	xr_test_area[9] = in_text;
	xr_test_area[13] = 0x5a5a5a5a5a5a5a5aULL;
	xr_test_area[17] = below;
	XR_CHECK(xr_scan_range(current, (unsigned long)xr_test_area,
			       XR_TEST_BYTES, 7) == 1 &&
			 scan_record_count == 1 && scan_dropped == 0,
		 "scan_detects_exactly_the_planted_candidate");
	XR_CHECK(scan_records[0].offset_in_stack == 5 * sizeof(u64) &&
			 scan_records[0].value == candidate &&
			 scan_records[0].restored == in_text &&
			 scan_records[0].iteration == 7 &&
			 scan_records[0].pid == current->pid,
		 "scan_record_fields_exact");
	XR_CHECK(scan_records[0].stable == 1, "scan_rereads_are_stable");
	XR_CHECK(scan_records[0].paddr_valid == 1 &&
			 scan_records[0].paddr != 0,
		 "scan_resolves_physical_address");

	/* --- scan: bounded records with an explicit drop counter --- */
	scan_record_count = 0;
	scan_dropped = 0;
	scan_candidates = 0;
	max_records = 2;
	memset(xr_test_area, 0, XR_TEST_BYTES);
	for (i = 0; i < 5; i++)
		xr_test_area[i * 4] = candidate;
	XR_CHECK(xr_scan_range(current, (unsigned long)xr_test_area,
			       XR_TEST_BYTES, 8) == 5 &&
			 scan_record_count == 2 && scan_dropped == 3 &&
			 scan_candidates == 5,
		 "scan_caps_records_and_counts_drops");
	max_records = saved_max;

	/* --- die handler: argument validation before any capture --- */
	atomic_set(&die_claimed, 0);
	atomic64_set(&die_events, 0);
	memset(&die_record, 0, sizeof(die_record));
	XR_CHECK(xr_vm_notify(DIE_OOPS + 1, &r) == NOTIFY_DONE &&
			 !atomic_read(&die_claimed),
		 "die_ignores_non_oops_event");
	XR_CHECK(xr_die_handler(&xr_die_nb, DIE_OOPS, NULL) == NOTIFY_DONE &&
			 !atomic_read(&die_claimed),
		 "die_rejects_null_args");
	{
		struct die_args nullargs = { .regs = NULL };

		XR_CHECK(xr_die_handler(&xr_die_nb, DIE_OOPS, &nullargs) ==
				 NOTIFY_DONE &&
				 !atomic_read(&die_claimed),
			 "die_rejects_null_regs");
	}

	/* --- die handler: capture of the recorded signature --- */
	memset(die_area, 0, sizeof(die_area));
	die_area[15] = candidate; /* SP - 136, the AP47 reconstruction. */
	xr_vm_set_ip(&r, candidate);
	r.sp = (unsigned long)&die_area[32];
	XR_CHECK(xr_vm_notify(DIE_OOPS, &r) == NOTIFY_DONE &&
			 atomic_read(&die_claimed) == XR_DIE_READY,
		 "die_claims_first_fault");
	XR_CHECK(die_record.pc == candidate &&
			 die_record.pc_is_candidate == 1 &&
			 die_record.pc_in_text == 0 &&
			 die_record.pc_restored == in_text,
		 "die_records_bit63_analysis");
	XR_CHECK(die_record.word_count > 0 &&
			 die_record.word_addr[0] ==
				 (u64)(unsigned long)&die_area[8],
		 "die_records_bounded_raw_window");
	XR_CHECK(die_record.sp_paddr_valid == 1 && die_record.sp_paddr != 0,
		 "die_resolves_stack_physical_address");
	XR_CHECK(die_record.pid == current->pid && die_record.comm[0] != 0,
		 "die_records_task_identity");

	xr_vm_set_ip(&r, candidate + 0x40);
	XR_CHECK(xr_vm_notify(DIE_OOPS, &r) == NOTIFY_DONE &&
			 die_record.pc == candidate && atomic64_read(&die_events) == 2,
		 "die_is_first_fault_only_and_counts_later_events");

	XR_CHECK(module_refcount(THIS_MODULE) > 0,
		 "die_pins_module_so_notifier_cannot_be_unloaded");


	{
		bool found = false;
		for (i = 0; i < die_record.word_count; i++)
			if (die_record.word_addr[i] == (u64)(unsigned long)&die_area[15] &&
			    !die_record.word_error[i] && die_record.words[i] == candidate &&
			    die_record.word_paddr_valid[i]) found = true;
		XR_CHECK(found, "die_captures_sp_minus_136_and_physical_identity");
	}
	module_put(THIS_MODULE);
	atomic_set(&die_claimed, 0);
	xr_deadline_ns = 1;
	xr_vm_notify(DIE_OOPS, &r);
	XR_CHECK(!atomic_read(&die_claimed), "die_rejects_event_after_deadline");
	xr_deadline_ns = saved_deadline;

	/* Corrupt SP must never turn the die notifier into a second fault. */
	{
		unsigned long invalid[] = { 0, ~0UL, VMALLOC_START + PAGE_SIZE };
		for (i = 0; i < ARRAY_SIZE(invalid); i++) {
			r.sp = invalid[i];
			xr_vm_notify(DIE_OOPS, &r);
			XR_CHECK(atomic_read(&die_claimed) == XR_DIE_READY &&
				 !die_record.sp_in_stack && !die_record.word_count &&
				 !die_record.sp_paddr_valid, "die_rejects_invalid_sp_without_read");
			module_put(THIS_MODULE);
			atomic_set(&die_claimed, 0);
		}
	}
	{
		unsigned long base = (unsigned long)task_stack_page(current);
		unsigned long edge[] = {base, base + THREAD_SIZE - sizeof(u64)};
		int e;
		for (e = 0; e < ARRAY_SIZE(edge); e++) {
			r.sp = edge[e];
			xr_vm_notify(DIE_OOPS, &r);
			XR_CHECK(die_record.sp_in_stack && die_record.word_count,
				 "die_accepts_stack_edge");
			for (i = 0; i < die_record.word_count; i++)
				if (die_record.word_addr[i] < base ||
				    die_record.word_addr[i] > base + THREAD_SIZE - sizeof(u64))
					goto out_free;
			pr_info("XR_IABT_TEST_PASS die_window_stays_inside_stack\n");
			module_put(THIS_MODULE);
			atomic_set(&die_claimed, 0);
		}
	}
	{
		u64 word;
		XR_CHECK(copy_from_kernel_nofault(&word, (void *)~0UL, sizeof(word)) != 0,
			 "nofault_read_rejects_unmapped_address");
	}

	{
		static struct xr_die_record probe;
		unsigned long old_pc = qdisc_fault_pc;
		memset(&probe, 0, sizeof(probe));
		qdisc_fault_pc = text_start + 0x100;
		probe.pc = qdisc_fault_pc;
		probe.gpr[19] = (unsigned long)xr_test_area;
		xr_test_area[9] = candidate;
		xr_qdisc_slot(&probe);
		XR_CHECK(probe.slot_attempted && !probe.slot_error1 && !probe.slot_error2 &&
			 probe.slot_value1 == candidate && probe.slot_value2 == candidate &&
			 probe.slot_paddr_valid && probe.slot_addr == (unsigned long)&xr_test_area[9],
			 "pointer_slot_reads_exact_word_twice_and_physical_identity");
		memset(&probe, 0, sizeof(probe));
		probe.pc = qdisc_fault_pc + 4;
		probe.gpr[19] = (unsigned long)xr_test_area;
		xr_qdisc_slot(&probe);
		XR_CHECK(!probe.slot_attempted, "pointer_probe_rejects_other_pc");
		probe.pc = qdisc_fault_pc; probe.gpr[19] = ULONG_MAX;
		xr_qdisc_slot(&probe);
		XR_CHECK(!probe.slot_attempted, "pointer_probe_rejects_overflow");
		probe.gpr[19] = (unsigned long)xr_test_area + 1;
		xr_qdisc_slot(&probe);
		XR_CHECK(!probe.slot_attempted, "pointer_probe_rejects_unaligned");
		qdisc_fault_pc = 0; probe.gpr[19] = (unsigned long)xr_test_area;
		xr_qdisc_slot(&probe);
		XR_CHECK(!probe.slot_attempted, "pointer_probe_default_disabled");
		qdisc_fault_pc = old_pc;
	}

	/* --- kernel-side pattern helpers --- */
	XR_CHECK(xr_kint_value(2, 63, 0, 0) == XR_BIT63 &&
			 xr_kint_value(3, 63, 0, 0) == ~XR_BIT63,
		 "kint_walking_patterns_cover_bit63");
	XR_CHECK(xr_kint_value(4, 0, 3, 0x1000) ==
			 xr_kint_value(4, 0, 3, 0x1000),
		 "kint_address_pattern_is_deterministic");
	memset(&kint, 0, sizeof(kint));
	xr_kint_note(in_text, candidate, area1);
	XR_CHECK(kint.mismatches == 1 && kint.bit_hist[63] == 1 &&
			 kint.bit_hist[62] == 0 &&
			 kint.first_bad_vaddr == area1 &&
			 kint.first_bad_value == candidate &&
			 kint.first_bad_expected == in_text,
		 "kint_histogram_isolates_bit63");

	/* --- physical identity of an independent vmalloc buffer --- */
	{
		void *buf = vmalloc(PAGE_SIZE);
		u64 pa;

		XR_CHECK(buf != NULL, "phys_test_allocates");
		pa = xr_phys_of(buf, &ok);
		XR_CHECK(ok == 1 && pa != 0, "phys_of_resolves_vmalloc_page");
		vfree(buf);
	}

	/* --- deadline --- */
	xr_deadline_ns = 1;
	XR_CHECK(xr_expired(), "deadline_expiry_is_observed");
	xr_deadline_ns = saved_deadline;
	XR_CHECK(!xr_expired(), "deadline_restore_clears_expiry");

	rc = 0;
	pr_info("XR_IABT_VM_OK\n");

out_free:
	/* Guest-only reset: drop the pin and clear the claim so the fixture can
	 * still exercise a clean rmmod. The pin is only released if a claim
	 * actually happened, otherwise the refcount would underflow. The ARM
	 * artifact contains no such reset; on the target a captured fault keeps
	 * the module pinned until reboot. */
	if (atomic_read(&die_claimed))
		module_put(THIS_MODULE);
	atomic_set(&die_claimed, 0);
	text_start = saved_ts;
	text_end = saved_te;
	max_records = saved_max;
	xr_deadline_ns = saved_deadline;
	if (xr_test_area) {
		memset(xr_test_area, 0, XR_TEST_BYTES);
		vfree(xr_test_area);
		xr_test_area = NULL;
	}
	return rc;
}
