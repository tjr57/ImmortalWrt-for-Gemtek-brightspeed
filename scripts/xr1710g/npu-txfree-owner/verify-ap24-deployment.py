from pathlib import Path
from datetime import datetime
import json,importlib.util,sys,re
from xr_two_ap import WORKSPACE,connect as pinned_connect,command,script
def connect(unit,via=None):return pinned_connect(unit,via="lan")
spec=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
VERSION='20261010-ap24-d331711d';a.base.VERSION=VERSION;a.base.connect=connect
out=WORKSPACE/'development/ap24/deployment';packed=json.loads((WORKSPACE/'development/ap24/packed-files-qa.json').read_text())
for unit in (1,2):assert json.loads((out/('ap'+str(unit)+'-upgrade/result.json')).read_text())['passed']
def existing(filename,replacements,args=()):
 path=Path(__file__).with_name(filename);code=path.read_text(encoding='utf-8')
 replacements=[*replacements,("via='direct'","via='lan'")] if "via='direct'" in code else replacements
 for old,new in replacements:
  assert old in code,(filename,old);code=code.replace(old,new)
 old_args=sys.argv
 try:
  sys.argv=[str(path),*args]
  try:exec(compile(code,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
  except SystemExit as error:assert error.code in (None,0)
 finally:sys.argv=old_args
files={};health={}
for unit in (1,2):
 c=connect(unit)
 try:
  expected={'/rom/'+p:h for p,h in packed['matchedFiles'].items()};assert a.file_hashes(c,list(expected))==expected
  modules={'/'+p:h for p,h in packed['matchedFiles'].items() if p.startswith('lib/modules/')};assert a.file_hashes(c,list(modules))==modules
  before=json.loads((out/('ap'+str(unit)+'-upgrade/preflight.json')).read_text())
  assert a.preservation(c)==before['preservationBefore'] and a.file_hashes(c,list(before['preservedFiles']))==before['preservedFiles']
  kernel=command(c,'dmesg')[0];(out/f'final-kernel-ap{unit}.txt').write_bytes(kernel)
  assert not re.search(rb'WARNING:|BUG:|kernel BUG|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated',kernel)
  files[str(unit)]={'ROMMatched':len(expected),'activeModulesMatched':len(modules),'preservedFiles':len(before['preservedFiles'])}
 finally:c.close()
 health[str(unit)]=a.health(unit,VERSION);assert health[str(unit)]['healthy']
existing('verify-ap12-web-ap1.py',[('20261009-ap12-d331711d',VERSION),('development/ap12/ap1-web-login.json','development/ap24/deployment/ap1-web-login.json')])
existing('check-ap22-ap2-live.py',[("out=w/'development/ap22/web-recovery'","out=w/'development/ap24/deployment'"),('20261010-ap22-d331711d',VERSION),("checks['AP22Running']","checks['AP24Running']")],['full'])
existing('verify-ap22-iot-backhaul.py',[("out=w/'development/ap22/web-recovery'","out=w/'development/ap24/deployment'"),
 ("(out/'mesh-live-latest.json')","(out/'full-live-latest.json')"),
 ("prefix='post-reboot-' if (out/'reboot-returned.json').exists() else ''","prefix=''"),
 ('02:58:28:50:aa:72','02:58:28:50:aa:75'),('AP22_REAL_MESH','AP24_REAL_MESH')])
report={'passed':True,'at':datetime.now().astimezone().isoformat(),'version':VERSION,'imageSHA256':packed['imageSHA256'],
 'AP2AcceptedBeforeAP1':True,'bothKeepConfiguration':True,'bothOrdinaryRebootSSHAutorecovered':True,
 'npuTxfreeOwnershipGuardInstalled':True,'dropbearDeviceRecreationFixInROMAndLive':True,'collectorPackagedButOptInAbsent':True,
 'fileVerification':files,'health':health,'realMeshVLAN50DHCPDNSPassed':True,'temporaryIoTClientRemoved':True,
 'AP1ChineseRootWebLoginPassed':True,'allExperimentalFlagsOff':True,'phoneTested':False,
 'historicalNpuRootCauseProven':False,'NpuHardwareOffloadQualified':False,
 'mainRouterSwitchWindowsNetworkOriginalDebianChanged':False,'newRawFlashConfigKeysBackupsCreated':False}
(out/'final-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
