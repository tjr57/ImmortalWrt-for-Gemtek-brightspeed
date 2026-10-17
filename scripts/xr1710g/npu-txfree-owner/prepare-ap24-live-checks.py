from pathlib import Path
import ast
w=Path(__file__).resolve().parents[1]
p=w/'environment/verify-ap23-deployment.py'
s=p.read_text().replace('ap23','ap24').replace('AP23','AP24')
s=s.replace('from xr_two_ap import WORKSPACE,connect,command,script','from xr_two_ap import WORKSPACE,connect as pinned_connect,command,script\ndef connect(unit,via=None):return pinned_connect(unit,via="lan")')
s=s.replace("a.base.VERSION=VERSION","a.base.VERSION=VERSION;a.base.connect=connect")
s=s.replace("for old,new in replacements:\n", "replacements=[*replacements,(\"via='direct'\",\"via='lan'\")] if \"via='direct'\" in code else replacements\n for old,new in replacements:\n")
s=s.replace('02:58:28:50:aa:74','02:58:28:50:aa:75')
s=s.replace("'dropbearDeviceRecreationFixInROMAndLive':True,","'npuTxfreeOwnershipGuardInstalled':True,'dropbearDeviceRecreationFixInROMAndLive':True,")
ast.parse(s);target=w/'environment/verify-ap24-deployment.py';assert not target.exists();target.write_text(s)
# Reuse the exact AP1-only recovery4/activation2/address observer qualified in
# eleven/eleven/twelve real-guest cases and AP23 original-firmware epoch3.
# No new boot helper or native binary; only host orchestration paths change.
p=w/'environment/run-guarded-npu-addresses.py';s=p.read_text()
s=s.replace('AP1 epoch 3: independently bounded fault addresses and token metadata; no traffic.','AP24 AP1 candidate ownership fix: original NPU blob, exact qualified startup, no traffic.')
s=s.replace('from xr_two_ap import WORKSPACE,connect,command','from xr_two_ap import WORKSPACE,connect as pinned_connect,command\ndef connect(unit,via=None):return pinned_connect(unit,via="lan")')
s=s.replace('20261010-ap23-d331711d','20261010-ap24-d331711d').replace('a.base.VERSION=VERSION','a.base.VERSION=VERSION;a.base.connect=connect')
s=s.replace("out=base/'live-epoch-3'","out=WORKSPACE/'development/ap24/npu-ap1-epoch1'")
s=s.replace('development/ap23/packed-files-qa.json','development/ap24/packed-files-qa.json')
# Remove unused snapshot routine whose old independence assumptions no longer
# describe AP2. No arbitrary gate is spoofed in the new harness.
start=s.index('def snapshot(diag):');end=s.index("assert len(sys.argv)==2",start)
s=s[:start]+s[end:]
s=s.replace("assert len(sys.argv)==2", "assert json.loads((WORKSPACE/'development/ap24/deployment/final-result.json').read_text())['passed']\nassert len(sys.argv)==2")
s=s.replace("'VMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12},'noPhoneTest':True", "'VMGates':{'activationCases':11,'recoveryCases':11,'addressObserverCases':12},'ownerAcceptedNoIndependentRecovery':True,'originalNpuFirmwareUnchanged':True,'candidateDmaOwnershipFixInstalled':True,'noPhoneTest':True")
s=s.replace("fault,_,code=command(c,'cat '+record+'/capture/first-fault.kmsg',check=False)","capture,_,capture_code=command(c,'cat '+record+'/capture/kernel.kmsg',check=False)\n if capture_code==0:(out/'capture-kernel.kmsg').write_bytes(capture)\n fault,_,code=command(c,'cat '+record+'/capture/first-fault.kmsg',check=False)")
s=s.replace("'NpuDriverActiveRecordedAtFault':", "'AP24OwnershipFixTrial':True,'originalNpuFirmwareUnchanged':True,'NpuDriverActiveRecordedAtFault':")
ast.parse(s);target=w/'environment/run-ap24-npu-ap1-epoch1.py';assert not target.exists();target.write_text(s)
print('Prepared AP24 deployment verification and bounded AP1 original-firmware candidate trial; neither executed')
