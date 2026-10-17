XR1710G 独立持久化内核日志记录器（诊断用，默认不自启）

用法：xr-persist-log NEW_ABSOLUTE_DIRECTORY SECONDS [--daemon]
SECONDS限定1..600；输出目录必须不存在，父目录必须已存在且不经符号链接。
--daemon建立新会话并忽略SIGHUP，只有首个持久化提交成功才向启动进程返回成功；SSH退出后继续运行。生产二进制固定只读/dev/kmsg，不接受替换输入环境变量。

不等崩溃触发：连续追加kernel.kmsg，每2秒或64KiB执行fdatasync，再追加并同步带CRC32/字节范围/序号/单调时间/bootID的commits.jsonl。错误标记及观察模块尾标记会提前提交。日志上限1MiB、提交上限512条，无循环覆盖旧记录；限时结束写closed.json。程序不操作NPU、驱动、网络配置或重启，不会自动扩展运行时限。

恢复后读：python3 read_log.py 保存目录。读取器仅接受校验通过的已提交前缀，忽略未完整提交尾部；没有closed不等于已证明内核崩溃。

资格化：20项宿主/ARM模拟检查；强制终止VM并重启同一磁盘后，346条记录完整读回；AP1在NPU关闭时实测脱离SSH运行30秒，378条/16提交，配置与boot不变。
旧采集器是识别到故障才持久化，而新程序预先写盘，因此硬复位后仍可能保留故障前最后批次。CPU/存储完全停机时任何用户态进程都无法继续写入。2秒未提交尾部仍可能丢失。VM ext4测试不是物理SPI-NAND断电保证。

源码/验证入口：D:/ChatGPT/XR1710G/development/npu-iabt-repair/persistent-recorder/。
ARM产物及SHA读result.json。本项目只用限时诊断，避免常年额外闪存写入。未安装开机服务。
当前仍处于用户规定第1阶段：下轮NPU诊断采用本程序；若失败才版本对照，最后串口。
