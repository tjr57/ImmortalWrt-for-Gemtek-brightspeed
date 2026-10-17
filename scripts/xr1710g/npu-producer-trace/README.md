# NPU 原始 TXFREE 交接观察原型：尚未部署

当前候选 `b48d5e6e4725adfc3560b25aeb9aa00a01134e2a0b9ae84ac2313fe5c32bc298` 仅供开发验证，不是故障修复镜像。原 NPU 固件及已部署 AP23 保持原样。历史 TXFREE 截断与独立 Maple Oops 的根因仍未证明。

实际运行寄存器与原启动指令确认执行基址为 `0x84000000`，GP 为 `0x3e9013a8`。原型在 `0x8400b162` 重放被替换的 `lw s9,0(a4)`，跳往偏移 `0x40000` 的 332 字节观察代码，再返回 `0x8400b166`。记录区偏移为 `0x41000`，NPU 写入视图为 `0x44041000`。旧候选 c622e07c… 的偏移 `0x20000/0x21000` 与原 hart0 栈重叠，已拒绝并归档于 `rejected-stack-overlap-v1`，从未部署。

八个 hart 各有 2048 字节区域，最多保存 32 条、每条 48 字节。记录包括队列索引、两次 control、原 8… 视图的首字、长度至少为 8 时的版本、缓冲区与描述符地址、4… 视图的同一首字、buf1、保留字和提交序号。不采集 token、MAC、密钥或用户数据。写入时暂时关闭本 hart 的 MIE，并恢复原值；不使用跨核锁。两种视图的实际缓存语义尚未证明。

`test.json` 绑定候选、汇编、模型和测试哈希，覆盖长度边界、GPR、容量、非 TXFREE、hart 分区、无效表头和 MIE 恢复。交接前与交接后的人为首字变化能产生相同 Linux 输出，原型保留不同交接信息；这只是观察位置的有效性测试。

`startup-layout.json` 执行八核冷/暖入口共 16 个案例，原栈最高端为偏移 `0x3de00`。`startup-path.json` 对原固件和候选分别执行八核默认关闭启动路径，寄存器与 SRAM 结果一致，附加区未写入。锁、计时、UART 与 MMIO 使用明确的单线程模型；不是 SoC 启动验收。`../npu-buffer-lifetime/result.json` 执行原分配/释放代码与延迟 DMA，在 520 次环回中保持源缓冲区至 DMA 完成。拥塞时丢通知路径不解释已见的空闲队列初始故障。

`0xfc298073` 编码匹配 SiFive CDISCARD.D.L1 s3；[原作者 binutils 补丁](https://sourceware.org/pipermail/binutils/2021-September/118032.html) 提供编码依据，不能据此证明 AN7581 缓存语义。

只读 Linux 观察器在 `../npu-producer-reader`。27 项真实 KASAN/lockdep 内核 VM 检查与生产 ARM ABI 编译通过；AP1 原固件预期以 ENOEXEC 拒绝读取，临时模块已清除。这不证明候选运行或缓存可见性。最多 256 条文字记录超过旧 16 KiB 快照预算，因此 recovery5 使用独立 2 秒、64 KiB 子进程；其集成证据单独记录。

NPU 驱动内建，普通启动在 overlay 挂载和 S08 之前已经装入 ROM 固件，S08 设置 firmware_class.path 不能替换此次早期加载。尚无新生产镜像。用户离家，AP2 已在大厅、仅有 Mesh；不进行新的 NPU 激活或 AP2 故意断链测试。剩余门槛见 `progress.json`，旧一次性实机脚本不得重跑。
