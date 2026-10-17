"""Private AP24 single-intervention image; exact qualified recovery and producer."""
from pathlib import Path
W=Path('/mnt/d/ChatGPT/XR1710G')
s=(W/'environment/build-ap24-owner-trace.py').read_text()
s=s.replace("OUT=W/'development/ap24/owner-trace'", "OUT=W/'development/ap24/prefill-probe'")
s=s.replace("ID='ap24-npu-owner-trace1'", "ID='ap24-npu-startup-prefill-probe1'")
needle="marker={'schema':1"
insert='''module_build=j(OUT/'module-build.json');assert module_build['passed']
assert module_build['VMReportSHA256']==sha(OUT/'vm/vm-result-latest.json')
assert module_build['sourceSHA256']==sha(OUT/'dma.c')
module_path='lib/modules/6.18.54/mt76.ko'
assert sha(OUT/'mt76-prefill-probe.ko')==module_build['moduleSHA256']
shutil.copyfile(OUT/'mt76-prefill-probe.ko',root/module_path)
bindings['singleStartupPrefill']={'VMReportSHA256':module_build['VMReportSHA256'],'moduleSHA256':module_build['moduleSHA256'],'sourceSHA256':module_build['sourceSHA256']}
'''
s=s.replace(needle,insert+needle)
s=s.replace("Observe fixed host-driver ownership with the same producer hook used before the fix", "Single startup prefill intervention with all AP24 runtime ownership guards retained; same producer hook")
s=s.replace("assert set(changed)==set(prior['changedFiles'])", "assert set(changed)==set(prior['changedFiles'])|{module_path}")
s=s.replace("assert all(before[p]==after[p] for p in before if p.startswith", "assert all(before[p]==after[p] for p in before if p!=module_path and p.startswith")
s=s.replace("assert all(sha(root/p)==h for p,h in packed.items())", "assert all(sha(root/p)==h for p,h in packed.items() if p!=module_path);assert len(packed)==39")
s=s.replace("'productionModulesByteIdentical':True,'AP24PackedFilesMatched':len(packed)", "'productionModulesByteIdentical':False,'AP24PackedFilesMatched':len(packed)-1,'onlyChangedProductionModule':module_path")
s=s.replace("Reuses exact previously compiled and guest-qualified binary payloads; AP24 already built -j12", "Recompiled private DMA startup intervention with exact original object/ABI inputs; other AP24/recovery/producer binaries unchanged")
s=s.replace("post-fix producer ownership samples", "bounded startup-prefill causal intervention")
exec(compile(s,__file__,'exec'))
