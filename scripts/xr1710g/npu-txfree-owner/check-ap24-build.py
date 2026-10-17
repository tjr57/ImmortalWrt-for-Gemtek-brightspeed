"""Bind AP24 to the changed-function guest test and inherited packed/ABI gates."""
from pathlib import Path
import hashlib,json,subprocess,sys
from elftools.elf.elffile import ELFFile
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap24'
source=(w/'environment/check-ap23-build.py').read_text().replace('ap23','ap24')
anchor="exec(compile(script,'ap24-inherited-packed-file-verification','exec'),{})"
assert source.count(anchor)==1
source=source.replace(anchor,"script=script.replace('be5ce791-r13','be5ce791-r14').replace('mt76r13','mt76r14')\n"+anchor)
exec(compile(source,'AP24-inherited-build-checks','exec'),{})
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ld=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581';mt=ld/'mt76-2026.09.01~be5ce791'
owner=w/'development/npu-txfree-owner';vm=json.loads((owner/'vm-result-latest.json').read_text())
assert vm['passed'] and sha(mt/'dma.c')==sha(owner/'after/dma.c')==vm['sourceBindings']['after']['sourceSHA256']
assert sha(mt/'mt76.h')==sha(owner/'after/mt76.h')
def sections(path):
    with path.open('rb') as f:
        e=ELFFile(f);assert e['e_machine']=='EM_AARCH64'
        return {s.name:hashlib.sha256(s.data()).hexdigest() for s in e.iter_sections() if s['sh_flags']&4 and s['sh_size']}
packed=r/'build_dir/target-aarch64_cortex-a53_musl/root-airoha/lib/modules/6.18.54/mt76.ko'
code=sections(mt/'mt76.ko');assert code and code==sections(packed)
report={'passed':True,'checks':['rebuilt dma.c and predicate header equal the actual VM-tested after source',
 'packaged ARM mt76 executable sections equal compiled module','old-code negative controls failed ownership in the real guest'],
 'dmaSourceSHA256':sha(mt/'dma.c'),'headerSHA256':sha(mt/'mt76.h'),'packedMt76SHA256':sha(packed),
 'vmResultSHA256':sha(owner/'vm-result-latest.json'),'historicalRootProven':False}
(out/'ownership-compiled-qa.json').write_text(json.dumps(report,indent=2)+'\n')
gate=json.loads((out/'boot-lab/result.json').read_text());gate['scope'].append('boot-loaded mt76 NPU TXFREE ownership guard')
gate['ownershipVM']='development/npu-txfree-owner/vm-result-latest.json';gate['ownershipCompiledQA']='development/ap24/ownership-compiled-qa.json'
gate['limits']=['Real guest executes exact changed DMA bodies; DMA/allocation/dequeue and queue layout are fixtures',
                'AN7581/MT7996 physical DMA/cache semantics need hardware validation']
(out/'boot-lab/result.json').write_text(json.dumps(gate,indent=2)+'\n')
script=(w/'environment/run-ap22-defaults-qa.py').read_text().replace('development/ap22','development/ap24')
script=script.replace("['python3',str(r/'scripts/test-xr1710g-ap-defaults.py')]","['sudo','-n','python3',str(r/'scripts/test-xr1710g-ap-defaults.py')]")
exec(compile(script,'AP24-actual-shipped-defaults','exec'),{})
print(json.dumps({'passed':True,'packedMt76SHA256':sha(packed),'VMChangedSourcesMatched':True}))
