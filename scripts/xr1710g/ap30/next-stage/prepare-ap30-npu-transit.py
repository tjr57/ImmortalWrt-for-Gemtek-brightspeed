"""Create a fresh AP30/recovery6 one-boot trial; never run old journals."""
from pathlib import Path
import ast

w=Path('D:/ChatGPT/XR1710G')
s=(w/'environment/run-ap27-npu-steady2.py').read_text()
def change(old,new):
    global s
    assert old in s,old
    s=s.replace(old,new)

change('AP26 real wired-to-Mesh transit through AP1 NPU; qualified one-boot recovery unchanged.',
       'Owned AP30 wired-to-Mesh transit through AP1 NPU with qualified recovery6.')
change('20261010-ap26-d331711d','20261010-ap30-d331711d')
change("recovery=WORKSPACE/'development/npu-recovery'", "recovery=WORKSPACE/'development/npu-recovery6'")
change('development/ap27/forwarding/steady-npu-2','development/ap30/forwarding/npu-transit1')
change('development/ap25/maple-startup/ap1','development/ap30/npu-gates/ap1')
change('development/ap27/forwarding/steady-guard','development/ap30/npu-gates/ap1')
# The fresh helper is 240s; compare it to the immutable recovery6 180s helper.
change("(startup/'files/xr-recovery-once').read_text().replace", "(recovery/'files/xr-recovery-once').read_text().replace")
change("assert json.loads((WORKSPACE/'development/ap27/forwarding/steady-software-2/result.json').read_text())['pings']=={'1':{'sent':105,'received':105},'2':{'sent':105,'received':105}}",
       "assert json.loads((WORKSPACE/'development/ap30/forwarding-completion.json').read_text())['passed']")
change('development/ap26/deployment/final-result.json','development/ap30/deployment/final-result.json')
change('development/ap27/forwarding/steady-software-2/header-analysis.json','development/ap30/forwarding/loaded-transit1/analysis.json')
change('for directory,count in ((base,11),(recovery,11)):', 'for directory,count in ((base,11),(recovery,18)):')
change("vm=json.loads((directory/'vm/result-latest.json').read_text());", "vm=json.loads(((WORKSPACE/'development/ap30/npu-gates/activation-vm/result-latest.json') if directory==base else (directory/'vm/result-latest.json')).read_text());")
change("(base/'vm/result-latest.json')", "(WORKSPACE/'development/ap30/npu-gates/activation-vm/result-latest.json')")
change("assert json.loads((recovery/'live-baseline/result.json').read_text())['automatic180SecondRecoveryToOrdinaryBoot']", """live_recovery=json.loads((WORKSPACE/'development/ap30/recovery6-live1/result.json').read_text())
assert live_recovery['passed'] and live_recovery['completeContinuousCollectorClosureRequiredAndObserved']
assert live_recovery['recoveryBuild']['binaries']==rec_build['binaries']
manifest=json.loads((WORKSPACE/'development/ap30/npu-gates/prepared.json').read_text())
assert manifest['version']==VERSION
repo=Path(r'\\\\wsl.localhost\\Debian-XR1710G\\home\\xrdev\\projects\\xr1710g\\openwrt')
k=repo/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
assert {name:sha(k/name) for name in manifest['kernelBuildHashes']}==manifest['kernelBuildHashes']
assert json.loads((WORKSPACE/'development/ap30/build-module-abi.json').read_text())['passed']
for name,digest in manifest['helperHashes'].items():assert sha(WORKSPACE/'development/ap30/npu-gates'/name)==digest
""")
change('development/ap25/packed-files-qa.json','development/ap30/packed-files-qa.json')
change("'inheritedNativeVMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12}",
       "'inheritedNativeVMGates':{'activationWithRecovery6Cases':11,'recoveryCases':18,'addressObserverCases':12}")
change('Steady topology only, one20second/P4 PC-to-AP2 transfer, simultaneous36 ICMP probes per AP and42s headers-only observations',
       'Two20second/P4 directions PC-to-AP2 and reverse,36 ICMP probes per AP per direction and42s headers-only observations; AP1 NPU only, PPE off')
change('for index,reverse in enumerate((False,)):', 'for index,reverse in enumerate((False,True)):')
change('if remaining<70000:', 'if remaining<80000:')
change('probes=Probes(out)', "probe_out=out/('direction-'+str(index));probe_out.mkdir();probes=Probes(probe_out)")
change('xr-ap27-transit-', 'xr-ap30-npu-transit-')
change('5319','5331');change(':14C7',':14D3')
change("    after=snapshot(diag);save('after-'+str(index)+'.json',after)", """    probes.finish()
    probe_check=qualify_probe_headers(probe_out)
    save('direction-'+str(index)+'-probes.json',probe_check)
    if not probe_check['passed']:epoch.reject('loaded echo exchange or four-stage header evidence incomplete')
    after=snapshot(diag);save('after-'+str(index)+'.json',after)
""")
change("save('steady-after-traffic.json',readiness_after)", "save('steady-after-traffic-'+str(index)+'.json',readiness_after)")
change("case.update(reverse=reverse,tcpPacingMbpsPerStream=None,streams=4,durationSeconds=20)",
       "case.update(reverse=reverse,tcpPacingMbpsPerStream=None,streams=4,durationSeconds=20,probeEvidence=probe_check)")
change("saved.get('aborted.json',{}).get('reason') not in (None,'deadline')", "saved.get('aborted.json',{}).get('reason')!='deadline' or saved.get('recovery.json',{}).get('reason')!='deadline'")
change("'boundedForwardTransferQualified':capture_complete and len(traffic)==1", "'boundedBidirectionalTransfersQualified':capture_complete and len(traffic)==2")
change("assert absent(c,'/sys/module/xr_npu_addresses')", "assert absent(c,'/sys/module/xr_npu_addresses')")
change("'AP24OwnershipFixTrial':True", "'AP30ForwardingFixesAndRecovery6Trial':True")
# Report genuine exceptions while waiting, without repeating any submission.
change("if time.monotonic()-last_notice>30:print(json.dumps({'waitingForRecovery':type(error).__name__}),flush=True);last_notice=time.monotonic()",
       "if time.monotonic()-last_notice>30:print(json.dumps({'waitingForRecovery':type(error).__name__,'detail':str(error)[:160]}),flush=True);last_notice=time.monotonic()")

anchor="assert json.loads((WORKSPACE/'development/ap30/deployment/final-result.json').read_text())['passed']"
helper='''def qualify_probe_headers(directory):
 from collections import Counter
 from ap27_forwarding_observer import header_rows
 pings={};counts={};capture={}
 monitors=json.loads((directory/'icmp-monitors.json').read_text())
 assert len(monitors)==6 and all('error' not in m for m in monitors)
 for u in [1,2]:
  data=(directory/f'ap{u}-peer-ping.txt').read_text()
  m=re.search(r'(\\d+) packets transmitted, (\\d+) packets received',data)
  assert m
  pings[str(u)]={'sent':int(m[1]),'received':int(m[2])}
  for interface in ['br-lan.1','mesh6g']:
   name=f'ap{u}-{interface}-headers'
   counts[name]=Counter(tuple(row[k] for k in ['source','destination','type','id','seq','length'])
                        for row in header_rows((directory/(name+'.txt')).read_text()))
   drop=re.search(r'(\\d+) packets dropped by kernel',(directory/(name+'.stderr')).read_text())
   assert drop
   capture[name]=int(drop[1])
 first=next(iter(counts.values()))
 passed=all(p=={'sent':36,'received':36} for p in pings.values())
 passed=passed and len(first)==144 and all(v==1 for v in first.values())
 passed=passed and all(c==first for c in counts.values()) and all(v==0 for v in capture.values())
 return {'passed':passed,'pings':pings,'captureDrops':capture,'eachStageHeaders':{k:sum(v.values()) for k,v in counts.items()},'fourStageMatch':all(c==first for c in counts.values())}

'''
change(anchor,helper+anchor)
ast.parse(s)
target=w/'environment/run-ap30-npu-transit1.py'
assert not target.exists()
target.write_text(s,encoding='utf-8',newline='\n')
print('Prepared AP30 NPU trial with new manifest, recovery6, per-direction probe gates; not executed.')
