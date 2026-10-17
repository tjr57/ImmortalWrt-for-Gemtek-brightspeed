"""Save bounded evidence and tracked diagnostic sources; no device operations."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil
import subprocess

W = Path('/mnt/d/ChatGPT/XR1710G')
R = Path('/home/xrdev/projects/xr1710g/openwrt')
O = W/'development/ap24/maple-observer'
j = lambda p: json.loads(p.read_text())
build = j(O/'result-latest.json')
live = j(O/'live-baseline2/result.json')
replay = j(W/'development/ap24/maple-binary/replay-result.json')
assert build['passed'] and live['passed'] and len(replay['matches']) == 25
report = {'at': datetime.now().astimezone().isoformat(), 'goalComplete': False,
          'phase': 'Maple fault hypothesis narrowed; passive observer qualified and removed from both APs',
          'historicalTXFREECauseProvenAndFixed': True, 'separateMapleCauseProven': False,
          'oldBinaryAll400InstructionsMatched': True, 'replayCases': 123,
          'matchingInjectionBoundaries': 25,
          'replayLimits': replay['assumptions'], 'vmCases': build['vmCasesPassed'],
          'moduleSHA256': build['moduleSHA256'], 'live': live,
          'newFinding': 'AP2 closes users BSS on a single gateway ICMP miss; two close/reopen pairs logged with NPU disabled. Transient probe failure versus true gateway outage not distinguished by old scalar log.',
          'next': ['Fix users-gate failure debounce, preserve open gate on recovery of isolated misses; test and deploy AP2 then AP1.',
                   'Integrate passive Maple observer into a separately qualified bounded NPU boot trial.'],
          'noNewNpuEpochOrFirmwareFlashThisPhase': True}
(O/'progress.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
summary = '''Maple 故障定位与采集点（2026-10-10）

历史 TXFREE 启动预填充缺陷已在 AP24 修复并完成因果验证，证据仍以
development/ap24/prefill-probe/final-result.json 为准。

本轮从 AP18-r2 冻结镜像恢复实际 ARM64 指令，400 条函数指令与旧记录
全部吻合。123 个合成树场景中，栈节点指针被清除最高位（14 个时点）
或 x9 寄存器被清除最高位（11 个时点）均可复现 x0–x29、SP、LR、NZCV、
故障地址和 PC。场景使用合成内存，不是实机内存转储，也不能据此确定
真实写入者、DMA、缓存、物理内存故障或唯一执行路径。

已实现被动 xr_maple_observer：只匹配 AP24 函数的完整机器码和故障位置，
在 die notifier 中读取当前任务栈内一个节点地址两次；不跟随坏指针，
不修复寄存器/内存，不改变异常处理返回值。仅保留首次标量记录。
14 项 KASAN Linux VM 回调/边界/生命周期测试通过；ARM 模块 -j12 编译
及 ABI 校验通过；先 AP2 后 AP1 实机加载、空记录读取、卸载均成功。
VM 使用合成寄存器直接调用回调；未模拟 ARM 异常或 NPU 硬件。

第一次 AP2 验证因设备缺少 stat 命令而失败，模块已清理，失败记录保留。
使用设备现有 ls 校验权限后，新一轮完整验证通过。两台启动 ID 和配置
哈希保持一致，模块和临时文件均已移除，NPU 仍关闭；本轮未刷机。

另外发现：AP2 上联守护在一次网关 ping 失败后立即关闭 Tizer，日志中
出现两次短暂关开。下一步先修复失联防抖和孤立丢包后的保持开启行为，
再继续采集器的限时启动集成。Maple 根因仍未确定，目标保持进行中。
'''
(O/'Maple定位与采集验证.txt').write_text(summary)
dst = R/'scripts/xr1710g/maple-observer'
dst.mkdir(exist_ok=True)
for p in (O/'src').iterdir():
    shutil.copy2(p, dst/p.name)
scripts = ('extract-ap18-maple-binary.py', 'replay-ap18-maple-binary.py',
           'qualify-maple-observer.py', 'test-maple-observer-live.py',
           'record-maple-observer-progress.py')
for name in scripts:
    shutil.copy2(W/'environment'/name, dst/name)
(dst/'README.txt').write_text(summary)
g = j(W/'development/current-goal.json')
g['latestMapleEvidence'] = 'development/ap24/maple-observer/progress.json'
g['currentNpuConclusion']['MapleOops'] = '123 frozen-binary replay scenarios narrow stack/register hypotheses; qualified passive observer available; physical cause still unknown.'
g['nextConcreteRepair'] = 'AP2 users BSS gate flaps on a single gateway ICMP miss; debounce failure and retain open gate on isolated recovery.'
(W/'development/current-goal.json').write_text(json.dumps(g, ensure_ascii=False, indent=2)+'\n')
agents = R/'AGENTS.md'
old = agents.read_text()
marker = '<!-- ap24-maple-observer-current:start -->'
assert marker not in old
block = '''<!-- ap24-maple-observer-current:start -->
## Maple observer qualified; newly observed users-gate flapping is next

- Latest: development/ap24/maple-observer/progress.json. Frozen AP18-r2
  binary 400 instructions matched;123 synthetic single-bit scenarios,
  25 boundaries reproduce all saved registers+SP/LR/NZCV/PC/address.
  Stack-node and x9-register hypotheses both fit; NOT a physical root proof.
- Passive die-notifier module 64181b840d34a4ae006dbf32bb4418c8ddc8da521a9a4ad4e3f8e75c9a0e1d8f
  bound to full AP24 Maple machine code,14 real KASAN guest callback cases,
  ARM ABI/build passed. AP2 thenAP1 load/read/unload passed; no NPU activation,
  reboot or flash. Both original AP24 boots/config remain intact; module removed.
  First attempt lacked stat, cleaned; full live-baseline2 passed. Do not rerun.
- New live AP2 log shows two gateway-unreachable down/up BSS pairs; source
  xr1710g-ap-uplink-guard closes on one ICMP miss. No NPU/Maple fault here.
  Next repair: debounce soft ping failure and retain already-open gate after
  isolated recovery; retain immediate close on invalid configuration/hold.
  Then integrate observer into newly qualified bounded NPU startup. Do not
  repeat completed prefill probes, or declare Maple/full NPU qualified.
<!-- ap24-maple-observer-current:end -->

'''
agents.write_text(old.replace('# XR1710G development context\n', '# XR1710G development context\n\n'+block, 1))
subprocess.run(['git', 'add', '--', 'scripts/xr1710g/maple-observer', 'AGENTS.md'], cwd=R, check=True)
subprocess.run(['git', '-c', 'core.whitespace=cr-at-eol', 'diff', '--cached', '--check'], cwd=R, check=True)
print(json.dumps(report, ensure_ascii=False))
