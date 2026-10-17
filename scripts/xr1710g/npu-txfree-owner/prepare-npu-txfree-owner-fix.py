"""Prepare a narrow host queue-ownership correction from actual producer evidence."""
from pathlib import Path
from datetime import datetime
import difflib,hashlib,json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
out=w/'development/npu-txfree-owner';out.mkdir(exist_ok=True)
assert not (out/'preparation.json').exists()
p=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791'
evidence=json.loads((w/'development/npu-ap1-debugfs/live-epoch-1/analysis.json').read_text())
assert evidence['ordinaryRecoveryPassed'] and len(evidence['poolMismatchRows'])==1
before=(p/'dma.c').read_text();after=before
def replace_in_function(name,old,new):
    global after
    start=after.index('\n'+name+'(');left=after.index('{',start);depth=1;end=left+1
    while depth:
        depth+=(after[end]=='{')-(after[end]=='}');end+=1
    body=after[start:end];assert body.count(old)==1,name
    after=after[:start]+body.replace(old,new)+after[end:]
replace_in_function('mt76_dma_rx_fill_buf','\tif (!q->ndesc)\n\t\treturn 0;',
 '''\t/* Firmware owns TXFREE buffers and its private buffer-id table. Host
\t * page-pool refill would make the descriptor disagree with that table.
\t */
\tif (!q->ndesc || mt76_queue_is_npu_txfree(q))
\t\treturn 0;''')
replace_in_function('mt76_dma_rx_cleanup','\tif (!q->ndesc)\n\t\treturn;',
 '''\t/* No host buffers are allocated for the firmware-owned TXFREE ring. */
\tif (!q->ndesc || mt76_queue_is_npu_txfree(q))
\t\treturn;''')
replace_in_function('mt76_dma_rx_reset','\tif (!q->ndesc)\n\t\treturn;',
 '''\t/* Return before clearing DONE, walking descriptors or resetting WED.
\t * The NPU reset/hw-init path rebuilds this ring and its private table.
\t */
\tif (!q->ndesc || mt76_queue_is_npu_txfree(q))
\t\treturn;''')
replace_in_function('mt76_dma_rx_reset','\n\tif (mt76_queue_is_npu_txfree(q))\n\t\treturn;\n','\n')
replace_in_function('mt76_dma_rx_process','\tbool more;\n',
 '''\tbool more;

\t/* A stale/spurious host poll must not consume firmware-owned entries. */
\tif (mt76_queue_is_npu_txfree(q))
\t\treturn 0;
''')
for phase,text in (('before',before),('after',after)):
    d=out/phase;d.mkdir(exist_ok=True);(d/'dma.c').write_text(text)
    shutil.copy2(p/'mt76.h',d/'mt76.h');shutil.copy2(p/'dma.h',d/'dma.h')
diff=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/dma.c',tofile='b/dma.c'))
header='''From: XR1710G local development
Subject: [PATCH] wifi: mt76: leave NPU TXFREE buffers to firmware

The NPU TXFREE ring uses standard Wi-Fi descriptors but firmware manages
their backing buffers through a private buffer-id table. It does not use
the host RX page pool. Prevent generic refill, dequeue/cleanup and reset
from touching those entries. Keep ordinary DMA, WED and NPU CPU-facing
receive queues unchanged. NAPI registration remains symmetric with cleanup.

AP1 producer instrumentation observed len20/header92 and a table-derived
buffer8a500080 against descriptor94671000. AP2's32 normal samples matched.
This establishes a hardware ownership inconsistency; the exact writer and
historical root still require controlled before/after hardware validation.
No buffer-length clamping, warning removal, firmware change or NPU default.

'''
name='9999s-XR-preserve-firmware-owned-TXFREE-rings.patch'
(out/name).write_text(header+diff)
target=r/'package/kernel/mt76/patches'/name
assert not target.exists() or target.read_bytes()==(out/name).read_bytes()
shutil.copy2(out/name,target)
make=r/'package/kernel/mt76/Makefile';s=make.read_text();assert 'PKG_RELEASE=13' in s
make.write_text(s.replace('PKG_RELEASE=13','PKG_RELEASE=14'))
subprocess.run(['git','add','--','package/kernel/mt76/Makefile',str(target.relative_to(r))],cwd=r,check=True)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
report={'at':datetime.now().astimezone().isoformat(),'prepared':True,'patch':name,'patchSHA256':sha(target),
        'sourceBeforeSHA256':sha(out/'before/dma.c'),'sourceAfterSHA256':sha(out/'after/dma.c'),
        'producerEvidence':'development/npu-ap1-debugfs/live-epoch-1/analysis.json',
        'hostOwnershipDefectCandidate':True,'historicalRootProven':False,
        'VMPreflashStillRequired':True,'built':False,'deployed':False}
(out/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
