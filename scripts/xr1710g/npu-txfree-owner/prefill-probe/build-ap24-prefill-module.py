"""Rebuild only private dma.o using captured production commands and exact ABI."""
from pathlib import Path
from datetime import datetime
import hashlib,json,subprocess,os,shlex,shutil,fcntl
W=Path('/mnt/d/ChatGPT/XR1710G');R=Path('/home/xrdev/projects/xr1710g/openwrt')
P=R/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791'
O=W/'development/ap24/prefill-probe';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (O/'module-build.json').exists()
vm=json.loads((O/'vm/vm-result-latest.json').read_text());assert vm['passed']
assert vm['sourceBindings']['after']['sourceSHA256']==sha(O/'dma.c')
run=R.parent/'boot-lab'/('ap24-prefill-module-'+datetime.now().strftime('%Y%m%d-%H%M%S'));run.mkdir()
paths=[P/'dma.c',P/'mt76.ko',P/'dma.o',R/'.config',P.parent/'linux-6.18.54/Module.symvers']
protected={str(p):sha(p) for p in paths}
env=dict(os.environ);env['PATH']=str(R/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin')+':'+str(R/'staging_dir/host/bin')+':'+env['PATH'];env['STAGING_DIR']=str(R/'staging_dir')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 objects=(P/'mt76.mod').read_text().splitlines()
 for rel in objects+['mt76.mod.o','.module-common.o','mt76.mod']:
  shutil.copy2(P/rel,run/rel)
 shutil.copy2(O/'dma.c',run/'dma.c')
 commands=[]
 with (O/'module-build.log').open('w') as log:
  for target in ('dma.o','mt76.o','mt76.ko'):
   command=(P/('.'+target+'.cmd')).read_text().splitlines()[0].split(' := ',1)[1]
   argv=shlex.split(command);commands.append(argv)
   subprocess.run(argv,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 # No new imports or export/version contracts. Reuse of generated mod.o is
 # valid only under this exact equality; otherwise a full modpost is required.
 nm=env['PATH'].split(':')[0]+'/aarch64-openwrt-linux-musl-nm'
 def undefined(p):return subprocess.check_output([nm,'-u',p],text=True).splitlines()
 assert undefined(run/'mt76.ko')==undefined(P/'mt76.ko')
 from elftools.elf.elffile import ELFFile
 def sections(p):
  with p.open('rb') as f:
   e=ELFFile(f);return {s.name:s.data() for s in e.iter_sections() if s.name in ('.modinfo','__versions','__ksymtab_strings')}
 assert sections(run/'mt76.ko')==sections(P/'mt76.ko')
 module=O/'mt76-prefill-probe.ko';shutil.copy2(run/'mt76.ko',module)
 subprocess.run([env['PATH'].split(':')[0]+'/aarch64-openwrt-linux-musl-strip','--strip-debug',module],check=True)
 assert undefined(module)==undefined(P/'mt76.ko')
 assert all(sha(Path(p))==h for p,h in protected.items())
 report={'passed':True,'at':datetime.now().astimezone().isoformat(),'moduleSHA256':sha(module),'moduleBytes':module.stat().st_size,
  'sourceSHA256':sha(O/'dma.c'),'VMReportSHA256':sha(O/'vm/vm-result-latest.json'),'productionInputsUnchanged':protected,
  'undefinedSymbolsIdentical':True,'moduleInfoVersionsExportsIdentical':True,'originalObjectInputs':{rel:sha(P/rel) for rel in objects if rel!='./dma.o'},
  'commands':commands,'lab':str(run),'jobs':1,'fullMakeWorldRun':False,'scope':'Private diagnostic DMA startup intervention; reuse exact other production objects'}
 (O/'module-build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','moduleSHA256','moduleBytes')}))
