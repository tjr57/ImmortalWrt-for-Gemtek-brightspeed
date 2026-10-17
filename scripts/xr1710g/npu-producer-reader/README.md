# 固定 NPU 生产端标量读取器

该可选模块没有自动加载、NPU 控制、写寄存器或任意地址参数。只允许 root/CAP_SYS_RAWIO，验证设备型号、绑定驱动、固定 MMIO 资源及 DT no-map 非 reusable 保留区。锁定设备生命周期后使用与原驱动相同类型的映射，只读固定候选指令指纹和已提交的标量记录。

逐条提交序号前后核对，检查 hart、magic、容量、保留字和单调计数；旧 blob 返回 ENOEXEC，未提交或变化记录返回 EAGAIN，无效表头返回 EBADMSG。输出明确标记非原子采样。256 条文本记录超过 16 KiB，调用方需独立限时且至少提供 64 KiB 预算，并检查 complete/failed/capped 或缺少尾标志。

27 项真实 KASAN/lockdep VM 结果见 vm/result-latest.json。虚拟机仅替代 OF 身份/保留区发现及物理读取传输，实际读者验证逻辑不变。arm/result-latest.json 绑定生产内核 ABI 和源码。live-baseline/result.json 记录 AP1 原 blob 的预期拒绝及完整清理，不能解读为候选执行验收。原一次性 baseline 脚本不得重跑。
