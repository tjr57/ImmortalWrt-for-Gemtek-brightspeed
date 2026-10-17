# xr-mem-integrity：受限用户态内存完整性模式测试器

## 为什么存在

本目标机上两次独立的内核 IABT 故障具有同一签名：

| | AP44（2026-10-11 19:33） | AP47（2026-10-12 21:43） |
|---|---|---|
| 任务 / CPU | `modprobe` / CPU3 | `napi/phy0-0` / CPU1 |
| 被破坏的字 | 内层 `do_dentry_open` 的 saved LR | `dequeue_entities` 的 saved LR |
| 应有值 | `vfs_open+0x28` = `0xffffffc080217368` | `dequeue_task_fair+0x88` = `0xffffffc08007c968` |
| 实测值 | `0x7fffffc080217368` | `0x7fffffc08007c968` |
| 差异 | 恰好清 bit63 | 恰好清 bit63 |
| 同一条 `ldp` 载入的 saved fp | 正确 | 正确 |

两次都是"帧记录里的 saved-LR 槽被以恰好清 bit63 的方式读回，故障发生在消费它的尾声 `ret`"。
本工具是该签名的**过滤器**：它报告 64 位字读回时是否有单个比特错误、哪些比特位不同、
错误是**持久**（存进去的值真的错了）还是**瞬态**（立即重读又得到期望值），以及在
pagemap 可用时的物理地址。

## 能得出什么、不能得出什么

可判读：

- 同一比特索引出现在**许多不同地址** → 数据线 / 字节通道 / 数据通路类系统性机制。
- 同一地址反复出错 → 单元级缺陷。
- 分类为 **transient**（重读即恢复） → 指向读取通路 / 缓存 / 时序，而不是持久存储错误。
- 分类为 **persistent** → 写入时或存储介质上就已错误。
- NPU 关闭对照臂与 NPU 开启负载臂的差异 → 是否与 NPU 负载相关。

必须随结果一起引用的局限：

- 只覆盖**本进程的匿名页**；不覆盖 vmapped 内核栈页、内核数据结构、DMA 一致性缓冲或环。
- **阴性结果只削弱、不排除**内存子系统或读取通路机制，也不能排除只在特定指令窗口显现的故障。
- 采样率虽远高于等待罕见栈命中，但两次故障对应的每字错误率极低；运行时长与规模决定检出功率，
  必须记录实际 `wordsChecked` 与 `patternPassesDone`，不能用"跑过了"代替功率说明。
- 这是诊断过滤器，**不是修复，也不是任何验收**。
- 工具本身会产生 DDR 带宽与一个 CPU 的占用；在负载臂中它是额外负载，必须记录在案。

## 用法

```
xr-mem-integrity [--size BYTES] [--seconds N] [--passes N]
                 [--patterns all|zero,ones,walk-one,walk-zero,alt-byte,addr,prng]
                 [--pin CPU] [--ldp] [--retain SECONDS] [--out FILE]
                 [--selftest]
```

- `--size`：测试区字节数，默认 64 MiB。设备上应保守选择，避免挤压转发所需内存。
- `--seconds`：硬截止；到点后停止并把 `completed` 记为 false。
- `--patterns`：`walk-one` / `walk-zero` 各展开 64 个子遍（逐比特），`alt-byte` 2 个子遍，其余 1 个。
  `addr` 用地址派生模式，可发现"写到错误位置"。
- `--ldp`：仅 aarch64。用内联 `ldp` 成对读取，覆盖两次故障所涉及的那一类访问
  （尾声 `ldp x29, x30, [sp], #N`）。
- `--retain N`：填充后等待 N 秒再校验，用于区分保持性错误与访问期错误。
- `--pin CPU`：绑定到指定 CPU，避免与负载争用同一核。
- `--out FILE`：结果 JSON 路径；设备上应放 `/tmp`（RAM）。省略则写 stdout。
- `--selftest`：注入已知错误以证明检测、比特索引上报与分类逻辑，不做真实测试。

退出码：`0` 完成并写出结果；`1` 致命错误或自检失败；`2` 用法错误；
`3` 因截止/信号停止（**部分覆盖，不算通过**）。

## 构建与离线资格化

```
sh build.sh [output-dir]        # 默认 /tmp/xr-mem-integrity-qa
```

脚本依次执行，任一步失败则整体退出码非 0：

1. 宿主 `gcc -O2 -Wall -Wextra -Werror -std=gnu11` 构建（证明可移植逻辑）。
2. 宿主 `--selftest`。
3. 宿主短跑（8 MiB，30 秒截止，5 种模式）。
4. root 下的 pagemap 物理地址路径（非 root 时打印 SKIP，不算通过）。
5. 用项目交叉工具链构建**静态** aarch64 二进制并 strip。
6. `qemu-aarch64-static` 下运行 ARM `--selftest`，**这是唯一能离线覆盖 `--ldp` 路径的方式**。
7. 记录源码与二进制 SHA256。

## 已完成的资格化（2026-10-13）

- 宿主自检 7/7 通过；`-Wall -Wextra -Werror` 无警告。
- ARM 静态二进制在 `qemu-aarch64-static` 下自检 `allPassed: true`，
  其中 `detect-via-ldp-pair` 报 `pairs=2048 expected=2048 mismatches=1`。
- 宿主短跑：71,303,168 字校验、68 个模式遍、0 失配、`completed: true`。
- root 短跑：`pagemapPfnAvailable: true`、`bufferPaddrFirst` 非零、34,603,008 字、0 失配。
- 自检抓到并修复了两个真实缺陷：
  1. `--ldp` 分支每次只前进 1 个字，导致配对重叠（`pairs=4095` 而非 2048，同一字被重复计数）。
     修复后断言收紧为必须等于 `words/2`，使该类缺陷此后会被显式抓住。
  2. `pagemapPfnAvailable` 在首次 `phys_of()` 成功之前就被打印，清洁运行下恒为 false，
     会让读者误判"设备上取不到物理地址"。改为启动时主动探测一次并保留结果。
- WSL2 宿主 0 失配是预期结果，只证明工具不误报，**不代表目标机内存状况**。

## 目标机实测限制（2026-10-13 arm A 对照臂实测）

- **`/proc/self/pagemap` 在目标机上不存在**（内核未开 `CONFIG_PROC_PAGE_MONITOR`），
  运行时 stderr 报 `warning: pagemap unavailable`，结果里 `pagemapPfnAvailable=false`、
  所有 `paddr` 为 0。因此**用户态无法取得物理地址**，物理地址相关的判读
  （单元级 vs 数据线级、bank/row 聚集）在本工具上不可用；需要物理地址时必须走内核模块。
  宿主 WSL2 上 root 可用 pagemap，这一差异使宿主资格化**不能代表**目标机的物理地址能力。
- 其余目标机行为已实测：4 个 CPU；`mlock` 64 MiB 成功；`/tmp`（tmpfs）余量约 933 MB；
  BusyBox 无 `nproc`、无 `getconf`，CPU 数需读 `/proc/cpuinfo`；`sha256sum` 在 `/usr/bin/sha256sum`。
- 实测吞吐：单核绑核 240 秒完成 7,247,757,312 次 64 位字校验
  （约 3.0e7 字/秒），其中 3,623,878,656 次成对 `ldp`。规划设备运行时应按此量级估算功率，
  不要按桌面机带宽估计。

## 未覆盖

- vmapped 内核栈页（两次故障实际发生的位置）、内核数据结构、DMA 一致性或环缓冲：
  本工具**不覆盖**，需要内核模块（MA/MB/INT-kernel）才能覆盖。
- 与 NPU 上行负载并发时的表现（arm A 为 NPU/PPE 关闭的对照臂，不含该条件）。
- 物理地址维度的判读（见上）。


## 设备运行边界

任何在 AP 上的运行都是设备操作，需要用户单独批准，并且必须：限时、限量、
结果写 `/tmp`、有独立恢复路径、记录当时版本/boot ID/NPU 与 PPE 状态/负载条件。
不得把本工具的输出当作修复、收益或收官证据。
