"""Final current health/preservation checks after restoring production firmware."""
from pathlib import Path
from datetime import datetime
import json,re,importlib.util
from xr_two_ap import connect,command,WORKSPACE as w
spec=importlib.util.spec_from_file_location('checks',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
version='20261010-ap24-d331711d';a.base.VERSION=version;a.base.connect=lambda unit,via=None:connect(unit,via='lan')
out=w/'development/ap24/owner-trace/final-health';out.mkdir(exist_ok=True);j=lambda p:json.loads(p.read_text());save=lambda n,v:(out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert j(w/'development/ap24/npu-ap1-load2/result.json')['ordinaryRecoveryAndCleanupPassed']
packed=j(w/'development/ap24/packed-files-qa.json');results={}
for unit in (1,2):
 transition=w/f'development/ap24/owner-trace/deployment/ap{unit}-restore';assert j(transition/'result.json')['passed']
 before=j(transition/'preflight.json');c=connect(unit,via='lan')
 try:
  expected={'/rom/'+p:h for p,h in packed['matchedFiles'].items()};assert a.file_hashes(c,list(expected))==expected
  live={'/'+p:h for p,h in packed['matchedFiles'].items() if p.startswith(('lib/modules/','usr/libexec/xr1710g-','usr/sbin/xr1710g-','etc/init.d/dropbear'))};assert a.file_hashes(c,list(live))==live
  assert a.preservation(c)==before['preservationBefore'] and a.file_hashes(c,list(before['preservedFiles']))==before['preservedFiles']
  assert command(c,'sha256sum /lib/firmware/airoha/en7581_MT7996_npu_rv32.bin')[0].decode().split()[0]=='e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
  for path in ('/etc/xr1710g-diagnostic.json','/etc/xr-recovery.once','/etc/xr-npu-guarded.once','/usr/libexec/xr-diag-activate','/usr/libexec/xr-diag-recovery','/sys/module/xr_npu_addresses','/sys/module/xr_npu_producer'):
   assert command(c,'test ! -e '+path+' && test ! -L '+path,check=False)[2]==0,path
  raw=command(c,'dmesg')[0];assert not re.search(rb'TXFREE truncated|WARNING:|BUG:|Oops:|Kernel panic|Call [Tt]race:',raw);(out/f'ap{unit}-kernel.txt').write_bytes(raw)
  results[str(unit)]={'bootID':command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip(),'ROMMatched':len(expected),'liveFilesMatched':len(live),'preservedFiles':len(before['preservedFiles']),'originalNpuFirmware':True,'diagnosticToolsAndRequestsAbsent':True}
 finally:c.close()
 results[str(unit)]['health']=a.health(unit,version);assert results[str(unit)]['health']['healthy']
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':version,'imageSHA256':packed['imageSHA256'],'APs':results,'allExperimentalParametersOff':True,'phoneTested':False,'mainRouterSwitchPCNetworkChanged':False,'limits':['No phone or long-term/full-rate radio acceptance','Historical Maple Oops remains separate and unresolved']}
save('result.json',report);print(json.dumps(report))
