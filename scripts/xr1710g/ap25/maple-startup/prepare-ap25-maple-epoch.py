"""Generate a new AP2 one-shot observer epoch; never reuse old journal paths."""
from pathlib import Path
import ast,re
w=Path(__file__).resolve().parents[1]
s=(w/'environment/run-ap24-npu-ap1-epoch1.py').read_text()
def swap(text,a,b):return text.replace(a,'__XR_SWAP__').replace(b,a).replace('__XR_SWAP__',b)
s=swap(s,'connect(1)','connect(2)')
s=re.sub(r'AP([12])(?![0-9])',lambda m:'AP'+str(3-int(m[1])),s)
s=s.replace('ap2_before','ap1_before').replace("['role']=='ap1'","['role']=='ap2'")
s=s.replace("VERSION='20261010-ap24-d331711d'","VERSION='20261010-ap25-d331711d'")
s=s.replace("out=WORKSPACE/'development/ap24/npu-ap1-epoch1'","out=WORKSPACE/'development/ap25/maple-ap2-epoch1'")
s=s.replace("out.mkdir(exist_ok=True)","out.mkdir(parents=True,exist_ok=True)")
s=s.replace('development/ap24/packed-files-qa.json','development/ap25/packed-files-qa.json')
anchor="links=['/etc/rc.d/S08xr_diag_recovery'"
pos=s.index(anchor)
s=s[:pos]+'''startup=WORKSPACE/'development/ap25/maple-startup/ap2'
items['/usr/libexec/xr-npu-guarded-once']=startup/'files/xr-npu-guarded-once'
items['/usr/libexec/xr-recovery-once']=startup/'files/xr-recovery-once'
items['/usr/libexec/xr_maple_observer.ko']=WORKSPACE/'development/ap24/maple-observer/xr_maple_observer.ko'
startup_qa=json.loads((startup/'shell-qa.json').read_text())
assert startup_qa['passed'] and len(startup_qa['checks'])==14 and startup_qa['helperSHA256']==sha(items['/usr/libexec/xr-npu-guarded-once'])
maple_qa=json.loads((WORKSPACE/'development/ap24/maple-observer/result-latest.json').read_text())
assert maple_qa['passed'] and maple_qa['moduleSHA256']==sha(items['/usr/libexec/xr_maple_observer.ko'])
assert json.loads((WORKSPACE/'development/ap24/maple-observer/live-baseline2/result.json').read_text())['passed']
for u in (2,1):assert json.loads((WORKSPACE/f'development/ap25/deployment/ap{u}/result.json').read_text())['passed']
'''+s[pos:]
s=s.replace("'/sys/module/xr_npu_addresses']:assert absent", "'/sys/module/xr_npu_addresses','/sys/module/xr_maple_observer']:assert absent")
s=s.replace("'VMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12}","'inheritedNativeVMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12},'newStartupHelperARMCases':14,'passiveMapleObserverAdded':True,'ownerHomeMode':True")
old="active_samples.append({'bootID':current,'uptime':read(c,'cat /proc/uptime'),'tokenMetadata':token(c),'parameters':params(c)})"
assert old in s
s=s.replace(old,"active_samples.append({'bootID':current,'uptime':read(c,'cat /proc/uptime'),'tokenMetadata':token(c),'parameters':params(c),'mapleObserver':read(c,'cat /sys/kernel/debug/xr_maple_observer')})")
anchor="  save('activation-observed.json',"
pos=s.index(anchor)
s=s[:pos]+'''  maple=read(c,'cat /sys/kernel/debug/xr_maple_observer')
  assert maple=='schema=1 captured=0' and 'XR_MAPLE_OBSERVER ready exact_site=d4 passive=1' in kernel
  (out/'initial-maple-snapshot.txt').write_text(maple+'\\n')
'''+s[pos:]
s=s.replace("assert absent(c,'/sys/module/xr_npu_addresses') and absent(c,'/sys/kernel/debug/xr_npu_addresses')", "assert absent(c,'/sys/module/xr_npu_addresses') and absent(c,'/sys/kernel/debug/xr_npu_addresses') and absent(c,'/sys/module/xr_maple_observer') and absent(c,'/sys/kernel/debug/xr_maple_observer')")
s=s.replace("'AP24OwnershipFixTrial':True", "'AP24OwnershipFixTrial':True,'passiveMapleObserverInstalledBeforeNpu':True,'newMapleSnapshotObserved':b'XR_MAPLE_SNAPSHOT schema=1' in capture")
s=s.replace('AP24 AP2 candidate ownership fix: original NPU blob, exact qualified startup, no traffic.','AP25 AP2 original NPU boot with passive Maple observer; no generated traffic.')
assert "'passiveMapleObserverInstalledBeforeNpu':True" in s and 'AP14' not in s
ast.parse(s);p=w/'environment/run-ap25-maple-ap2-epoch1.py'
assert not (w/'development/ap25/maple-ap2-epoch1/operation.json').exists(),'Never alter a submitted epoch'
p.write_text(s)
print('New AP2 original-NPU/passive-Maple epoch prepared; not submitted')
