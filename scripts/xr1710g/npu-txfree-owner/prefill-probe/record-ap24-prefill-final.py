"""Close the TXFREE startup diagnosis, preserving the separate Maple unknown."""
from pathlib import Path
from datetime import datetime
import json,hashlib,re,shutil,subprocess
W=Path('/mnt/d/ChatGPT/XR1710G');R=Path('/home/xrdev/projects/xr1710g/openwrt');O=W/'development/ap24/prefill-probe'
j=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
a=j(O/'analysis.json');f=j(O/'final-health/result.json');old=j(W/'development/ap24/followup-result.json')
assert a['experimentQualified'] and a['startupPrefillCausalityDemonstrated'] and f['passed']
assert all(x['health']['healthy'] for x in f['APs'].values())
assert a['units']['1']['singleStartupInterventionReproducedHistoricalFault']
assert a['units']['2']['producerDescriptorMatchesStartupHostBuffer']
paths=['analysis.json','source-order.json','module-build.json','result.json','packed-startup.json','vm/vm-result-latest.json','vm/provenance.json',
 'ap1-epoch1/result.json','ap1-epoch1/analysis.json','ap2-epoch1/result.json','ap2-epoch1/analysis.json','final-health/result.json']
report={'at':datetime.now().astimezone().isoformat(),'version':f['version'],'goalStatus':'active','goalComplete':False,
 'phase':'Historical TXFREE startup-prefill cause demonstrated; production AP24 restored on both APs',
 'historicalTXFREEStartupCauseDemonstrated':True,'productionFixAlreadyIncludedInAP24':True,
 'cause':'Generic host page-pool prefill publishes firmware-owned TXFREE descriptors before NPU takeover; restoring only that startup operation reintroduces pointer mismatch and the historical truncation while AP24 runtime guards remain intact.',
 'AP1':{k:a['units']['1'][k] for k in ('bootID','activeMs','faultObserved','poolMismatches','shortFrames','mismatchRingIndices','recoveryReason')},
 'AP2':{k:a['units']['2'][k] for k in ('bootID','activeMs','faultObserved','poolMismatches','shortFrames','mismatchRingIndices','producerDescriptorMatchesStartupHostBuffer','recoveryReason')},
 'correctedControls':'development/ap24/owner-trace/analysis.json','originalFirmwarePacedLoad':'development/ap24/npu-ap1-load2/analysis.json',
 'fiveItemCodeBuildDeployment':'AP24 contains all five implementations; NPU TXFREE startup cause now demonstrated, phone/extended hardware acceptance deferred',
 'finalCurrentDevices':f['APs'],'evidence':{p:sha(O/p) for p in paths},
 'separateMapleOopsCauseProven':False,'fullNpuHardwareAcceptance':False,'NpuEnabledByDefault':False,
 'physicalPrefetchWritebackDirectlyObserved':False,
 'residual':['Separate historical mas_safe_min/mas_rev_awalk Maple Oops remains unattributed; do not claim it shares this cause',
 'PCIe prefetch/writeback is an explanation consistent with the first-four-entry pattern, not directly traced hardware internals',
 'Long-term/full-rate NPU and phone acceptance are not completed; all experimental parameters remain off'],
 'phoneTested':False,'mainRouterSwitchPCNetworkChanged':False}
(O/'final-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
note=f'''AP24：NPU TXFREE 启动预填充问题的因果验证（{report['at']}）

已确认的软件原因
旧代码在启动时，先向由 NPU 管理的 TXFREE 队列填入主机 page-pool 缓冲区并提交 DMA；随后 NPU 才接管初始化。
NPU 根据自己的私有缓冲区编号表读取数据。描述符若仍指向主机缓冲区，就会从另一块内存读取旧数据，出现描述符长度与报文头长度不一致。
AP24 已禁止这条队列的主机启动填充，也保护了后续填充、轮询、清理和复位路径。

本轮验证
诊断镜像只恢复旧的启动预填充，保留 AP24 全部运行期保护，沿用同一 NPU 生产端观测代码；增加两行启动元数据日志，不记录数据包或密钥。
先通过真实 Linux/KASAN 虚拟机检查、模块 ABI 和镜像内启动检查，再依次部署到 AP2、AP1。
AP2：前 4 项地址错配，第 0 项描述符地址 0x9421f000 与启动时填入的主机地址完全一致；之后 28 项正常。本轮没有触发长度截断。
AP1：启动约 36 秒重现截断，描述符长度 20、旧头部长度 212、计数 25。记录到的队列索引是 2，NPU 私有缓冲区为 0x8a501080，描述符为 0x948e0000。
AP1 启动日志只记录索引 0 的地址，因此不声称直接捕获了索引 2 的初始写入；单一启动干预、保留全部后续保护且重现同类故障构成了软件原因的因果证据。
对照：此前修复版 AP24 两台各 32 条记录均匹配，原始 NPU 固件的限速传输累计 12665 条 TXFREE 无截断。
AP1 故障触发自动恢复；AP2 按 180 秒期限恢复。所有测试和升级均只提交一次。

最终设备状态
两台已重新刷回正式 AP24（镜像 SHA256 411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0）。
AP1：192.168.10.3，开机 ID {f['APs']['1']['bootID']}。
AP2：192.168.10.4，开机 ID {f['APs']['2']['bootID']}。
配置、密码、SSH 身份和关键分区哈希保留；两台各 39 项 ROM 文件、13 项运行文件、41 项保留文件检查通过。
Tizer/160MHz、Poro/VLAN50、6GHz Mesh 与网关连接通过。诊断镜像、模块和临时启动请求已撤除，所有实验开关关闭。

仍保留的限制
首 4 项错配与源码设置的预取数量相符，但没有直接观测硬件内部预取/写回动作。
独立的 Maple 内核异常仍未归因，不能认定和 TXFREE 是同一问题；整体目标因此仍保持进行中。
本轮未做手机、长期或满速 NPU 验收，也未改动主路由、交换机或电脑网络配置。

证据索引：development/ap24/prefill-probe/final-result.json
'''
(O/'AP24-TXFREE因果验证结果.txt').write_text(note,encoding='utf-8')
gpath=W/'development/current-goal.json';g=j(gpath);g['status']='in-progress';g['latestAP24CausalEvidence']='development/ap24/prefill-probe/final-result.json'
g['networkState'].update({f'AP{u}':f"AP24 正式镜像，启动预填充诊断已结束；开机 {f['APs'][str(u)]['bootID']}，配置/身份与 Mesh、Tizer/Poro 正常，实验参数关闭。" for u in (1,2)})
g['NpuFinding']['historicalTXFREEStartupCauseProven']=True;g['NpuFinding']['rootCauseProven']=False
g['NpuFinding']['rootCauseScope']='TXFREE startup-prefill cause demonstrated; separate Maple Oops still unknown'
g['NpuFinding']['latestOwnershipEvidence']='development/ap24/prefill-probe/final-result.json';g['remainingNpuCodeInvestigation']='Separate Maple Oops: mas_safe_min / mas_rev_awalk; do not conflate with now-demonstrated TXFREE startup issue'
g={'latestAP24CausalEvidence':'development/ap24/prefill-probe/final-result.json',
   'currentNpuConclusion':{'TXFREE':'Startup-prefill cause demonstrated and fixed in production AP24',
                           'MapleOops':'Separate historical fault remains unattributed',
                           'experiments':'Completed; both APs restored; never rerun completed epochs'},**g}
gpath.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
p=R/'AGENTS.md';s=p.read_text();s=re.sub(r'<!-- ap24-prefill-current:start -->.*?<!-- ap24-prefill-current:end -->', '''<!-- ap24-prefill-current:start -->
## AP24 startup-prefill cause demonstrated; both production AP24 restored

- Latest authoritative evidence: development/ap24/prefill-probe/final-result.json.
 Startup-only old prefill intervention retained all AP24 runtime guards.
 AP2 first4 entries mismatched, first pointer exactly matched logged host page.
 AP1 reproduced len20/header212/count25 at36s, table8a501080 vsdesc948e0000,
 recorded index2. AP1 startup log is index0 only; do not claim direct equality.
- AP24 same-hook controls both32 matching rows; original firmware bounded load
 12665 TXFREE clean. Historical TXFREE startup software cause now demonstrated.
 Physical prefetch/writeback is inferred from source/order/first4, not directly
 observed. Separate historical Maple Oops remains unknown; broader goal active.
- Both diagnostic epochs and four image transitions are COMPLETE. Do NOT rerun
 any. Final health confirms original411299ad AP24, original NPU blob,39ROM/13live/
 41preserved files perAP, Mesh/Tizer/Poro/gateway healthy, allflags off.
- Private probe a67b7f2c intentionally reintroduces the startup defect. It is NOT
 a production candidate. Production source/frozen AP24 never changed this run.
 No phone tests, main/switch/PC changes. Next code investigation is the separate
 Maple Oops; never call the whole NPU stack fully qualified from bounded trials.
<!-- ap24-prefill-current:end -->''',s,flags=re.S);p.write_text(s)
dest=R/'scripts/xr1710g/npu-txfree-owner/prefill-probe'
for path in (W/'environment').glob('*ap24*prefill*.py'):shutil.copy2(path,dest/path.name)
shutil.copy2(O/'AP24-TXFREE因果验证结果.txt',dest/'RESULTS.txt')
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-txfree-owner/prefill-probe'],cwd=R,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=R,check=True)
print(json.dumps({'recorded':True,'TXFREEStartupCauseDemonstrated':True,'bothProductionAP24Healthy':True,'broaderGoalComplete':False}))
