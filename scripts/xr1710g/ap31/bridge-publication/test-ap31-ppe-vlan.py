"""Run actual candidate action/context functions with modeled kernel APIs."""
from pathlib import Path
import subprocess,json,hashlib,os,fcntl
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap31/ppe-vlan'
r=Path('/home/xrdev/projects/xr1710g/openwrt');tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
t=(out/'airoha_ppe.c').read_text();old=(out/'before-airoha_ppe.c').read_text()
def fn(s,name):
 a=s.index('static bool '+name+'(');b=s.index('\n}\n',a)+3;return s[a:b]
actions=fn(t,'airoha_ppe_l2_actions');context=fn(t,'airoha_ppe_l2_context')
a=old.index('\tflow_action_for_each(i, act, &rule->action) {',old.index('static int airoha_ppe_flow_offload_replace('))
b=old.index('\n\tif (offload_type != PPE_PKT_TYPE_BRIDGE',a)
old_loop=old[a:b]
mock=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <arpa/inet.h>
typedef uint16_t u16;
#define VLAN_VID_MASK 4095
#define ETH_P_8021Q 0x8100
#define BRIDGE_VLAN_INFO_UNTAGGED 4
#define FLOW_DISSECTOR_KEY_VLAN 0
#define FLOW_ACT_MANGLE_HDR_TYPE_ETH 1
#define PPE_PKT_TYPE_BRIDGE 7
enum {FLOW_ACTION_REDIRECT,FLOW_ACTION_VLAN_POP,FLOW_ACTION_VLAN_PUSH,
 FLOW_ACTION_CSUM,FLOW_ACTION_PPPOE_PUSH,FLOW_ACTION_MANGLE,FLOW_ACTION_DROP};
struct net {uint64_t net_cookie;};
struct net_device {int ifindex;struct net*net;struct net_device*master;
 bool port,vlan,filter,member;u16 pvid,proto,flags;};
struct ethhdr {unsigned char h_dest[6],h_source[6];};
struct airoha_flow_data {struct ethhdr eth;struct {struct {u16 id,proto;}hdr[2];int num;}vlan;struct {int num;u16 sid;}pppoe;};
struct airoha_l2_flow_key {uint64_t net_cookie;uint32_t ingress_ifindex,bridge_ifindex;u16 vid,vlan_proto,ingress_tagged;unsigned char dest[6],source[6];};
struct flow_action_entry {int id;struct net_device*dev;struct {u16 vid,proto,prio;}vlan;struct {u16 sid;}pppoe;struct {int htype;}mangle;};
struct flow_action {int num_entries;struct flow_action_entry entries[6];};
struct meta {int ingress_ifindex;};struct vlan {u16 vlan_id,vlan_tpid;};
struct flow_rule {struct flow_action action;bool exact,tagged;struct meta meta;struct vlan vlan[2];};
struct flow_match_meta {struct meta*key;};struct flow_match_vlan {struct vlan*key,*mask;};
struct bridge_vlan_info {u16 flags;};
static struct net ns={1},other_ns={2};
static struct net_device in,outdev,bridge,other_bridge;
#define flow_action_for_each(i,a,f) for((i)=0;(i)<(f)->num_entries&&((a)=&(f)->entries[i],1);(i)++)
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
static bool flow_rule_match_key(struct flow_rule*r,int key){(void)key;return r->tagged;}
static void flow_rule_match_meta(struct flow_rule*r,struct flow_match_meta*m){m->key=&r->meta;}
static void flow_rule_match_vlan(struct flow_rule*r,struct flow_match_vlan*m){m->key=&r->vlan[0];m->mask=&r->vlan[1];}
static bool airoha_ppe_l2_rule_exact(struct flow_rule*r){return r->exact;}
static struct net*dev_net(struct net_device*d){return d->net;}
static struct net_device*dev_get_by_index_rcu(struct net*n,int i){return n==in.net&&i==in.ifindex?&in:NULL;}
static bool is_vlan_dev(struct net_device*d){return d->vlan;}
static bool netif_is_bridge_port(struct net_device*d){return d->port;}
static struct net_device*airoha_ppe_foe_get_bridge_master_rcu(struct net_device*d){return d->master;}
static bool net_eq(struct net*a,struct net*b){return a==b;}
static bool br_vlan_enabled(struct net_device*d){return d->filter;}
static int br_vlan_get_proto(struct net_device*d,u16*p){*p=d->proto;return 0;}
static int br_vlan_get_pvid_rcu(struct net_device*d,u16*p){*p=d->pvid;return !d->pvid;}
static int br_vlan_get_info_rcu(struct net_device*d,u16 vid,struct bridge_vlan_info*i){i->flags=d->flags;return !d->member||vid!=50;}
static void ether_addr_copy(unsigned char*a,const unsigned char*b){memcpy(a,b,6);}
static void airoha_ppe_flow_mangle_eth(struct flow_action_entry*a,struct ethhdr*b){(void)a;(void)b;}
static int old_interpret(struct flow_rule*rule,struct airoha_flow_data*result){
 struct airoha_flow_data data={0};struct net_device*odev=NULL;
 int offload_type=PPE_PKT_TYPE_BRIDGE,i;struct flow_action_entry*act;
OLD_LOOP
 (void)odev;*result=data;return 0;
}
'''.replace('OLD_LOOP',old_loop)
tests=r'''
static int checks,accepted;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed line %d\n",__LINE__);return 1;}checks++;}while(0)
static struct flow_action_entry action(int id){struct flow_action_entry a={0};a.id=id;a.dev=&outdev;a.vlan.vid=50;a.vlan.proto=htons(ETH_P_8021Q);a.pppoe.sid=7;return a;}
/* Independent packet-stack evaluator, including terminal redirect semantics. */
static bool software(struct flow_rule*r,bool tagged,int priority,int*depth,int*vid,int*prio){
 int vs[8]={50},ps[8]={priority},n=tagged?1:0;
 for(int i=0;i<r->action.num_entries;i++){
  struct flow_action_entry*a=&r->action.entries[i];
  if(a->id==FLOW_ACTION_VLAN_PUSH){for(int j=n;j>0;j--){vs[j]=vs[j-1];ps[j]=ps[j-1];}vs[0]=a->vlan.vid;ps[0]=a->vlan.prio;n++;}
  else if(a->id==FLOW_ACTION_VLAN_POP){if(!n)return false;for(int j=0;j<n-1;j++){vs[j]=vs[j+1];ps[j]=ps[j+1];}n--;}
  else if(a->id==FLOW_ACTION_REDIRECT){if(!a->dev)return false;*depth=n;*vid=n?vs[0]:0;*prio=n?ps[0]:0;return true;}
  else return false;
 }
 return false;
}
static void reset(struct flow_rule*r){
 memset(r,0,sizeof(*r));*r=(struct flow_rule){.exact=true,.meta={11}};
 bridge=(struct net_device){.ifindex=10,.net=&ns,.filter=true,.proto=ETH_P_8021Q};
 other_bridge=(struct net_device){.ifindex=20,.net=&ns};
 in=(struct net_device){.ifindex=11,.net=&ns,.master=&bridge,.port=true,.member=true,.pvid=50};
 outdev=(struct net_device){.ifindex=12,.net=&ns,.master=&bridge,.port=true,.member=true,.pvid=50,.flags=BRIDGE_VLAN_INFO_UNTAGGED};
 r->vlan[0]=(struct vlan){50,htons(ETH_P_8021Q)};r->vlan[1]=(struct vlan){VLAN_VID_MASK,htons(0xffff)};
 r->action.num_entries=1;r->action.entries[0]=action(FLOW_ACTION_REDIRECT);
}
int main(void){
 struct flow_rule r;struct airoha_flow_data data;struct airoha_l2_flow_key key,untagged_key;
 reset(&r);data=(struct airoha_flow_data){0};key=(struct airoha_l2_flow_key){0};
 CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(key.vid==50&&key.ingress_tagged==0&&data.vlan.num==0);untagged_key=key;
 r.tagged=true;r.action.num_entries=2;r.action.entries[0]=action(FLOW_ACTION_VLAN_POP);r.action.entries[1]=action(FLOW_ACTION_REDIRECT);key=(struct airoha_l2_flow_key){0};
 CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(key.ingress_tagged==1&&memcmp(&key,&untagged_key,sizeof(key)));
 outdev.flags=0;CHECK(!airoha_ppe_l2_context(&r,&outdev,&data,&key));
 r.action.num_entries=3;r.action.entries[1]=action(FLOW_ACTION_VLAN_PUSH);r.action.entries[2]=action(FLOW_ACTION_REDIRECT);
 CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(data.vlan.num==1&&data.vlan.hdr[0].id==50);
 for(int mutation=0;mutation<13;mutation++){
  reset(&r);
  switch(mutation){
   case 0:in.member=false;break;case 1:outdev.member=false;break;case 2:in.pvid=0;break;
   case 3:in.pvid=51;break;case 4:bridge.proto=0x88a8;break;case 5:outdev.master=&other_bridge;break;
   case 6:outdev.net=&other_ns;break;case 7:in.port=false;break;case 8:outdev.port=false;break;
   case 9:in.vlan=true;break;case 10:outdev.vlan=true;break;case 11:r.exact=false;break;case 12:r.meta.ingress_ifindex=99;break;
  }
  CHECK(!airoha_ppe_l2_context(&r,&outdev,&data,&key));
 }
 reset(&r);CHECK(!airoha_ppe_l2_context(&r,&in,&data,&key));CHECK(!airoha_ppe_l2_context(&r,NULL,&data,&key));
 reset(&r);bridge.filter=false;CHECK(airoha_ppe_l2_context(&r,&outdev,&data,&key));CHECK(key.vid==0);r.tagged=true;CHECK(!airoha_ppe_l2_context(&r,&outdev,&data,&key));
 /* Old production parser ignores priority and executes actions after redirect. */
 reset(&r);r.action.num_entries=2;r.action.entries[0]=action(FLOW_ACTION_VLAN_PUSH);r.action.entries[0].vlan.prio=7;r.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(old_interpret(&r,&data)==0&&data.vlan.hdr[0].id==50);CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 r.action.entries[0]=action(FLOW_ACTION_REDIRECT);r.action.entries[1]=action(FLOW_ACTION_VLAN_PUSH);
 CHECK(old_interpret(&r,&data)==0&&data.vlan.num==1);CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 r.action.entries[0]=action(FLOW_ACTION_VLAN_POP);r.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(old_interpret(&r,&data)==0);CHECK(!airoha_ppe_l2_actions(&r,50,false,true,&data));
 /* Enumerate short action programs; every accepted case must produce the
  * same concrete packet stack as software, for every ingress priority. */
 for(int len=0;len<=5;len++){
  int total=1;for(int j=0;j<len;j++)total*=7;
  for(int code=0;code<total;code++){
   reset(&r);r.action.num_entries=len;int v=code;
   for(int j=0;j<len;j++){r.action.entries[j]=action(v%7);v/=7;}
   for(int tagged=0;tagged<2;tagged++)for(int untagged=0;untagged<2;untagged++){
    data=(struct airoha_flow_data){0};
    bool ok=airoha_ppe_l2_actions(&r,50,tagged,untagged,&data);
    checks++;
    if(!ok)continue;
    accepted++;
    for(int p=0;p<8;p++){int depth,vid,prio;CHECK(software(&r,tagged,p,&depth,&vid,&prio));CHECK(depth==data.vlan.num);CHECK(depth==!untagged);if(depth){CHECK(vid==data.vlan.hdr[0].id);CHECK(prio==0);}}
   }
  }
 }
 CHECK(accepted==4);
 reset(&r);r.action.num_entries=2;r.action.entries[0]=action(FLOW_ACTION_VLAN_PUSH);r.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 for(int p=1;p<8;p++){r.action.entries[0].vlan.prio=p;CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));}
 r.action.entries[0].vlan.prio=0;r.action.entries[0].vlan.vid=51;CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 r.action.entries[0].vlan.vid=50;r.action.entries[0].vlan.proto=htons(0x88a8);CHECK(!airoha_ppe_l2_actions(&r,50,false,false,&data));
 reset(&r);CHECK(!airoha_ppe_l2_actions(&r,4095,false,true,&data));r.action.entries[0].dev=NULL;CHECK(!airoha_ppe_l2_actions(&r,0,false,true,&data));
 printf("%d checks; %d canonical programs accepted; packet-stack equivalence and context negatives passed\n",checks,accepted);return 0;
}
'''
(out/'contract.c').write_text(mock+actions+context+tests)
cc=tc/'bin/aarch64-openwrt-linux-musl-gcc'
(out/'Makefile').write_text(f'''all: contract-native contract-arm
contract-native: contract.c
\tgcc -Wall -Wextra -Werror -g -fsanitize=address,undefined contract.c -o $@
contract-arm: contract.c
\t{cc} -Wall -Wextra -Werror -Os contract.c -o $@
''')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p=subprocess.run(['make','-j12'],cwd=out,env=dict(os.environ,STAGING_DIR=str(tc)),capture_output=True,text=True)
(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
logs={}
for name,cmd in [('native',[str(out/'contract-native')]),('ARM',['qemu-aarch64-static','-L',str(r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'),str(out/'contract-arm')])]:
 p=subprocess.run(cmd,capture_output=True,text=True);(out/(name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(name,p.stderr);logs[name]=p.stdout.strip()
replace=t[t.index('static int airoha_ppe_flow_offload_replace('):]
assert replace.index('!airoha_ppe_l2_context(')<replace.index('airoha_ppe_foe_entry_prepare(')
result={'passed':True,'candidateSHA256':hashlib.sha256(t.encode()).hexdigest(),'nativeASanUBSan':True,'actualArmABI':True,'kernelAPIsModeled':True,'oldProductionActionLoopNegativeControls':True,'independentPacketStackModel':True,'policyConcurrencyOrHardwareQualified':False,'logs':logs}
(out/'qa.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
