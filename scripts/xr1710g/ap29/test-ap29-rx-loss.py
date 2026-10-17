from pathlib import Path
import subprocess,hashlib,json,os,re
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');base=w/'development/ap29';out=base/'rx-loss-audit/qa';out.mkdir(parents=True,exist_ok=True)
stubs=out/'stubs/linux';stubs.mkdir(parents=True,exist_ok=True)
for n in ['moduleparam.h','ktime.h']:(stubs/n).write_text('/* isolated kernel API fixture */\n')
oldtest=(w/'development/ap28/mesh-rx-audit/qa/test.c').read_text()
prefix=oldtest[:oldtest.index('struct vif')]
prefix=prefix.replace('typedef uint64_t u64;typedef uint32_t u32;','typedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;typedef int64_t s64;')
prefix+=oldtest[oldtest.index('static u64 ktime_get_mono_fast_ns'):oldtest.index('#include "../../mesh-rx-audit.h"')]
prefix+=r'''
#define NL80211_BAND_6GHZ 3
#define IEEE80211_NUM_TIDS 16
#define IEEE80211_QOS_CTL_TID_MASK 15
#define RX_FLAG_DECRYPTED 1
#define RX_FLAG_ONLY_MONITOR 4
#define RX_FLAG_8023 8
#define RX_FLAG_IV_STRIPPED 16
#define RX_FLAG_PN_VALIDATED 32
#define BUILD_BUG_ON(x) _Static_assert(!(x),"size")
struct mt76_wcid {u32 idx;bool rx_check_pn;u8 rx_key_pn[17][6];};
struct ieee80211_hdr {u32 frame_control,seq_ctrl;};
struct mt76_rx_status {struct mt76_wcid *wcid;u32 flag,band,phy_idx,qos_ctl,seqno,aggr,amsdu,first_amsdu,last_amsdu;u8 iv[6];};
struct sk_buff {struct mt76_rx_status cb[1];u32 len;struct ieee80211_hdr hdr;};
static struct ieee80211_hdr *mt76_skb_get_hdr(struct sk_buff *s){return &s->hdr;}
static bool ieee80211_is_frag(struct ieee80211_hdr *h){return h->seq_ctrl!=0;}
static bool ieee80211_is_first_frag(u32 s){return s==1;}
static bool ieee80211_is_mgmt(u32 f){return f&1;}
static bool ieee80211_has_tods(u32 f){return f&2;}
#include "../../rx-loss-audit.h"
'''
def function(p):
 s=p.read_text();a=s.index('static void\nmt76_check_ccmp_pn(');z=s.index('\nstatic void\nmt76_airtime_report',a);return s[a:z]
prefix+=function(base/'original-mac80211.c').replace('mt76_check_ccmp_pn','old_check')
prefix+=function(base/'patched-mac80211.c')
source=prefix+r'''
static struct mt76_wcid peer={.idx=7,.rx_check_pn=true};
static struct sk_buff packet={.cb={{.wcid=&peer,.band=3,.seqno=100,.flag=RX_FLAG_DECRYPTED}},.len=206};
static void pn(u8 *p,u64 x){for(int i=5;i>=0;i--){p[i]=x&255;x>>=8;}}
static void read_check(void){
 char b[PAGE_SIZE+16];memset(b,0x5a,sizeof(b));int n=xr_rx_loss_get(b,NULL);assert(n>0&&n<PAGE_SIZE&&b[n]==0);
 for(int i=PAGE_SIZE;i<(int)sizeof(b);i++)assert(b[i]==0x5a);
 unsigned en,count;unsigned long long total;assert(sscanf(b,"schema=1 enabled=%u total=%llu retained=%u",&en,&total,&count)==3);assert(count<=16);
 char *p=strchr(b,'\n');p=strchr(p+1,'\n')+1;unsigned rows=0;unsigned long long prev=0;
 while(*p){unsigned long long serial;assert(sscanf(p,"%llu",&serial)==1);assert(serial>prev);prev=serial;rows++;p=strchr(p,'\n');assert(p);p++;}
 assert(rows==count);if(rows)assert(prev==total);
}
static void *writer(void *v){(void)v;for(int i=0;i<10000;i++)xr_rx_loss_record(&packet,1,0,true);return NULL;}
int main(void){
 assert(!xr_rx_loss_audit);xr_rx_loss_record(&packet,1,0,true);assert(!xr_rx_loss_total);
 xr_rx_loss_audit=true;packet.cb->band=1;xr_rx_loss_record(&packet,1,0,true);assert(!xr_rx_loss_total);packet.cb->band=3;
 packet.cb->wcid=NULL;xr_rx_loss_record(&packet,1,0,true);assert(!xr_rx_loss_total);packet.cb->wcid=&peer;
 xr_rx_loss_record(&packet,2,-1,true);xr_rx_loss_record(&packet,2,17,true);xr_rx_loss_record(&packet,3,0,true);assert(!xr_rx_loss_total);
 pn(packet.cb->iv,100);xr_rx_loss_record(&packet,0,0,true);pn(peer.rx_key_pn[0],100);
 pn(packet.cb->iv,99);packet.cb->seqno=99;xr_rx_loss_record(&packet,2,0,false);
 assert(xr_rx_events[0].pn_delta==-1&&xr_rx_events[0].previous_seq==100&&xr_rx_events[0].previous_context==1&&xr_rx_events[0].context==2);
 pn(peer.rx_key_pn[0],101);xr_rx_loss_record(&packet,2,0,true);assert(xr_rx_events[1].previous_seq==65535&&xr_rx_events[1].previous_us==0);
 pn(packet.cb->iv,0);pn(peer.rx_key_pn[0],0xffffffffffffULL);xr_rx_loss_record(&packet,2,0,true);assert(xr_rx_events[2].pn_delta==-281474976710655LL);
 unsigned cases=0;
 for(int enabled=0;enabled<2;enabled++)for(int flags=0;flags<64;flags++)for(int frag=0;frag<3;frag++)for(int fc=0;fc<4;fc++)for(int relation=-1;relation<=1;relation++)for(int tid=0;tid<17;tid++){
  struct mt76_wcid a={.idx=7,.rx_check_pn=true},b;for(int i=0;i<17;i++)pn(a.rx_key_pn[i],100);b=a;
  struct sk_buff x={.cb={{.wcid=&a,.flag=flags,.qos_ctl=tid,.seqno=20,.band=3}},.len=206,.hdr={fc,frag}},y=x;
  pn(x.cb->iv,100+relation);y=x;y.cb->wcid=&b;xr_rx_loss_audit=enabled;
  old_check(&x);mt76_check_ccmp_pn(&y,true);
  assert(x.cb->flag==y.cb->flag&&!memcmp(a.rx_key_pn,b.rx_key_pn,sizeof(a.rx_key_pn)));cases++;
 }
 read_check();xr_rx_loss_audit=true;u64 initial=xr_rx_loss_total;
 pthread_t t[4];for(int i=0;i<4;i++)assert(!pthread_create(&t[i],NULL,writer,NULL));
 for(int i=0;i<1000;i++)read_check();for(int i=0;i<4;i++)pthread_join(t[i],NULL);assert(xr_rx_loss_total==initial+40000);read_check();
 xr_rx_loss_audit=false;xr_rx_loss_record(&packet,1,0,true);assert(xr_rx_loss_total==initial+40000);
 printf("PASS %u exact old/new PN decision comparisons; disabled/band/null/TID guards, PN delta boundaries, stale-counter rejection,16-row wrap,40000 concurrent events\n",cases);
}
'''
(out/'test.c').write_text(source)
args=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Wno-sign-compare','-Wno-misleading-indentation','-pthread','-I'+str(out/'stubs'),str(out/'test.c')]
cc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc'
commands=[['gcc',*args,'-fsanitize=address,undefined','-o',str(out/'test-native')],[str(out/'test-native')],[str(cc),*args,'-static','-o',str(out/'test-arm')],['qemu-aarch64',str(out/'test-arm')]]
logs=[]
for cmd in commands:
 p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=dict(os.environ,STAGING_DIR=str(r/'staging_dir')));logs.append({'command':cmd,'exitCode':p.returncode,'output':p.stdout});assert p.returncode==0,p.stdout
result={'passed':True,'headerSHA256':hashlib.sha256((base/'rx-loss-audit.h').read_bytes()).hexdigest(),'nativeASanUBSan':True,'ARMABI':True,'tests':logs,'limits':'Userspace fixtures test exact helper and old/new PN functions; real kernel build and live opt-in qualification still required.'}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(logs[-1]['output'],flush=True)
