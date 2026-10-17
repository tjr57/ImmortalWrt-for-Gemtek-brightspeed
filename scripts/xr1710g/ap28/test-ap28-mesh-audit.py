"""Run exact observer header natively (sanitizers) and as shipped ARM ABI."""
from pathlib import Path
import subprocess,hashlib,json,os
r=Path('/home/xrdev/projects/xr1710g/openwrt');base=Path('/mnt/d/ChatGPT/XR1710G/development/ap28');out=base/'mesh-rx-audit/qa';out.mkdir(exist_ok=True)
stubs=out/'stubs/linux';stubs.mkdir(parents=True,exist_ok=True)
for n in ['moduleparam.h','ktime.h']:(stubs/n).write_text('/* userspace API fixture */\n')
source=r'''#define _GNU_SOURCE
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>
#include <pthread.h>
#include <time.h>
#include <assert.h>
typedef uint64_t u64;typedef uint32_t u32;
#define PAGE_SIZE 4096
#define NSEC_PER_MSEC 1000000
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define DEFINE_SPINLOCK(x) pthread_mutex_t x=PTHREAD_MUTEX_INITIALIZER
#define spin_lock_irqsave(x,f) do {(f)=0;pthread_mutex_lock(x);} while(0)
#define spin_unlock_irqrestore(x,f) do {(void)(f);pthread_mutex_unlock(x);} while(0)
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define module_param_named(...)
#define module_param_cb(...)
#define MODULE_PARM_DESC(...)
struct kernel_param {int unused;};
struct kernel_param_ops {int (*get)(char *,const struct kernel_param *);};
struct vif {bool mesh;};struct dev {u32 ifindex;};struct sk_buff {u32 len;};
struct sdata {struct vif vif;struct dev *dev;};
struct ieee80211_rx_data {struct sdata *sdata;struct sk_buff *skb;};
struct ieee80211_sta {int placeholder;};
struct sta_info {struct ieee80211_sta sta;struct sdata *sdata;};
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-__builtin_offsetof(type,member)))
static bool ieee80211_vif_is_mesh(struct vif *v){return v->mesh;}
static u64 ktime_get_mono_fast_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (u64)t.tv_sec*1000000000+t.tv_nsec;}
static u64 div_u64(u64 n,u32 d){return n/d;}
static int scnprintf(char *b,size_t n,const char *f,...){va_list a;va_start(a,f);int r=vsnprintf(b,n,f,a);va_end(a);return r<0?r:(r>=(int)n?(int)n-1:r);}
#include "../../mesh-rx-audit.h"
static struct dev device={7};static struct sk_buff packet={96};static struct sdata iface={{true},&device};
static struct ieee80211_rx_data rx={&iface,&packet};
static void read_check(void){
 char b[PAGE_SIZE+16];memset(b,0x5a,sizeof(b));int n=xr_mesh_rx_drop_ops.get(b,NULL);assert(n>=0&&n<PAGE_SIZE&&b[n]==0);
 for(int i=PAGE_SIZE;i<(int)sizeof(b);i++)assert(b[i]==0x5a);
 unsigned long long total;unsigned enabled,retained;assert(sscanf(b,"schema=1 enabled=%u total=%llu retained=%u",&enabled,&total,&retained)==3);assert(retained<=32);
 char *p=strchr(b,'\n');assert(p);p=strchr(p+1,'\n');assert(p);p++;
 unsigned rows=0;unsigned long long previous=0;
 while(*p){unsigned long long serial,ms;unsigned reason,length,index,fast;int used=0;
  assert(sscanf(p,"%llu %llu 0x%x %u %u %u%n",&serial,&ms,&reason,&length,&index,&fast,&used)==6);
  assert(index==7&&length==96&&serial>previous&&fast<=1);previous=serial;rows++;p+=used;assert(*p=='\n');p++;
 }
 assert(rows==retained);if(rows)assert(previous==total);
}
static void *writer(void *v){uintptr_t id=(uintptr_t)v;for(int i=0;i<10000;i++)xr_mesh_rx_drop_record(&rx,0x10000+(u32)id,id&1);return NULL;}
int main(void){
 struct sta_info peer={.sdata=&iface};
 assert(!xr_mesh_rx_drop_audit);
 xr_mesh_rx_early_drop(&peer.sta,&packet,4);assert(!xr_mesh_rx_drop_total);
 xr_mesh_rx_drop_audit=true;xr_mesh_rx_early_drop(NULL,&packet,4);assert(!xr_mesh_rx_drop_total);
 iface.vif.mesh=false;xr_mesh_rx_early_drop(&peer.sta,&packet,4);assert(!xr_mesh_rx_drop_total);iface.vif.mesh=true;
 xr_mesh_rx_early_drop(&peer.sta,&packet,4);assert(xr_mesh_rx_drop_total==1&&xr_mesh_rx_drops[0].reason==0x20000004);read_check();
 xr_mesh_rx_early_drop(&peer.sta,&packet,32|64);assert(xr_mesh_rx_drop_total==2&&xr_mesh_rx_drops[1].reason==0x20000060);read_check();
 /* fixture reset, not an exposed production operation */
 xr_mesh_rx_drop_total=0;memset(xr_mesh_rx_drops,0,sizeof(xr_mesh_rx_drops));xr_mesh_rx_drop_audit=false;
 assert(!xr_mesh_rx_drop_audit);xr_mesh_rx_drop_record(&rx,1,false);assert(xr_mesh_rx_drop_total==0);read_check();
 xr_mesh_rx_drop_audit=true;iface.vif.mesh=false;xr_mesh_rx_drop_record(&rx,1,false);assert(!xr_mesh_rx_drop_total);iface.vif.mesh=true;
 struct ieee80211_rx_data missing={0};xr_mesh_rx_drop_record(&missing,1,false);assert(!xr_mesh_rx_drop_total);
 for(int i=0;i<100;i++)xr_mesh_rx_drop_record(&rx,0x10001,false);assert(xr_mesh_rx_drop_total==100);read_check();
 pthread_t threads[4];for(uintptr_t i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,writer,(void *)i));
 for(int i=0;i<1000;i++)read_check();for(int i=0;i<4;i++)pthread_join(threads[i],NULL);
 assert(xr_mesh_rx_drop_total==40100);read_check();xr_mesh_rx_drop_audit=false;xr_mesh_rx_drop_record(&rx,2,true);assert(xr_mesh_rx_drop_total==40100);read_check();
 puts("PASS disabled/non-Mesh/null guards, bounded wrap, chronological snapshots, concurrent writers/readers, disable retention");
}
'''
(out/'test.c').write_text(source)
args=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Wno-misleading-indentation','-pthread','-I'+str(out/'stubs'),str(out/'test.c')]
commands=[['gcc',*args,'-fsanitize=address,undefined','-o',str(out/'test-native')],[str(out/'test-native')]]
cc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc'
commands.extend([[str(cc),*args,'-static','-o',str(out/'test-arm')],['qemu-aarch64',str(out/'test-arm')]])
logs=[]
for cmd in commands:
    p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=dict(os.environ,STAGING_DIR=str(r/'staging_dir')));logs.append({'command':cmd,'exitCode':p.returncode,'output':p.stdout});assert p.returncode==0,p.stdout
result={'passed':True,'headerSHA256':hashlib.sha256((base/'mesh-rx-audit.h').read_bytes()).hexdigest(),'nativeASanUBSan':True,'actualARMABI':True,'concurrentWriters':4,'acceptedRecords':40100,'tests':logs,'limits':'Userspace synchronization fixtures validate recorder logic and bounds; kernel package compilation and live opt-in validation remain required.'}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='tests'}))
