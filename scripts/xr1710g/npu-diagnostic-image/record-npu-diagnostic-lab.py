"""Record the completed offline integration and its physical evidence blocker."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--goal-status', choices=('active','blocked'), required=True)
a = p.parse_args()
w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
out = w/'development/npu-diagnostic-lab'
read = lambda path: json.loads(path.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
image = read(out/'result.json')
startup = read(out/'packed-startup.json')
assert image['passed'] and startup['passed'] and len(startup['checks']) == 14
assert sha(Path(image['artifact'])) == image['artifactSHA256'] == startup['artifactSHA256']
assert sha(out/'result.json') == startup['assemblyReportSHA256']
assert all(sha(Path(path)) == expected for path, expected in image['productionInputsUnchanged'].items())
assert not image['hardwareDeployable'] and not startup['hardwareDeployable']
hall = read(w/'development/resumed-hall/latest.json')
assert hall['passed'] and hall['ownerAway']
previous = [w/'development/npu-recovery5/progress.json',w/'development/npu-activation3/progress.json']
assert read(previous[0])['AP2IndependentRecovery'] is False
assert read(previous[1])['AP2IndependentRecoveryAvailable'] is False
report = {
    'at':datetime.now().astimezone().isoformat(), 'passed':True,
    'goalStatus':a.goal_status, 'goalComplete':False,
    'progress':'Private diagnostic FIT assembly, complete rootfs round-trip and packed ARM startup verification',
    'artifactSHA256':image['artifactSHA256'], 'artifactBytes':image['artifactBytes'],
    'rootfsEntriesVerified':image['rootfsFilesVerified'], 'changedPaths':len(image['changedFiles']),
    'productionKernelDtbModulesUnchanged':True, 'productionConfigAndAP23Unchanged':True,
    'packedArmStartupChecks':14, 'matchingPriorRealKernelCases':{'recovery':18,'activation':19},
    'maxParallelJobs':12, 'fullMakeWorldRun':False,
    'diagnosticPackagesAlreadyCompiledJobs12':True,
    'normalUpgradeRelease':False, 'hardwareDeployable':False,
    'actualNpuActivated':False, 'APRebootedOrFlashed':False,
    'APConfigurationChanged':False, 'phoneTested':False,
    'mainSwitchPCNetworkOriginalDebianChanged':False,
    'historicalTXFREERootCauseFixed':False, 'historicalMapleRootCauseFixed':False,
    'latestReadOnlyHealth':'development/resumed-hall/latest.json',
    'bothHealthyAP23':True, 'AP2IndependentRecoveryAvailable':False,
    'blockingConditionRepeatedAcrossAtLeastThreeConsecutiveContinuations':True,
    'previousContinuations':[{ 'path':str(path.relative_to(w)), 'sha256':sha(path)} for path in previous],
    'blocker':'Owner away, AP2 hall Mesh-only. Remaining decisive data requires real producer/NPU execution; no confirmed independent recovery for an early-firmware failure.',
    'whyOfflineTestsCannotFinishGoal':[
        'Actual cache alias visibility, source ownership and concurrent producer handoff are absent from software fixtures',
        'NPU firmware executes around 5.9s; overlay/guard comes later, so its reboot deadline cannot protect an early firmware failure',
        'More identical virtual cases cannot supply the missing physical fault record'],
    'resumePrerequisites':[
        'Operator available and verified recovery path for the diagnostic target, including recovery from failure before S08',
        'Restore independent AP2 wire/TTL; do not infer it from ordinary LAN-over-Mesh access',
        'Recheck exact candidate and current health before any new hardware test; do not rerun retired one-shot scripts'],
    'remaining':[
        'Actual diagnostic NPU boot/trace visibility and bounded execution validation',
        'Capture anomalous original Wi-Fi producer handoff; distinguish upstream descriptor, cache/order and reuse',
        'Prove and implement TXFREE root fix; investigate separate Maple Oops',
        'After a real fix: full make -j12, applicable VM checks, preserve-config AP2 then healthy AP1 deployment'],
    'evidence':{'image':'development/npu-diagnostic-lab/result.json',
                'packedStartup':'development/npu-diagnostic-lab/packed-startup.json'},
    'firstAssemblyFailure':'Package inventory .list was correctly rejected as unknown payload; no artifact published. Excluded APK metadata from explicit lab overlay, rebuilt in fresh directory and retained failed fixture.'
}
(out/'progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
note = '''本轮完成：NPU 诊断镜像离线集成

两台 AP 的现网仍为 AP23，最后只读检查的 Tizer/Poro、6GHz Mesh、管理和网关均正常，无新内核报错。本轮没有刷机、重启或启用 NPU。

已生成 ap23-npu-producer-lab1.itb.offline（18530304 字节）。它由已冻结 AP23 的内核/设备树/根文件系统，以及已用 -j12 编译的 recovery5、activation3 和两份观察模块组装；不是新一轮 make world 或正式升级发布。
内核、设备树、现有驱动、配置默认值与 AP23 相同。1619 个根文件系统条目的文件内容、权限、属主、链接、设备号经打包回读核验；修改仅限清单中 14 个路径。
14 项实际打包 ARM 启动入口检查通过：无请求和同次启动不激活，手动 start 不激活，非法/宽权限/符号链接/AP2 请求被拒绝。recovery5 的 18 项及 activation3 的 19 项先前真实内核 VM 结果已与当前源码绑定，未冒充本轮重跑。

本镜像有明确 LAB 标记，没有正式 sysupgrade 元数据，诊断文件是显式覆盖层，未伪造 APK 安装登记。hardwareDeployable=false。不能直接用现有升级脚本部署。

关键限制：替换后的 NPU ROM 代码在约 5.9 秒开始执行，早于 overlay 和 S08 恢复保护。普通重启仍会载入同一诊断 ROM；一次性 mt76 激活标记并不能恢复原 NPU 固件，也不能保护此前发生的故障。用户不在家、AP2 仅 Mesh；这一步需要能处理早期启动失败的独立恢复条件。
原始生产端描述符交接、缓存别名可见性、并发和缓冲区复用仍需实机证据。软件模型不能补出这些观测，历史 TXFREE 与独立 Maple Oops 仍未修复。目标没有完成。

恢复推进时：先确认操作者和诊断目标的恢复方式，再确认 AP2 独立有线或 TTL，重新核对镜像及现网状态。旧的一次性实机脚本均不重跑。真正修复后仍执行 -j12 完整构建、相关 VM 检查、保留配置先 AP2 后 AP1。
详情见本目录 result.json、packed-startup.json、progress.json。
'''
# Derive the path count rather than hard-code it in the human-readable record.
note = note.replace('14 个路径',str(len(image['changedFiles']))+' 个路径')
(out/'离线集成与接续说明.txt').write_text(note,encoding='utf-8')
goal_path = w/'development/current-goal.json'
goal = read(goal_path)
goal['status'] = a.goal_status
goal['physicalRecoveryBlockerResolved'] = False
goal['recoveryRequired']['AP2WiredLinkRestored'] = False
goal['recoveryRequired']['ownerMorningStep'] = 'AP2 现已在大厅、仅 Mesh。现网正常；后续 NPU ROM 诊断需要操作者可用及经过确认的独立恢复条件。'
goal['NpuFinding']['diagnosticImageIntegration'] = report
goal['lastDevelopmentUpdate'] = report
goal['lastInvestigation'] = {'at':report['at'],'topic':'NPU diagnostic image offline integration','evidence':'development/npu-diagnostic-lab/progress.json','rootCauseFixed':False,'firmwareFlashed':False}
goal['goalToolStatusNote'] = a.goal_status+': offline diagnostic integration passed. Remaining producer/cache/root evidence requires physical hardware with independent recovery; neither TXFREE nor Maple root fixed.'
goal['preflashPolicy']['diagnosticImage'] = {'id':image['id'],'artifactSHA256':image['artifactSHA256'],'deploymentHeld':True,'hardwareBootProven':False,'earlyFailureGuardCoverage':False}
goal_path.write_text(json.dumps(goal,ensure_ascii=False,indent=2)+'\n')
dest = r/'scripts/xr1710g/npu-diagnostic-image'
dest.mkdir(exist_ok=True)
for name in ('build-npu-diagnostic-lab.py','test-npu-diagnostic-packed-startup.py','record-npu-diagnostic-lab.py'):
    shutil.copy2(w/'environment'/name,dest/name)
shutil.copy2(out/'离线集成与接续说明.txt',dest/'qualification.txt')
agents = r/'AGENTS.md'
text = agents.read_text()
start,end = '<!-- npu-diagnostic-image-current:start -->','<!-- npu-diagnostic-image-current:end -->'
section = '''<!-- npu-diagnostic-image-current:start -->
## NPU lab FIT integrated offline; physical evidence required (2026-10-10)

- Current goal status: STATUS. Three consecutive resumed continuations recorded
 AP2 hall/Mesh-only/no independent recovery. Offline recovery5, activation3 and
 image integration are now complete. No new physical activation until adequate
 independent recovery is actually available; no repetitive virtual tests can
 establish the missing original hardware handoff/cache/concurrency evidence.
- Both AP23 healthy at14:40 read-only; same boot IDs; no device writes/reboots.
 Private AP23-derived lab FIT dfea625f373ba0fe5eac253b7c8f9535db26da5db344580d0ba019845350f76c,
 18530304 bytes. Kernel/FDT/production modules unchanged;1619 rootfs entries
 round-trip verified;14 packed ARM startup rejection/no-request checks passed.
 Source-bound prior18 recovery +19 activation real-kernel cases still apply.
 No new make world: qualified -j12 package binaries were assembled privately.
- Artifact is NOT a release: .itb.offline, lab marker/banner, no sysupgrade
 metadata, diagnostic overlay is not represented as installed APK packages.
 hardwareDeployable=false. Production source blob/.config/AP23 unchanged.
- ROM candidate executes before S08: one-shot activation marker and userspace
 deadline do NOT protect early NPU firmware failure, and ordinary reboot would
 still load candidate ROM. Need operator and verified early-failure recovery
 for diagnostic target, plus independent AP2 access. Generic VM != SoC proof.
- TXFREE and separate Maple root unproven. Next actual producer capture,
 root repair, relevant validation, full-j12 and AP2->healthy->AP1 deployment.
 Previous ACTIVE/pending-image paragraphs below are historical. Old producer
 recorder now refuses to overwrite this newer state; no retired live scripts.
- Evidence: development/npu-diagnostic-lab/{result,packed-startup,progress}.json
 and its Chinese .txt handoff. No phone/main/switch/PCnetwork/originalDebian changes.
<!-- npu-diagnostic-image-current:end -->'''.replace('STATUS',a.goal_status.upper())
if start in text:
    left,right=text.index(start),text.index(end)+len(end)
    text=text[:left]+section+text[right:]
else:
    position=text.index('<!-- npu-activation3-current:start -->')
    text=text[:position]+section+'\n\n'+text[position:]
agents.write_text(text)
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-diagnostic-image'],cwd=r,check=True)
subprocess.run(['git','diff','--cached','--check','--','AGENTS.md','scripts/xr1710g/npu-diagnostic-image'],cwd=r,check=True)
print(json.dumps({'recorded':True,'goalStatus':a.goal_status,'artifactSHA256':image['artifactSHA256'],'changedPaths':len(image['changedFiles']),'hardwareDeployable':False}))
