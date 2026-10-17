"""Record observed remote trials without replacing historical qualification evidence."""
from pathlib import Path
from datetime import datetime
import hashlib,json,re,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
out=w/'development/npu-remote-progress';out.mkdir(exist_ok=True)
links=['npu-diagnostic-ap2/promotion.json','npu-diagnostic-ap2/deployment/result.json',
       'npu-diagnostic-ap2/producer-baseline/result.json','npu-ap2-guard/live-epoch-1/result.json',
       'npu-ap2-debugfs/activation/vm/result-latest.json','npu-ap2-debugfs/activation/shipped-shell-qa.json',
       'npu-ap2-debugfs/live-epoch-2/result.json','npu-ap1-debugfs/activation/vm/result-latest.json',
       'npu-ap1-debugfs/activation/shipped-shell-qa.json','npu-activation4/package-build.json',
       'npu-diagnostic-ap1/deployment/result.json','npu-diagnostic-ap1/producer-baseline/result.json',
       'npu-ap1-debugfs/live-epoch-1/result.json']
evidence={p:{'sha256':sha(w/'development'/p),'result':read(w/'development'/p)} for p in links if (w/'development'/p).exists()}
active=w/'development/npu-ap2-debugfs/live-epoch-2/active-producer.txt'
lines=active.read_text().splitlines();assert lines[0]=='schema=2 atomic=0 source=producer-scalar record_words=12'
counts=[];rows=[];cursor=1
for hart in range(8):
    m=re.fullmatch(r'hart='+str(hart)+r' count=(\d+)',lines[cursor]);assert m
    count=int(m[1]);assert count<=32;counts.append(count);cursor+=1
    for record in range(count):
        m=re.fullmatch(f'hart={hart} record={record}'+''.join(r' w'+str(i)+r'=([0-9a-f]{8})' for i in range(12)),lines[cursor]);assert m
        v=[int(x,16) for x in m.groups()];assert v[10]==0 and v[11]==record+1 and v[3]>>27==6 and v[4]<=7
        rows.append({'descriptorBytes':v[1]>>16&0x3fff,'headerBytes':v[3]&0xffff,'sourceLast':bool(v[1]&1<<30),
                     'viewsEqual':v[3]==v[7],'controlStable':v[1]==v[2],'poolMatches':v[5]==v[6]});cursor+=1
assert cursor==len(lines) and counts==[0,0,0,0,32,0,0,0]
assert all(x=={'descriptorBytes':20,'headerBytes':20,'sourceLast':True,'viewsEqual':True,'controlStable':True,'poolMatches':True} for x in rows)
ap2=read(w/'development/npu-ap2-debugfs/live-epoch-2/result.json');assert ap2['passed']
report={'at':datetime.now().astimezone().isoformat(),'status':'in-progress','ownerAcceptedRemoteLoss':True,
        'AP2':{'diagnosticInstalled':True,'activationAndAutomaticRecoveryPassed':True,'faultObserved':False,
               'bootID':ap2['ordinaryBootID'],'healthy':ap2['health']['healthy'],'preservedFiles':41,
               'producerSample':{'sha256':sha(active),'source':'direct bounded SSH read, no recovery envelope',
                                 'bootID':ap2['diagnosticBootID'],'countsPerHart':counts,'all32DescriptorAndHeaderBytes':20,
                                 'twoViewsEqual':True,'coverage':'First32/hart only; not all notifications or a stress test'}},
        'AP1':{'deployment':evidence.get('npu-diagnostic-ap1/deployment/result.json',{}).get('result'),
               'epoch':evidence.get('npu-ap1-debugfs/live-epoch-1/result.json',{}).get('result')},
        'earlyDebugfsFix':{'problem':'S08 preflight precedes the S10 debugfs mount; old VM mounted it too early',
                          'AP2ActualActivationAfterFix':True,'ARMChecksPerRole':23,'VMRebootPairsPerRole':3,
                          'optionalPackageRelease':4,'packageBuildJobs':12,'inShippedRom':False},
        'historicalTXFREERootFixed':False,'historicalMapleRootFixed':False,
        'noMainSwitchPCNetworkOrOriginalDebianChanges':True,'evidence':evidence}
(out/'progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
goal=w/'development/current-goal.json';g=read(goal)
g['status']='in-progress-after-explicit-owner-resume';g['NpuFinding']['latestRemoteTrial']='development/npu-remote-progress/progress.json'
g['NpuFinding']['noFurtherActivationUntilAnalysis']=False
g['networkState']['AP2']='AP23 派生诊断镜像已安装；NPU 限时启用及自动恢复通过，41个保留文件和身份未变，普通启动 NPU 关闭，Tizer/Poro/Mesh/网关正常；仍仅 Mesh。'
if report['AP1']['deployment']:
    g['networkState']['AP1']='AP2 验收后，同一 AP23 派生诊断镜像保留配置升级成功；普通启动健康，41个文件和身份保留。最新 NPU 试验见 npu-remote-progress/progress.json。'
goal.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
notice='''<!-- npu-remote-trials-current:start -->
## Current remote NPU producer trial (2026-10-10)

- Explicit owner accepts remote recovery loss; older physical-only holds below
 are superseded. AP2 diagnostic image installed first and healthy, then AP1.
- AP23-derived ROM contains b48d5e6e producer observer, not a root fix. Image
 eb8e25b40ec03c50cf601911d95c6f118ab6534a339f839f373cc77fe88c5c7d;
 base release still AP23 plus diagnostic marker. Production blob/config and
 frozen AP23 are unchanged. Generic VM is not physical NPU acceptance.
- AP2 epoch1 rejected before NPU enable because S08 precedes S10 debugfs mount;
 old VM pre-mounted it. Early mount corrected, 23 ARM +3 real-kernel reboot
 pairs per role pass. Optional diagnostic package release4 built-j12; ROM
 release3 retained, live epochs temporarily use qualified role-specific helper.
- AP2 epoch2 cd61bf16 enabled NPU and captured32 producer records, all length20/
 header20, views equal, sourceLAST1. No fault across372 continuous kmsg records.
 Independent180s deadline recovered to20f1ba3f, full health/config/41files pass.
 First32/hart cannot prove later stream or historical TXFREE/Maple root fixed.
- Latest AP1 deployment/epoch status and hashes: development/npu-remote-progress/
 progress.json. Check it before acting. Never rerun submitted one-shot deploy
 or epoch scripts; old epochs and qualifiers are immutable. Defaultflags off.
<!-- npu-remote-trials-current:end -->

'''
agents=r/'AGENTS.md';text=agents.read_text();start='<!-- npu-remote-trials-current:start -->';end='<!-- npu-remote-trials-current:end -->'
if start in text:text=re.sub(re.escape(start)+r'.*?'+re.escape(end)+r'\n\n',notice,text,flags=re.S)
else:
    pos=text.index('## Owner-away preflash policy');text=text[:pos]+notice+text[pos:]
agents.write_text(text)
tracked=r/'scripts/xr1710g/npu-diagnostic-image'
for name in ('promote-npu-diag-ap2.py','prepare-npu-ap2-early-debugfs.py','test-npu-ap2-early-debugfs-shell.py',
             'prepare-npu-ap1-diagnostic-followup.py','build-npu-activation4-package.py','record-npu-remote-progress.py'):
    shutil.copy2(w/'environment'/name,tracked/name)
(tracked/'remote-qualification.txt').write_text(notice+'\nEvidence: D:/ChatGPT/XR1710G/development/npu-remote-progress/progress.json\n')
subprocess.run(['git','add','--','AGENTS.md','scripts/xr1710g/npu-diagnostic-image'],cwd=r,check=True)
print(json.dumps({'recorded':True,'AP2Healthy':True,'AP1DeploymentAccepted':bool(report['AP1']['deployment']),
                  'AP1EpochComplete':bool(report['AP1']['epoch']),'rootFixed':False}))
