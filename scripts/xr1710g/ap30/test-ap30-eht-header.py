from pathlib import Path
import hashlib,json,subprocess,os,re
r=Path('/home/xrdev/projects/xr1710g/openwrt');base=Path('/mnt/d/ChatGPT/XR1710G/development/ap30');out=base/'eht-header/qa';out.mkdir(parents=True,exist_ok=True)
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54/include/linux/ieee80211.h'
def extract(s,name):
 a=s.index(name+'(');a=s.rfind('\nstatic ',0,a)+1;z=s.index('\n}',a)+2;return s[a:z]+'\n'
source=r'''#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint16_t __le16;typedef uint32_t u32;typedef uint32_t __le32;
#define __packed __attribute__((packed))
#define BIT(n) (1U<<(n))
#define cpu_to_le16(x) ((__le16)(x))
#define BUILD_BUG_ON(x) _Static_assert(!(x),"contract")
#define IEEE80211_FCTL_FTYPE 0x000c
#define IEEE80211_FTYPE_MGMT 0x0000
#define IEEE80211_FCTL_TODS 0x0100
#define IEEE80211_FCTL_MOREFRAGS 0x0400
#define IEEE80211_SCTL_FRAG 0x000f
#define IEEE80211_NUM_TIDS 16
#define IEEE80211_QOS_CTL_TID_MASK 15
#define RX_FLAG_DECRYPTED BIT(1)
#define RX_FLAG_ONLY_MONITOR BIT(2)
#define RX_FLAG_IV_STRIPPED BIT(4)
#define RX_FLAG_PN_VALIDATED BIT(10)
#define RX_FLAG_RADIOTAP_TLV_AT_END BIT(20)
#define RX_FLAG_RADIOTAP_HE BIT(26)
#define RX_FLAG_RADIOTAP_HE_MU BIT(27)
#define RX_FLAG_8023 BIT(30)
struct ieee80211_hdr {__le16 frame_control,duration_id;u8 a1[6],a2[6],a3[6];__le16 seq_ctrl;u8 a4[6];};
struct ieee80211_radiotap_he {u8 data[12];};struct ieee80211_radiotap_he_mu {u8 data[12];};
struct mt76_wcid {bool rx_check_pn;u8 rx_key_pn[17][6];};
struct mt76_rx_status {struct mt76_wcid *wcid;u32 flag;u8 qos_ctl,iv[6];};
struct sk_buff {u8 *data,*mac_header;struct mt76_rx_status cb[1];};
static u8 *skb_mac_header(struct sk_buff *s){return s->mac_header;}
static void xr_rx_loss_record(struct sk_buff *s,u32 reason,int tid,bool napi){(void)s;(void)reason;(void)tid;(void)napi;}
'''
rt=(r/'staging_dir/target-aarch64_cortex-a53_musl/usr/include/mac80211/net/ieee80211_radiotap.h').read_text()
for n in ['ieee80211_radiotap_eht_usig','ieee80211_radiotap_eht']:
 a=rt.index('struct '+n+' {');z=rt.index('} __packed;',a)+len('} __packed;');source+=rt[a:z]+'\n'
for n in ['ieee80211_has_tods','ieee80211_has_morefrags','ieee80211_is_mgmt','ieee80211_is_first_frag','ieee80211_is_frag']:source+=extract(k.read_text(),n)
source+=extract((base/'original-mt76.h').read_text(),'mt76_skb_get_hdr').replace('mt76_skb_get_hdr','old_hdr')
source+=extract((base/'patched-mt76.h').read_text(),'mt76_skb_get_hdr').replace('mt76_skb_get_hdr','new_hdr')
pnfunc=extract((base/'pn-check-source.c').read_text(),'mt76_check_ccmp_pn')
source+=pnfunc.replace('mt76_check_ccmp_pn','old_check').replace('mt76_skb_get_hdr','old_hdr')
source+=pnfunc.replace('mt76_check_ccmp_pn','new_check').replace('mt76_skb_get_hdr','new_hdr')
source+=r'''
static void pn(u8 *p,uint64_t value){for(int i=5;i>=0;i--){p[i]=value&255;value>>=8;}}
static uint64_t value(u8 *p){uint64_t v=0;for(int i=0;i<6;i++)v=(v<<8)|p[i];return v;}
static void packet(struct sk_buff *s,u8 *memory,struct mt76_wcid *w,u16 fc,u8 tid,uint64_t number,bool eht){
 const size_t usig=sizeof(struct ieee80211_radiotap_eht_usig),ehtlen=sizeof(struct ieee80211_radiotap_eht)+sizeof(u32),prefix=8+usig+ehtlen;
 assert(prefix==64);memset(memory,0,256);s->data=memory;s->mac_header=memory+(eht?prefix:0);
 *s->cb=(struct mt76_rx_status){.wcid=w,.flag=RX_FLAG_DECRYPTED|RX_FLAG_IV_STRIPPED|(eht?RX_FLAG_RADIOTAP_TLV_AT_END:0),.qos_ctl=tid};pn(s->cb->iv,number);
 if(eht){memory[0]=33;memory[2]=usig;memory[4+usig]=34;memory[6+usig]=ehtlen;}
 ((struct ieee80211_hdr *)s->mac_header)->frame_control=fc;
}
int main(void){
 unsigned cases=0;u8 a[256],b[256];struct sk_buff x,y;
 for(int tid=0;tid<16;tid++)for(int other=0;other<16;other++){
  if(tid==other)continue;
  struct mt76_wcid old={.rx_check_pn=true},fixed=old;for(int i=0;i<17;i++){pn(old.rx_key_pn[i],99);pn(fixed.rx_key_pn[i],99);}
  packet(&x,a,&old,0x0388,other,101,true);packet(&y,b,&fixed,0x0388,other,101,true);
  assert(old_hdr(&x)==x.data&&new_hdr(&y)==y.mac_header);assert(ieee80211_is_mgmt(((struct ieee80211_hdr *)old_hdr(&x))->frame_control));
  old_check(&x,true);new_check(&y,true);assert(value(old.rx_key_pn[16])==101&&value(fixed.rx_key_pn[16])==99);
  packet(&x,a,&old,0x0388,tid,100,true);packet(&y,b,&fixed,0x0388,tid,100,true);old_check(&x,true);new_check(&y,true);
  assert(x.cb->flag&RX_FLAG_ONLY_MONITOR);assert(!(y.cb->flag&RX_FLAG_ONLY_MONITOR));assert(value(fixed.rx_key_pn[tid])==100);
  /* Equal/older PN on the SAME TID remains rejected, in both plain and EHT frames. */
  for(int eht=0;eht<2;eht++)for(int delta=-1;delta<=0;delta++){
   packet(&y,b,&fixed,0x0388,tid,100+delta,eht);new_check(&y,true);assert(y.cb->flag&RX_FLAG_ONLY_MONITOR);assert(value(fixed.rx_key_pn[tid])==100);
  }
  /* Real robust management still uses slot16 and keeps replay protection. */
  packet(&y,b,&fixed,0x00d0,0,102,true);new_check(&y,true);assert(!(y.cb->flag&RX_FLAG_ONLY_MONITOR));assert(value(fixed.rx_key_pn[16])==102);
  packet(&y,b,&fixed,0x00d0,0,102,true);new_check(&y,true);assert(y.cb->flag&RX_FLAG_ONLY_MONITOR);
  cases++;
 }
 for(int he=0;he<2;he++)for(int mu=0;mu<2;mu++)for(int tlv=0;tlv<2;tlv++)for(int bytes=4;bytes<=128;bytes+=4){
  memset(a,0,sizeof(a));x.data=a;x.mac_header=a+12*he+12*mu+bytes;x.cb->flag=(he?RX_FLAG_RADIOTAP_HE:0)|(mu?RX_FLAG_RADIOTAP_HE_MU:0)|(tlv?RX_FLAG_RADIOTAP_TLV_AT_END:0);
  assert(new_hdr(&x)==(tlv?x.mac_header:a+12*he+12*mu));if(!tlv)assert(new_hdr(&x)==old_hdr(&x));cases++;
 }
 printf("PASS %u cases:240 cross-TID false-replay negative controls; equal/older replay still rejected; robust management slot preserved;256 header-layout combinations\n",cases);
}
'''
(out/'test.c').write_text(source)
args=['-std=gnu11','-O1','-g','-Wall','-Wextra',str(out/'test.c')];cc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-gcc'
commands=[['gcc',*args,'-fsanitize=address,undefined','-o',str(out/'test-native')],[str(out/'test-native')],[str(cc),*args,'-static','-o',str(out/'test-arm')],['qemu-aarch64',str(out/'test-arm')]];logs=[]
for cmd in commands:
 p=subprocess.run(cmd,capture_output=True,text=True,env=dict(os.environ,STAGING_DIR=str(r/'staging_dir')));logs.append({'command':cmd,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert p.returncode==0,p.stdout+p.stderr
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'passed':True,'oldHeaderSHA256':sha(base/'original-mt76.h'),'headerSHA256':sha(base/'patched-mt76.h'),'pnSourceSHA256':sha(base/'pn-check-source.c'),'nativeASanUBSan':True,'actualARMABI':True,'tests':logs,'limits':'Exact header/PN/helper functions in isolated skb/metadata fixtures; actual MT7996 firmware and over-air frame contents not emulated.'}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(logs[-1]['stdout'])
