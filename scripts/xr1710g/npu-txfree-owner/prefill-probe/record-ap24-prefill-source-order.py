"""Record source-bound startup ordering and diagnostic scope, without device IO."""
from pathlib import Path
from datetime import datetime
import hashlib,json,re,difflib
W=Path('/mnt/d/ChatGPT/XR1710G');R=Path('/home/xrdev/projects/xr1710g/openwrt')
P=R/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791';O=W/'development/ap24/prefill-probe'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def fn(s,n):
 m=re.search(r'(?:static (?:inline )?)?(?:int|bool|void)\s*\n?'+n+r'\(',s);assert m
 a=s.index('{',m.start());e=a+1;depth=1
 while depth:depth+=(s[e]=='{')-(s[e]=='}');e+=1
 return s[m.start():e]
files=['dma.c','mt76.h','mt7996/dma.c','mt7996/init.c','mt7996/npu.c','mt7996/mmio.c','mt7996/mac.c']
t={f:(P/f).read_text() for f in files}
checks={}
q=fn(t['dma.c'],'mt76_dma_rx_queue_init');checks['queueFillBeforeNapiEnable']=q.index('mt76_dma_rx_fill_buf')<q.index('napi_enable')
q=fn(t['mt7996/dma.c'],'mt7996_dma_init');checks['initQueuesBeforeDmaEnable']=q.index('mt76_init_queues')<q.index('mt7996_dma_enable')
q=fn(t['mt7996/init.c'],'mt7996_init_hardware');checks['dmaInitBeforeMcuInit']=q.index('mt7996_dma_init')<q.index('mt7996_mcu_init')
q=fn(t['mt7996/init.c'],'mt7996_register_device');checks['hardwareInitBeforeNpuInit']=q.index('mt7996_init_hardware')<q.index('mt7996_npu_hw_init')
q=fn(t['mt7996/npu.c'],'__mt7996_npu_hw_init');checks['npuRxEventInitBeforeTxDoneStart']=q.index('mt7996_npu_rx_event_init')<q.index('mt7996_npu_tx_done_init')
q=fn(t['mt7996/npu.c'],'mt7996_npu_rx_event_init');checks['ringAddressBeforeDescriptorCountBeforePciePublication']=q.index('WLAN_FUNC_SET_WAIT_RX_RING_FOR_TXDONE_HW_BASE')<q.index('WLAN_FUNC_SET_WAIT_DESC')<q.index('WLAN_FUNC_SET_WAIT_PCIE_ADDR')
private=(O/'dma.c').read_text()
guards=['mt76_dma_rx_fill_buf','mt76_dma_rx_fill','mt76_dma_rx_cleanup','mt76_dma_rx_reset','mt76_dma_rx_process']
checks['allRuntimeGuardFunctionsByteIdentical']=all(fn(private,n)==fn(t['dma.c'],n) for n in guards)
old=(W/'development/npu-txfree-owner/before/dma.c').read_text()
checks['diagnosticPrefillExactOldFill']=fn(private,'mt76_dma_rx_prefill_probe').replace('mt76_dma_rx_prefill_probe(','mt76_dma_rx_fill_buf(',1)==fn(old,'mt76_dma_rx_fill_buf')
assert all(checks.values())
(O/'diagnostic-only-v2.patch').write_text(''.join(difflib.unified_diff(t['dma.c'].splitlines(True),private.splitlines(True),fromfile='a/dma.c',tofile='b/dma.c')))
result={'passed':True,'at':datetime.now().astimezone().isoformat(),'checks':checks,'sourceHashes':{f:sha(P/f) for f in files},
 'diagnosticSourceSHA256':sha(O/'dma.c'),'observations':[
 'Old generic startup fill publishes ndesc-1 host page-pool addresses before WFDMA starts and before NPU ring initialization.',
 'MT7996 explicitly configures TXFREE prefetch with val=4; exact internal cache/prefetch completion behavior is not established by this source.',
 'Firmware b432 initialization unconditionally overwrites descriptor addresses and private buffer IDs, so post-init mismatch cannot be explained by software source order alone.',
 'Normal NPU-mode interrupt mask excludes TXFREE_BAND0; full-reset path can schedule it later. AP24 runtime guards remain unchanged in this experiment.'],
 'experiment':'Only initial queue fill restored, later host refill/dequeue/reset still rejected. Two bounded physical trials followed by original AP24 restoration.',
 'limits':['No assertion that PCIe prefetch/writeback is physically observed','No assertion that separate historical Maple Oops shares the TXFREE cause']}
(O/'source-order.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':True,'checks':len(checks)}))
