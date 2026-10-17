/* Offline-only candidate: preserve the original TXFREE producer handoff.
 * The live data alias visibility and deployment integration are NOT
 * qualified. This object must not be installed on a router.
 */
.option norvc
.option norelax
.section .text
.global xr_trace_entry
.extern xr_trace_storage
.extern xr_trace_return
xr_trace_entry:
    /* Original instruction displaced at live PC 0x8400b162. */
    lw s9, 0(a4)
    addi sp, sp, -32
    sw t0, 0(sp)
    sw t1, 4(sp)
    sw t2, 8(sp)
    sw t3, 12(sp)
    sw t4, 16(sp)
    sw t5, 20(sp)
    sw t6, 24(sp)
    srli t0, s9, 27
    li t1, 6
    bne t0, t1, .Lreturn
    csrr t1, mhartid
    li t2, 8
    bgeu t1, t2, .Lreturn
    /* Per-hart storage plus bounded local interrupt masking prevents a
     * same-hart interrupt from reserving the same record. No spin/wait. */
    csrrci t6, mstatus, 8
    sw t6, 28(sp)
    lui t0, %hi(xr_trace_storage)
    addi t0, t0, %lo(xr_trace_storage)
    slli t2, t1, 11 /* independent 2048-byte area for each of 8 harts */
    add t0, t0, t2
    lw t2, 12(t0)
    bne t2, t1, .Lirq_restore
    lw t2, 4(t0)
    li t3, 0x32505258
    bne t2, t3, .Lirq_restore
    lw t2, 8(t0)
    li t3, 32
    bne t2, t3, .Lirq_restore
    lw t1, 0(t0)
    li t2, 32
    bgeu t1, t2, .Lirq_restore
    slli t2, t1, 1
    add t2, t2, t1
    slli t2, t2, 4 /* 48-byte records */
    addi t2, t2, 16
    add t2, t0, t2
    lw t3, 36(sp) /* original worker saved control, before ring rearm */
    lw t4, 4(s1) /* second observation, explicitly not atomic */
    lw t5, 0(s1) /* Wi-Fi descriptor buffer address, not packet contents */
    sw s2, 0(t2)
    sw t3, 4(t2)
    sw t4, 8(t2)
    sw s9, 12(t2)
    slli t3, t3, 2
    srli t3, t3, 18
    li t4, 8
    li t6, -1
    bltu t3, t4, .Lversion_done
    lw t6, 4(a4)
    srli t6, t6, 16
    andi t6, t6, 7
.Lversion_done:
    sw t6, 16(t2)
    sw a4, 20(t2)
    sw t5, 24(t2)
    /* Same pool word through the firmware's alternate 0x4... view.
     * Do not infer real coherency from the coherent instruction fixture. */
    lui t3, 0x40000
    addi t4, t3, -1
    and t4, a4, t4
    or t4, t4, t3
    lw t6, 0(t4)
    sw t6, 28(t2)
    sw s1, 32(t2)
    lw t5, 8(s1)
    sw t5, 36(t2)
    sw zero, 40(t2)
    addi t1, t1, 1
    fence rw, rw
    sw t1, 44(t2) /* per-record commit sequence is published last */
    fence rw, rw
    sw t1, 0(t0)
.Lirq_restore:
    lw t6, 28(sp)
    andi t6, t6, 8
    csrs mstatus, t6
.Lreturn:
    lw t0, 0(sp)
    lw t1, 4(sp)
    lw t2, 8(sp)
    lw t3, 12(sp)
    lw t4, 16(sp)
    lw t5, 20(sp)
    lw t6, 24(sp)
    addi sp, sp, 32
    j xr_trace_return
