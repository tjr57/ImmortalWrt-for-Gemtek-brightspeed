"""Ensure the final preparer regenerates the exact tested private source."""
from pathlib import Path
import tempfile,contextlib,io,hashlib,json
W=Path('/mnt/d/ChatGPT/XR1710G');O=W/'development/ap24/prefill-probe'
path=W/'environment/prepare-ap24-prefill-probe.py'
s=path.read_text();temp=Path(tempfile.mkdtemp(prefix='ap24-prefill-regenerate-',dir='/home/xrdev/projects/xr1710g/boot-lab'))
needle="O=W/'development/ap24/prefill-probe';O.mkdir(exist_ok=True)";assert s.count(needle)==1
s=s.replace(needle,'O=Path('+repr(str(temp))+');O.mkdir(exist_ok=True)')
with contextlib.redirect_stdout(io.StringIO()):exec(compile(s,str(path),'exec'),{'__file__':str(path)})
assert (temp/'dma.c').read_bytes()==(O/'dma.c').read_bytes()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={'passed':True,'exactTestedSourceRegenerated':True,'sourceSHA256':sha(O/'dma.c'),'preparerSHA256':sha(path),'temporaryLab':str(temp),'noDeviceOperations':True}
(O/'regeneration-qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
