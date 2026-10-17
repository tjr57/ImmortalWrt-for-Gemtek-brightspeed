"""Isolated single-intervention experiment; never edit production DMA sources."""
from pathlib import Path
from datetime import datetime
import hashlib,json,re,difflib
W=Path('/mnt/d/ChatGPT/XR1710G');R=Path('/home/xrdev/projects/xr1710g/openwrt')
P=R/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791'
O=W/'development/ap24/prefill-probe';O.mkdir(exist_ok=True)
assert not (O/'preparation.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def fn(s,n):
 m=re.search(r'(?:static (?:inline )?)?(?:int|bool|void)\s*\n?'+n+r'\(',s);assert m,n
 b=s.index('{',m.start());e=b+1;d=1
 while d:d+=(s[e]=='{')-(s[e]=='}');e+=1
 return s[m.start():e]+'\n'
before=(P/'dma.c').read_text();old=(W/'development/npu-txfree-owner/before/dma.c').read_text()
assert before==(W/'development/npu-txfree-owner/after/dma.c').read_text()
probe=fn(old,'mt76_dma_rx_fill_buf').replace('mt76_dma_rx_fill_buf(', 'mt76_dma_rx_prefill_probe(',1)
queue=fn(before,'mt76_dma_rx_queue_init')
call='\tmt76_dma_rx_fill_buf(dev, &dev->q_rx[qid], false);'
assert queue.count(call)==1
replacement='''\t/* Private diagnostic only: isolate startup prefill from later host writes. */
\tif (mt76_queue_is_npu_txfree(&dev->q_rx[qid])) {
\t\tstruct mt76_queue *q = &dev->q_rx[qid];

\t\tdev_info(dev->dev, "XR_PREFILL_PROBE before q=%d queued=%d head=%d ctrl=%08x\\n",
\t\t\tqid, q->queued, q->head, le32_to_cpu(q->desc[0].ctrl));
\t\tmt76_dma_rx_prefill_probe(dev, q, false);
\t\tdev_info(dev->dev, "XR_PREFILL_PROBE after q=%d queued=%d head=%d buf0=%08x ctrl=%08x\\n",
\t\t\tqid, q->queued, q->head, le32_to_cpu(q->desc[0].buf0),
\t\t\tle32_to_cpu(q->desc[0].ctrl));
\t} else {
\t\tmt76_dma_rx_fill_buf(dev, &dev->q_rx[qid], false);
\t}'''
newqueue=queue.replace(call,replacement)
after=before.replace(queue,probe+'\n'+newqueue)
for n in ('mt76_dma_rx_fill_buf','mt76_dma_rx_cleanup','mt76_dma_rx_reset','mt76_dma_rx_process'):
 assert fn(before,n)==fn(after,n)
(O/'dma.c').write_text(after)
(O/'diagnostic-only.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/dma.c',tofile='b/dma.c')))
report={'at':datetime.now().astimezone().isoformat(),'prepared':True,'sourceSHA256':sha(O/'dma.c'),
 'productionSourceSHA256':sha(P/'dma.c'),'probeFunctionSHA256':hashlib.sha256(probe.encode()).hexdigest(),
 'oldFillIdenticalAfterNameNormalization':probe.replace('mt76_dma_rx_prefill_probe(','mt76_dma_rx_fill_buf(',1)==fn(old,'mt76_dma_rx_fill_buf'),
 'runtimeFillCleanupResetPollGuardsUnchanged':True,'productionSourcesModified':False,
 'hypothesis':'Startup page-pool prefill alone publishes host buffers before NPU takeover; isolate from post-init CPU refill',
 'limits':['A positive probe identifies startup prefill as causal but does not directly observe PCIe prefetch/cache internals',
 'Bounded reboot-only experiment; no module unload or driver reset; firmware pool and page pool remain separate'],
 'buildAndVMRequired':True,'hardwareTrialRun':False}
(O/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
