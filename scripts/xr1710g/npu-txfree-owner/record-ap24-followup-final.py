"""Record observed results and residual limits without marking the broader goal complete."""
from pathlib import Path
from datetime import datetime
import json,hashlib,re,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');o=w/'development/ap24';j=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
final=j(o/'owner-trace/final-health/result.json');trace=j(o/'owner-trace/analysis.json');load=j(o/'npu-ap1-load2/result.json');audit=j(o/'current-source-audit/result.json')
assert final['passed'] and trace['passed'] and audit['passed'] and load['ordinaryRecoveryAndCleanupPassed']
enabled=j(o/'npu-ap1-load2/module-enabled.json');recovery=j(o/'npu-ap1-load2/recovery.json');assert enabled['bootID']==recovery['bootID']
paths=['owner-trace/analysis.json','owner-trace/final-health/result.json','npu-ap1-load1/result.json','npu-ap1-load1/analysis.json','npu-ap1-load1/probe-parser-inspection.json','npu-ap1-load1/probe-integer-interval.json','npu-ap1-load2/result.json','npu-ap1-load2/analysis.json','current-source-audit/result.json','current-source-audit/control-qa.json','owner-trace/remote-gates-qa.json','owner-trace/live-parser-qa.json']
evidence={p:{'SHA256':sha(o/p),'path':'development/ap24/'+p} for p in paths}
evidence['npu-ap1-load1/probe-cli-qa.json']={'SHA256':sha(o/'npu-ap1-load1/probe-cli-qa.json'),'path':'development/ap24/npu-ap1-load1/probe-cli-qa.json'}
report={'at':datetime.now().astimezone().isoformat(),'version':final['version'],'goalStatus':'active','goalComplete':False,'phase':'AP24 post-fix producer comparison, original-firmware bounded transfer and production restoration complete','sourceAndArtifactAuditPassed':True,'diagnosticProducerObservations':trace['after'],'originalFirmwareLoad':{'bootID':enabled['bootID'],'activeMs':recovery['monotonicMs']-enabled['monotonicMs'],'qualified':load['bothBoundedTransfersQualified'],'captureContinuous':load['captureContinuousAndComplete'],'faultObserved':load['kernelFaultObserved'],'transfers':load['traffic']},'finalCurrentDevices':final['APs'],'evidence':evidence,'residual':['Historical physical writer/cache timing not directly observed; ownership bug is demonstrated and fixed, but do not equate bounded clean epochs with exhaustive root proof','Separate prior Maple Oops cause remains unresolved','Phone, full-rate and long-term radio acceptance deferred; experimental features remain off'],'mainRouterSwitchPCNetworkChanged':False,'phoneTested':False}
load_analysis=j(o/'npu-ap1-load2/analysis.json')
report['originalFirmwareLoad']['scalarSamples']=load_analysis['scalarSamples']
(o/'followup-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
gpath=w/'development/current-goal.json';g=j(gpath);g['status']='in-progress';g['latestAP24Followup']='development/ap24/followup-result.json'
g['networkState'].update({f'AP{u}':f"AP24 正式镜像，诊断镜像已撤除；当前开机 {final['APs'][str(u)]['bootID']}，配置/身份与 6GHz Mesh、Tizer/Poro 正常，实验参数关闭。" for u in (1,2)})
g['NpuFinding']['latestOwnershipEvidence']='development/ap24/followup-result.json';g['NpuFinding']['rootCauseProven']=False;gpath.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
rates='；'.join(('AP1→AP2' if x.get('reverse') else 'AP2→AP1')+f" {x['receiverMbps']:.1f} Mbps" for x in load['traffic'] if x.get('qualified')) or '未形成两方向合格结果，见原始记录'
note=f'''AP24 后续开发与回归记录（{report['at']}）

两台 AP 均已恢复 AP24 正式镜像，管理地址、密码、无线与 VLAN 配置保留。
AP1：192.168.10.3；AP2：192.168.10.4。6GHz Mesh、5GHz Tizer/160MHz、2.4GHz Poro/VLAN50 检查通过。

NPU 队列归属修复：真实 Linux 虚拟机复现旧代码的 4 项越权操作，修改后 4 项通过，普通队列对照不变。
使用与修复前相同的诊断固件：AP1/AP2 各 32 条生产端记录，均无指针错配和短帧；约 179 秒内分别观察 1223/1407 条 TXFREE，采集器未报告内核故障。
原始 NPU 固件限时传输：{rates}。每方向 8 秒、2 条流，每流限速 100 Mbps；这不是吞吐上限测试。
本轮最后一次有效采样记录 {load_analysis['scalarSamples'][-1]['messages']} 条 TXFREE；短头、长度不一致和截断计数均为零，采集器未报告内核故障。
自动恢复完成，临时启动请求、诊断模块与诊断镜像已撤除，实验参数仍默认关闭。
首轮负载被测试程序拦下：BusyBox 不支持小数 ping 间隔，实际未发包，也未执行 iperf。原记录保留；改为整数间隔并实测后使用全新的启动轮次重测。

FT/PPE/MCU统计/STA打孔和 CAC 源码与当前产物重新核对通过；FT 当前源码 10 项检查通过，控制器与当前配置程序联合 20 项检查通过。
纠正了旧测试报告中“自动打孔与 MLO 互斥”的过期描述，当前可共同配置；MLO+FT 仍受适用性限制。
七组候选按现有 5GHz 用户、2.4GHz IoT、6GHz Mesh 拓扑审查；已有 OFDMA 重连与后台 CAC 修复已包含在 AP24。

整个目标继续保持进行中：仍不能将这些有限时长结果视为历史物理写入时序、独立 Maple Oops 或长期 NPU 稳定性的完整证明。手机测试暂不进行。
证据索引：development/ap24/followup-result.json
'''
(o/'AP24-后续回归结果.txt').write_text(note,encoding='utf-8')
p=r/'AGENTS.md';t=p.read_text();t=re.sub(r'<!-- ap24-followup-final:start -->.*?<!-- ap24-followup-final:end -->\n?', '',t,flags=re.S)
notice='''<!-- ap24-followup-final:start -->
## AP24 follow-up completed; broader NPU goal remains active

- Authoritative latest: D:/ChatGPT/XR1710G/development/ap24/followup-result.json.
 Both APs restored original AP24 image411299ad; trace image removed, default
 experiment flags off, config/root/SSH/critical hashes and Mesh/radios healthy.
- AP1/AP2 same-producer-hook post-fix trials each32 matching pointer/length
 rows;1223/1407 TXFREE over about179seconds, no collector fault. Then original
 firmware AP1 bounded two-direction load; exact qualification in followup JSON.
- All submitted epochs/transitions are complete and MUST NOT be rerun.
 Control+current configurator20case regression now accepts autoPP+MLO; old
 inherited report's rejection text superseded. FT10 and current source/module
 provenance audit passed. Phone tests deferred, no main/switch/PC changes.
- Do not claim all NPU faults/root causes solved: host ownership bug reproduced
 and fixed, but historical exact physical writer/cache timing and separate
 Maple Oops are not directly established. Keep goal active; avoid blanket NPU
 enablement or treating bounded paced throughput as full-rate qualification.
<!-- ap24-followup-final:end -->
'''
pos=t.index('<!-- ap24-trace-current:start -->');p.write_text(t[:pos]+notice+'\n'+t[pos:])
dest=r/'scripts/xr1710g/npu-txfree-owner';files=('analyze-ap24-owner-traces.py','run-ap24-bounded-load.py','run-ap24-bounded-load2.py','prepare-ap24-load2.py','inspect-ap24-forwarding-probe.py','check-ap24-load-prerequisites.py','test-ap24-control-current.py','audit-ap24-current-sources.py','verify-ap24-after-trials.py','record-ap24-followup-final.py','test-ap24-remote-diagnostic-gates.py','analyze-ap24-bounded-load.py')
for n in files:shutil.copyfile(w/'environment'/n,dest/n)
shutil.copyfile(w/'environment/check-ap24-probe-cli.py',dest/'check-ap24-probe-cli.py')
shutil.copyfile(w/'environment/xr_npu_diagnostic_gates.py',dest/'xr_npu_diagnostic_gates.py')
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-txfree-owner'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
print(json.dumps({'recorded':True,'goalComplete':False,'loadQualified':load['bothBoundedTransfersQualified']}))
