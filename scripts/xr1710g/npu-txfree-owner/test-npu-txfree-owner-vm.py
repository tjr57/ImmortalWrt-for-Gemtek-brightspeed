"""Real guest kernel executes exact before/after DMA functions with transport fixtures."""
from pathlib import Path
from datetime import datetime
import subprocess,json,hashlib,shutil,gzip,re,fcntl
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/npu-txfree-owner'
lab=Path('/home/xrdev/projects/xr1710g/boot-lab/npu-txfree-owner');lab.mkdir(exist_ok=True)
k=lab.parent/'npu-addresses/linux-6.18.54';stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
run=lab/stamp;run.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=['mt76_dma_rx_fill_buf','mt76_dma_rx_fill','mt76_dma_rx_cleanup','mt76_dma_rx_reset','mt76_dma_rx_process']
def fn(text,name):
    m=re.search(r'(?:static (?:inline )?)?(?:int|bool|void)\s*\n?'+name+r'\(',text);assert m,name
    begin=text.index('{',m.start());depth=1;end=begin+1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[m.start():end]+'\n'
h=(out/'after/mt76.h').read_text();macros=h[h.index('#define MT_QFLAG_WED_RING'):h.index('\nstruct mt76_dev;')]
enum=h[h.index('enum mt76_wed_type {'):h.index('\n};',h.index('enum mt76_wed_type {'))+3]
predicates='\n'.join(fn(h,name) for name in ['mt76_queue_is_wed_tx_free','mt76_queue_is_wed_rro','mt76_queue_is_wed_rro_ind','mt76_queue_is_wed_rro_rxdmad_c','mt76_queue_is_wed_rx','mt76_queue_is_npu','mt76_queue_is_npu_txfree'])
prefix=r'''// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/skbuff.h>
#include <linux/bitfield.h>
struct mt76_desc { __le32 buf0,ctrl,buf1,info; };
struct mt76_queue { spinlock_t lock; u32 flags; int ndesc,buf_size,buf_offset,queued,head,tail;
 struct mt76_desc *desc; struct sk_buff *rx_head; };
struct mt76_dev;
struct drv { void (*rx_rro_ind_process)(struct mt76_dev *,void *);
 bool (*rx_check)(struct mt76_dev *,void *,int);
 void (*rx_skb)(struct mt76_dev *,int,struct sk_buff *,u32 *); };
struct mt76_dev { struct mt76_queue q_rx[1]; struct { struct {bool active;} wed;} mmio; struct drv *drv; bool npu_active; };
struct mt76_queue_buf { dma_addr_t addr; int len; bool skip_unmap; };
enum mt76_rxq_id { QID_ZERO };
static unsigned int allocs,writes,kicks,dequeues,wed_calls,sync_calls,npu_fill,npu_cleanup,frees;
static char dummy[4096];
#define MT_DMA_CTL_DMA_DONE BIT(31)
#define mtk_wed_device_active(p) ((p)->active)
#define mt76_npu_device_active(d) ((d)->npu_active)
'''
stubs=r'''
/* Only transport, DMA allocation and queue dequeue are fixtures. Spinlocks,
 * skb types, module lifetime and memory safety run in the real guest kernel. */
static void *mt76_get_page_pool_buf(struct mt76_queue *q,int *off,int size){allocs++;*off=0;return dummy;}
#define virt_to_head_page(b) (b)
#define page_pool_get_dma_addr(p) ((dma_addr_t)0x94671000)
static void mt76_put_page_pool_buf(void *b,bool direct){frees++;}
static int mt76_dma_add_rx_buf(struct mt76_dev *d,struct mt76_queue *q,struct mt76_queue_buf *b,void *data){
 q->desc[q->head].buf0=cpu_to_le32(b->addr);q->desc[q->head].ctrl=cpu_to_le32(b->len<<16);
 q->head=(q->head+1)%q->ndesc;q->queued++;writes++;return 0;
}
static void mt76_dma_kick_queue(struct mt76_dev *d,struct mt76_queue *q){kicks++;}
static void *mt76_dma_dequeue(struct mt76_dev *d,struct mt76_queue *q,bool flush,int *len,u32 *info,bool *more,bool *drop){dequeues++;return NULL;}
static void mt76_npu_queue_cleanup(struct mt76_dev *d,struct mt76_queue *q){npu_cleanup++;}
static void mt76_wed_dma_setup(struct mt76_dev *d,struct mt76_queue *q,bool reset){wed_calls++;}
static void mt76_dma_sync_idx(struct mt76_dev *d,struct mt76_queue *q){sync_calls++;}
static void mt76_npu_fill_rx_queue(struct mt76_dev *d,struct mt76_queue *q){npu_fill++;}
static int mt76_dma_read_dma_idx(struct mt76_queue *q,int fallback){return fallback;}
static void mt76_add_fragment(struct mt76_dev *d,struct mt76_queue *q,void *data,int len,bool more,u32 info,bool direct){}
'''
tests=r'''
static struct mt76_dev device;
static struct mt76_desc descriptors[4];
static void setup(u32 flags){int i;memset(&device,0,sizeof(device));memset(descriptors,0,sizeof(descriptors));
 spin_lock_init(&device.q_rx[0].lock);device.npu_active=true;device.q_rx[0].ndesc=4;
 device.q_rx[0].buf_size=2048;device.q_rx[0].flags=flags;device.q_rx[0].desc=descriptors;
 for(i=0;i<4;i++){descriptors[i].buf0=cpu_to_le32(0x8a500080+2048*i);descriptors[i].ctrl=cpu_to_le32(0x07000100);}
 allocs=writes=kicks=dequeues=wed_calls=sync_calls=npu_fill=npu_cleanup=frees=0;
}
static bool untouched(void){int i;
 if(allocs||writes||kicks||dequeues||wed_calls||sync_calls||npu_fill||npu_cleanup||frees||device.q_rx[0].head||device.q_rx[0].queued)return false;
 for(i=0;i<4;i++)if(le32_to_cpu(descriptors[i].buf0)!=0x8a500080+2048*i||le32_to_cpu(descriptors[i].ctrl)!=0x07000100)return false;
 return true;
}
#define CHECK(c,n) do {if(!(c)){pr_err("XR_OWNER_FAIL %s\n",n);return -EINVAL;}}while(0)
static int __init test_init(void){int i,ret;struct mt76_queue*q=&device.q_rx[0];
 for(i=0;i<4;i++){
  setup(MT_NPU_Q_TXFREE(0));
  if(i==0)ret=mt76_dma_rx_fill(&device,q,false);
  else if(i==1){mt76_dma_rx_cleanup(&device,q);ret=0;}
  else if(i==2){mt76_dma_rx_reset(&device,QID_ZERO);ret=0;}
  else ret=mt76_dma_rx_process(&device,q,64);
#if XR_BEFORE
  CHECK(!untouched(),"old code unexpectedly preserved ownership");
  if(i==0||i==3)CHECK(writes==3&&allocs==3&&le32_to_cpu(descriptors[0].buf0)==0x94671000,"old refill counterexample");
  if(i==2)CHECK(le32_to_cpu(descriptors[0].ctrl)==MT_DMA_CTL_DMA_DONE,"old reset clears descriptor before reject");
  pr_info("XR_OWNER_OLD_REPRODUCED case=%d\n",i);
#else
  CHECK(untouched()&&ret==0,"NPU TXFREE ownership violated");
  pr_info("XR_OWNER_FIXED_PASS case=%d\n",i);
#endif
 }
 /* Unchanged normal-DMA/WED/NPU-CPU-facing behavior is compared across builds. */
 setup(0);ret=mt76_dma_rx_fill(&device,q,false);CHECK(ret==3&&writes==3&&kicks==1,"normal RX refill");
 pr_info("XR_OWNER_CONTROL_PASS normal_refill\n");
 setup(MT_WED_Q_TXFREE);CHECK(!mt76_queue_is_npu_txfree(q),"WED type collision");mt76_dma_rx_reset(&device,QID_ZERO);CHECK(wed_calls==1,"WED reset preserved");
 pr_info("XR_OWNER_CONTROL_PASS wed_reset\n");
 setup(MT_NPU_Q_RX(0));mt76_dma_rx_reset(&device,QID_ZERO);CHECK(npu_cleanup==1&&npu_fill==1&&sync_calls==1,"NPU host receive preserved");
 pr_info("XR_OWNER_CONTROL_PASS npu_host_rx\n");
 setup(0);q->ndesc=0;ret=mt76_dma_rx_fill(&device,q,false);mt76_dma_rx_cleanup(&device,q);mt76_dma_rx_reset(&device,QID_ZERO);
 CHECK(ret==0&&!allocs&&!dequeues&&!wed_calls,"unallocated queue");
 pr_info("XR_OWNER_CONTROL_PASS unallocated\n");
 pr_info("XR_OWNER_ALL_PASS before=%d\n",XR_BEFORE);return 0;
}
static void __exit test_exit(void){pr_info("XR_OWNER_UNLOADED\n");}
module_init(test_init);module_exit(test_exit);MODULE_LICENSE("GPL");
'''
hashes={};modules=[]
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for variant in ('before','after'):
        build=run/variant;build.mkdir();source=(out/variant/'dma.c').read_text()
        extracted='\n'.join(fn(source,name) for name in names)
        (build/'owner.c').write_text(prefix+macros+enum+predicates+stubs+extracted+tests)
        (build/'Makefile').write_text('obj-m += owner.o\nccflags-y += -DXR_BEFORE='+str(int(variant=='before'))+'\n')
        log=out/(stamp+'-'+variant+'-build.log')
        with log.open('w') as f:p=subprocess.run(['make','-C',str(k),'M='+str(build),'-j12','modules'],stdout=f,stderr=subprocess.STDOUT)
        assert p.returncode==0,str(log)
        hashes[variant]={'sourceSHA256':sha(out/variant/'dma.c'),'functionHashes':{name:hashlib.sha256(fn(source,name).encode()).hexdigest() for name in names},'guestModuleSHA256':sha(build/'owner.ko')}
        modules.append(build/'owner.ko')
root=run/'root'
for d in ('bin','dev','proc','sys','tmp'):(root/d).mkdir(parents=True,exist_ok=True)
shutil.copy2('/bin/busybox',root/'bin/busybox')
for name in ('sh','mount','insmod','rmmod','poweroff'):(root/'bin'/name).symlink_to('busybox')
for variant,module in zip(('before','after'),modules):shutil.copy2(module,root/'bin'/('owner-'+variant+'.ko'))
(root/'init').write_text('''#!/bin/sh
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
fail() { echo XR_OWNER_GUEST_FAIL; poweroff -f; }
insmod /bin/owner-before.ko || fail
rmmod owner || fail
insmod /bin/owner-after.ko || fail
rmmod owner || fail
echo XR_OWNER_GUEST_PASS
poweroff -f
''');(root/'init').chmod(0o755)
paths=['.']+[str(p.relative_to(root)) for p in sorted(root.rglob('*'))]
archive=subprocess.run(['cpio','--null','-o','--format=newc','--owner=0:0'],cwd=root,input=('\0'.join(paths)+'\0').encode(),capture_output=True,check=True).stdout
initrd=run/'guest.cpio.gz'
with gzip.open(initrd,'wb') as f:f.write(archive)
log=out/(stamp+'-guest.log')
cmd=['sudo','-n','timeout','55','qemu-system-x86_64','-accel','tcg','-cpu','qemu64','-smp','2','-m','1024','-nodefaults','-display','none','-serial','stdio','-monitor','none','-no-reboot','-run-with','user=xrdev','-kernel',str(k/'arch/x86/boot/bzImage'),'-initrd',str(initrd),'-append','console=ttyS0 rdinit=/init nokaslr panic=1 panic_on_oops=1 panic_on_warn=1']
with log.open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
text=log.read_text(errors='replace');bad=re.findall(r'^.*(?:WARNING:|BUG:|KASAN:|Kernel panic|XR_OWNER_FAIL|XR_OWNER_GUEST_FAIL).*$',text,re.M)
passed=p.returncode==0 and not bad and text.count('XR_OWNER_OLD_REPRODUCED case=')==4 and text.count('XR_OWNER_FIXED_PASS case=')==4 and text.count('XR_OWNER_CONTROL_PASS ')==8 and text.count('XR_OWNER_UNLOADED')==2 and 'XR_OWNER_GUEST_PASS' in text
report={'passed':passed,'at':datetime.now().astimezone().isoformat(),'sourceBindings':hashes,'kernelSHA256':sha(k/'arch/x86/boot/bzImage'),'testSourceSHA256':sha(Path(__file__)),
        'oldOwnershipViolationsReproduced':4,'fixedOwnershipCases':4,'unchangedControlCasesPerVariant':4,'unexpectedFaults':bad,'exitCode':p.returncode,
        'actualFunctionBodies':names,'noHostNetworkOrDisks':True,'jobs':12,'log':str(log),
        'limits':['Exact function bodies and predicates; queue layout/transport/allocation/dequeue are fixtures',
                  'Real Linux kernel locking/module lifecycle/KASAN; no actual NPU or PCIe/cache emulation',
                  'Historical hardware root and firmware cache aliases remain unproven']}
(out/(stamp+'-vm-result.json')).write_text(json.dumps(report,indent=2)+'\n');(out/'vm-result-latest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report));raise SystemExit(0 if passed else 1)
