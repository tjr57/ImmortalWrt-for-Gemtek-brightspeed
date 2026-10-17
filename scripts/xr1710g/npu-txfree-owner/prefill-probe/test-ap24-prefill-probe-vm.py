"""Run actual AP24 and private probe startup functions in a real KASAN guest."""
from pathlib import Path
W=Path('/mnt/d/ChatGPT/XR1710G')
s=(W/'environment/test-npu-txfree-owner-vm.py').read_text()
s=s.replace("out=w/'development/npu-txfree-owner'", "out=w/'development/ap24/prefill-probe/vm';out.mkdir(parents=True,exist_ok=True)")
s=s.replace("boot-lab/npu-txfree-owner", "boot-lab/ap24-prefill-probe")
s=s.replace("names=['mt76_dma_rx_fill_buf'", "names=['mt76_dma_rx_queue_init','mt76_dma_rx_fill_buf'")
s=s.replace("h=(out/'after/mt76.h').read_text()", "h=(w/'development/npu-txfree-owner/after/mt76.h').read_text()")
s=s.replace('#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/netdevice.h>')
s=s.replace('struct mt76_dev { struct mt76_queue', 'struct mt76_dev { struct net_device *napi_dev; struct napi_struct napi[1]; struct mt76_queue')
s=s.replace('static char dummy[4096];', '''static unsigned int adds,enables;
static char dummy[4096];
#define netif_napi_add(d,n,p) do {adds++;} while(0)
#undef dev_info
#define dev_info(d,fmt,...) pr_info(fmt, ##__VA_ARGS__)
#define napi_enable(n) do {enables++;} while(0)''')
s=s.replace('allocs=writes=kicks=dequeues=wed_calls=sync_calls=npu_fill=npu_cleanup=frees=0;', 'allocs=writes=kicks=dequeues=wed_calls=sync_calls=npu_fill=npu_cleanup=frees=adds=enables=0;')
start=s.index('#if XR_BEFORE');end=s.index('#endif',start)+len('#endif')
s=s[:start]+'''  CHECK(untouched()&&ret==0,"NPU TXFREE ownership violated");
  pr_info("XR_OWNER_FIXED_PASS case=%d\\n",i);'''+s[end:]
s=s.replace(' /* Unchanged normal-DMA/WED/NPU-CPU-facing behavior', ''' setup(MT_NPU_Q_TXFREE(0));
 mt76_dma_rx_queue_init(&device,QID_ZERO,NULL);
 CHECK(adds==1&&enables==1,"NAPI lifecycle registration");
#if XR_BEFORE
 CHECK(writes==0&&allocs==0&&kicks==0,"AP24 must not publish startup buffers");
#else
 CHECK(writes==3&&allocs==3&&kicks==1,"probe must publish only at startup");
 CHECK(le32_to_cpu(descriptors[0].buf0)==0x94671000,"exact original page pool destination");
#endif
 { struct mt76_desc snapshot[4];unsigned int oldwrites=writes,oldallocs=allocs,oldkicks=kicks;
 memcpy(snapshot,descriptors,sizeof(snapshot));
 mt76_dma_rx_fill(&device,q,false);mt76_dma_rx_cleanup(&device,q);
 mt76_dma_rx_reset(&device,QID_ZERO);mt76_dma_rx_process(&device,q,64);
 CHECK(!memcmp(snapshot,descriptors,sizeof(snapshot))&&writes==oldwrites&&allocs==oldallocs&&kicks==oldkicks&&!dequeues&&!frees,"later ownership remains protected"); }
 pr_info("XR_PREFILL_STARTUP_PASS variant=%d\\n",XR_BEFORE);
 setup(0);mt76_dma_rx_queue_init(&device,QID_ZERO,NULL);
 CHECK(writes==3&&adds==1&&enables==1,"ordinary startup unchanged");
 pr_info("XR_PREFILL_ORDINARY_PASS\\n");
 /* Unchanged normal-DMA/WED/NPU-CPU-facing behavior''')
s=s.replace("source=(out/variant/'dma.c').read_text()", "source_path=w/('development/npu-txfree-owner/after/dma.c' if variant=='before' else 'development/ap24/prefill-probe/dma.c');source=source_path.read_text()")
s=s.replace("extracted='\\n'.join(fn(source,name) for name in names)", "ordered=[n for n in names if n!='mt76_dma_rx_queue_init']+(['mt76_dma_rx_prefill_probe'] if variant=='after' else [])+['mt76_dma_rx_queue_init'];extracted='\\n'.join(fn(source,name) for name in ordered)")
s=s.replace("sha(out/variant/'dma.c')", "sha(source_path)")
s=s.replace("text.count('XR_OWNER_OLD_REPRODUCED case=')==4 and text.count('XR_OWNER_FIXED_PASS case=')==4", "text.count('XR_OWNER_FIXED_PASS case=')==8 and text.count('XR_PREFILL_STARTUP_PASS variant=')==2 and text.count('XR_PREFILL_ORDINARY_PASS')==2")
s=s.replace("'oldOwnershipViolationsReproduced':4,'fixedOwnershipCases':4", "'startupVariants':2,'runtimeGuardCasesPerVariant':4")
s=s.replace("'Historical hardware root and firmware cache aliases remain unproven'", "'Transport/allocation fixtures; true PCIe prefetch and physical cache semantics are not emulated'")
exec(compile(s,__file__,'exec'))
