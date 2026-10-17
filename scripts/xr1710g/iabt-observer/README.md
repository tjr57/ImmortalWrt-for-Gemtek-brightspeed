# IABT observer — current supported scope

The latest reviewed module rejects `scan_enable=1` with `EOPNOTSUPP`. The deployed
kernel does not export `put_task_stack`; RCU-only raw scanning of other tasks'
VMAP_STACK pages is unsafe. Do not use earlier scan recipes.

`diecap_enable=1` captures the first DIE_OOPS before `deadline_s`: register values
and a bounded current-task-stack window (default 24 words before SP, 48 total).
Invalid SP and per-word nofault read failures are explicit. Completed records
are release/acquire published; the callback pins a live module until reboot.
The notifier is installed only after fallible worker initialization completes.

`kint_mib` checks only a private vmalloc buffer, with a synchronized snapshot,
independent duration and module deadline. It never writes driver rings.

Text bounds must come from the correct deployed ELF, with a `0x` prefix. No
observer covers NPU faults before it is loaded. A copied stack window is not
proof of a corruption writer or of the original stored LR value. ARM builds
alone are not ARM runtime validation. Production defaults remain disabled.

Windows evidence: development/ap47/npu-iabt-observer-review-20261013/RESULT.txt.
Do not replay old trial scripts. The old source/QA remains historical evidence.
