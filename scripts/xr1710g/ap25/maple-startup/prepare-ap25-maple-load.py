from pathlib import Path
import ast
w=Path(__file__).resolve().parents[1]
s=(w/'environment/run-ap24-bounded-load2.py').read_text()
def replace(a,b):
 global s
 assert a in s,a
 s=s.replace(a,b)
replace("VERSION='20261010-ap24-d331711d'","VERSION='20261010-ap25-d331711d'")
replace("out=WORKSPACE/'development/ap24/npu-ap1-load2'","out=WORKSPACE/'development/ap25/maple-ap1-load1'")
replace('development/ap24/packed-files-qa.json','development/ap25/packed-files-qa.json')
replace('development/ap24/deployment/final-result.json','development/ap25/deployment/final-result.json')
replace('import json,hashlib,importlib.util,re,time,threading,shlex,sys','import json,hashlib,importlib.util,re,time,threading,shlex,sys\nfrom concurrent.futures import ThreadPoolExecutor')
insert="""startup=WORKSPACE/'development/ap25/maple-startup/ap1'
items['/usr/libexec/xr-npu-guarded-once']=startup/'files/xr-npu-guarded-once'
items['/usr/libexec/xr-recovery-once']=startup/'files/xr-recovery-once'
items['/usr/libexec/xr_maple_observer.ko']=WORKSPACE/'development/ap24/maple-observer/xr_maple_observer.ko'
startup_qa=json.loads((startup/'shell-qa.json').read_text())
assert startup_qa['passed'] and len(startup_qa['checks'])==14 and startup_qa['helperSHA256']==sha(items['/usr/libexec/xr-npu-guarded-once'])
maple_qa=json.loads((WORKSPACE/'development/ap24/maple-observer/result-latest.json').read_text())
assert maple_qa['passed'] and maple_qa['moduleSHA256']==sha(items['/usr/libexec/xr_maple_observer.ko'])
ap2_trial=json.loads((WORKSPACE/'development/ap25/maple-ap2-epoch1/result.json').read_text())
assert ap2_trial['ordinaryRecoveryAndCleanupPassed'] and ap2_trial['NpuDriverActiveObserved'] and not ap2_trial['kernelFaultObserved']
"""
pos=s.index("links=['/etc/rc.d/S08xr_diag_recovery'");s=s[:pos]+insert+s[pos:]
begin=s.index("   for label,ip in [('peerPing'");end=s.index('   if unit==1:',begin)
old=s[begin:end]
new="""   targets=[('peerPing','192.168.10.'+('4' if unit==1 else '3')),('gatewayPing','192.168.10.1')]
   with ThreadPoolExecutor(max_workers=2) as pool:
    probes={label:pool.submit(command,c,'ping -I br-lan.1 -i 1 -c 5 -W 1 '+ip,timeout=12,check=False) for label,ip in targets}
    for label,ip in targets:
     data,error,code=probes[label].result()
     match=re.search(rb'(\\d+) packets transmitted, (\\d+) packets received',data)
     row[label]={'sent':int(match[1]),'received':int(match[2])} if match and code==0 else {'sent':0,'received':0}
     row[label+'Raw']={'stdout':data.decode(),'stderr':error.decode(),'code':code}
"""
s=s[:begin]+new+s[end:]
replace("'/sys/module/xr_npu_addresses']:assert absent","'/sys/module/xr_npu_addresses','/sys/module/xr_maple_observer']:assert absent")
replace("'VMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12}","'inheritedNativeVMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12},'newHelperARMCases':14,'passiveMapleObserverAdded':True,'ownerHomeMode':True")
replace('Two8secondTCPdirections,2streams,100MbpsPerStream,AP2clientAP1server','Two20secondTCPdirections,4streams,unpaced,AP2clientAP1server')
replace("'parameters':params(c)})","'parameters':params(c),'mapleObserver':read(c,'cat /sys/kernel/debug/xr_maple_observer')})")
pos=s.index("  save('activation-observed.json',")
s=s[:pos]+"  assert read(c,'cat /sys/kernel/debug/xr_maple_observer')=='schema=1 captured=0' and 'XR_MAPLE_OBSERVER ready exact_site=d4 passive=1' in kernel\n"+s[pos:]
replace("  save('activation-observed.json',", "  (out/'activation-kernel.txt').write_text(kernel)\n  save('activation-observed.json',")
replace("'/tmp/xr-ap24-load-'","'/tmp/xr-ap25-maple-load-'")
replace('timeout 18 iperf3 -s','timeout 30 iperf3 -s')
replace('timeout 15 iperf3 -c','timeout 27 iperf3 -c')
replace('-t 8 -P 2 -b 100M -J','-t 20 -P 4 -J')
replace('timeout=25,check=False','timeout=35,check=False')
replace('duration=8,reverse=reverse)','duration=20,reverse=reverse,streams=4)')
replace('tcpPacingMbpsPerStream=100','tcpPacingMbpsPerStream=None,streams=4,durationSeconds=20')
replace("assert absent(c,'/sys/module/xr_npu_addresses') and absent(c,'/sys/kernel/debug/xr_npu_addresses')","assert absent(c,'/sys/module/xr_npu_addresses') and absent(c,'/sys/kernel/debug/xr_npu_addresses') and absent(c,'/sys/module/xr_maple_observer') and absent(c,'/sys/kernel/debug/xr_maple_observer')")
replace("'AP24OwnershipFixTrial':True","'AP24OwnershipFixTrial':True,'passiveMapleObserverInstalledBeforeNpu':True,'newMapleSnapshotObserved':b'XR_MAPLE_SNAPSHOT schema=1' in capture")
replace('AP24 AP1 candidate ownership fix: original NPU blob, exact qualified startup, bounded two-direction AP-to-AP TCP load.','AP25 AP1 passive Maple observer with two 20-second unpaced four-stream TCP transfers.')
ast.parse(s);p=w/'environment/run-ap25-maple-ap1-load1.py';assert not (w/'development/ap25/maple-ap1-load1/operation.json').exists();p.write_text(s)
print('New AP1 original-NPU Maple-observer unpaced load script prepared; AP2 acceptance required before submission')
