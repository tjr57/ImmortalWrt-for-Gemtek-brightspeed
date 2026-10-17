"""Exact candidate functions, old-code controls; kernel APIs are modeled."""
from pathlib import Path
import fcntl, hashlib, json, os, subprocess

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
out = w / 'development/ap31/ppe-context'
parent = w / 'development/ap31/ppe-revocation'
tc = r / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
root = r / 'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'
source = (out / 'airoha_ppe.c').read_text()
old = (parent / 'airoha_ppe.c').read_text()

def fn(s, signature):
    a = s.index(signature)
    return s[a:s.index('\n}\n', a) + 3]

mock = (w / 'development/ap31/ppe-vlan/contract.c').read_text().split('static void airoha_ppe_flow_mangle_eth')[0]
mock = mock.replace('bool port,vlan,filter,member;', 'bool port,vlan,filter,member,running,carrier,mst; unsigned long policy; unsigned int state;')
mock += r'''
#define BR_STATE_FORWARDING 3
#define BR_ISOLATED (1UL<<16)
#define BR_PORT_LOCKED (1UL<<21)
#define BR_PORT_MAB (1UL<<22)
#define BR_VLAN_TUNNEL (1UL<<13)
#define BR_PROXYARP (1UL<<8)
#define BR_PROXYARP_WIFI (1UL<<10)
#define BR_NEIGH_SUPPRESS (1UL<<15)
#define BR_NEIGH_VLAN_SUPPRESS (1UL<<23)
#define BR_MRP_AWARE (1UL<<17)
#define BR_FDB_LOCAL 0
#define BR_FDB_LOCKED 1
#define READ_ONCE(x) (x)
#define EXPORT_SYMBOL_GPL(x)
struct net_bridge {int unused;};
struct net_bridge_port {struct net_device *dev;};
struct net_bridge_fdb_entry {unsigned long flags;struct net_bridge_port *dst;bool present,expired;};
static struct net_bridge br;
static struct net_bridge_port srcport,dstport;
static struct net_bridge_fdb_entry entries[2];
static bool netif_running(struct net_device*d){return d->running;}
static bool netif_carrier_ok(struct net_device*d){return d->carrier;}
static unsigned int br_port_get_stp_state(struct net_device*d){return d->state;}
static bool br_port_flag_is_set(struct net_device*d,unsigned long f){return d->policy&f;}
static bool br_mst_enabled(struct net_device*d){return d->mst;}
static bool netif_is_bridge_master(const struct net_device*d){return d==&bridge;}
static bool is_valid_ether_addr(const unsigned char*a){return !(a[0]&1)&&!!memcmp(a,(unsigned char[6]){0},6);}
static struct net_bridge*netdev_priv(const struct net_device*d){(void)d;return &br;}
static bool test_bit(int i,const unsigned long*f){return *f&(1UL<<i);}
static bool has_expired(struct net_bridge*b,struct net_bridge_fdb_entry*f){(void)b;return f->expired;}
static struct net_bridge_fdb_entry*br_fdb_find_rcu(struct net_bridge*b,const unsigned char*a,u16 vid){
 (void)b;
 if((vid!=0&&vid!=50)||a[5]<1||a[5]>2)return NULL;
 struct net_bridge_fdb_entry*f=&entries[a[5]-1];return f->present?f:NULL;
}
struct flow_cls_offload {struct {unsigned int chain_index;void *extack;} common;};
#define NL_SET_ERR_MSG_MOD(a,b) ((void)(a),(void)(b))
'''
fdb = fn((out / 'br_fdb.c').read_text(), 'bool br_fdb_forward_to_rcu(')
port = fn(source, 'static bool airoha_ppe_l2_port_eligible(')
actions = fn(source, 'static bool airoha_ppe_l2_actions(')
context = fn(source, 'static bool airoha_ppe_l2_context(')
oldcontext = fn(old, 'static bool airoha_ppe_l2_context(').replace('airoha_ppe_l2_context(', 'old_context(', 1)
a = source.index('\t/* FOE has no classifier chain/goto context. */')
b = source.index('\tif (!airoha_ppe_rule_has_single_redirect', a)
chain = 'static int chain_guard(struct flow_cls_offload*f){\n' + source[a:b] + '\nreturn 0;\n}\n'
tests = r'''
static int checks;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed line %d\n",__LINE__);return 1;}checks++;}while(0)
static struct flow_rule rule;
static struct airoha_flow_data data;
static struct airoha_l2_flow_key key;
static struct flow_action_entry action(int id){return (struct flow_action_entry){.id=id,.dev=&outdev,.vlan={50,htons(ETH_P_8021Q),0}};}
static void reset(void){
 rule=(struct flow_rule){.exact=true,.meta={11}};
 bridge=(struct net_device){.ifindex=10,.net=&ns,.filter=true,.proto=ETH_P_8021Q};
 other_bridge=(struct net_device){.ifindex=20,.net=&ns};
 in=(struct net_device){.ifindex=11,.net=&ns,.master=&bridge,.port=true,.member=true,.pvid=50,.running=true,.carrier=true,.state=BR_STATE_FORWARDING};
 outdev=in;outdev.ifindex=12;outdev.flags=BRIDGE_VLAN_INFO_UNTAGGED;
 rule.vlan[0]=(struct vlan){50,htons(ETH_P_8021Q)};rule.vlan[1]=(struct vlan){VLAN_VID_MASK,htons(0xffff)};
 rule.action.num_entries=1;rule.action.entries[0]=action(FLOW_ACTION_REDIRECT);
 data=(struct airoha_flow_data){.eth={{2,0,0,0,0,2},{2,0,0,0,0,1}}};
 key=(struct airoha_l2_flow_key){0};srcport.dev=&in;dstport.dev=&outdev;
 entries[0]=(struct net_bridge_fdb_entry){.present=true,.dst=&srcport};
 entries[1]=(struct net_bridge_fdb_entry){.present=true,.dst=&dstport};
}
int main(void){
 reset();CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(key.vid==50&&key.ingress_tagged==0);
 /* Previous candidate accepts blocked/learning ports and incompatible policy. */
 for(int side=0;side<2;side++)for(int state=0;state<=4;state++){
  reset();struct net_device*d=side?&outdev:&in;d->state=state;
  CHECK(old_context(&rule,&outdev,&data,&key));
  CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key)==(state==BR_STATE_FORWARDING));
 }
 for(int side=0;side<2;side++)for(int bit=0;bit<25;bit++){
  reset();struct net_device*d=side?&outdev:&in;d->policy=1UL<<bit;
  bool unsupported=d->policy&(BR_ISOLATED|BR_PORT_LOCKED|BR_PORT_MAB|BR_VLAN_TUNNEL|BR_PROXYARP|BR_PROXYARP_WIFI|BR_NEIGH_SUPPRESS|BR_NEIGH_VLAN_SUPPRESS|BR_MRP_AWARE);
  CHECK(old_context(&rule,&outdev,&data,&key));CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key)==!unsupported);
 }
 for(int side=0;side<2;side++)for(int fault=0;fault<7;fault++){
  reset();struct net_bridge_fdb_entry*f=&entries[side];
  switch(fault){case 0:f->present=false;break;case 1:f->flags=1UL<<BR_FDB_LOCAL;break;
   case 2:f->flags=1UL<<BR_FDB_LOCKED;break;case 3:f->expired=true;break;
   case 4:f->dst=NULL;break;case 5:f->dst=side?&srcport:&dstport;break;
   case 6:(side?data.eth.h_dest:data.eth.h_source)[0]=1;break;}
  CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 }
 for(int side=0;side<2;side++)for(int carrier=0;carrier<2;carrier++){
  reset();struct net_device*d=side?&outdev:&in;if(carrier)d->carrier=false;else d->running=false;
  CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 }
 reset();bridge.mst=true;CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 reset();rule.tagged=true;rule.action.num_entries=2;rule.action.entries[0]=action(FLOW_ACTION_VLAN_POP);rule.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(key.ingress_tagged==1&&data.vlan.num==0);
 outdev.flags=0;rule.action.num_entries=3;rule.action.entries[1]=action(FLOW_ACTION_VLAN_PUSH);rule.action.entries[2]=action(FLOW_ACTION_REDIRECT);
 CHECK(old_context(&rule,&outdev,&data,&key));CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 /* Canonical action equivalence alone did not imply bridge PCP preservation. */
 for(int pcp=0;pcp<8;pcp++)for(int dei=0;dei<2;dei++){int bridge_tci=(pcp<<13)|(dei<<12)|50;
  int explicit_pop_push_tci=50;CHECK((bridge_tci==explicit_pop_push_tci)==(!pcp&&!dei));}
 reset();outdev.flags=0;rule.action.num_entries=2;rule.action.entries[0]=action(FLOW_ACTION_VLAN_PUSH);rule.action.entries[1]=action(FLOW_ACTION_REDIRECT);
 CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(data.vlan.num==1&&data.vlan.hdr[0].id==50);
 for(int fault=0;fault<13;fault++){
  reset();switch(fault){case 0:in.member=false;break;case 1:outdev.member=false;break;case 2:in.pvid=0;break;
   case 3:in.pvid=51;break;case 4:bridge.proto=0x88a8;break;case 5:outdev.master=&other_bridge;break;
   case 6:outdev.net=&other_ns;break;case 7:in.port=false;break;case 8:outdev.port=false;break;
   case 9:in.vlan=true;break;case 10:outdev.vlan=true;break;case 11:rule.exact=false;break;case 12:rule.meta.ingress_ifindex=99;break;}
  CHECK(!airoha_ppe_l2_context(&rule,&outdev,&data,&key));
 }
 reset();bridge.filter=false;CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key));CHECK(key.vid==0);
 struct flow_cls_offload f={0};CHECK(chain_guard(&f)==0);
 for(unsigned int i=1;i<65536;i++){f.common.chain_index=i;CHECK(chain_guard(&f)==-EOPNOTSUPP);}
 f.common.chain_index=UINT32_MAX;CHECK(chain_guard(&f)==-EOPNOTSUPP);
 printf("%d checks; prior context negatives reproduced; new FDB/STP/policy/tag/chain guards passed\n",checks);return 0;
}
'''
(out / 'context-contract.c').write_text(mock + fdb + port + actions + oldcontext + context + chain + tests)
cc = tc / 'bin/aarch64-openwrt-linux-musl-gcc'
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for compiler, args, output in [('gcc', ['-g', '-fsanitize=address,undefined'], 'context-native'), (str(cc), ['-Os'], 'context-arm')]:
        p = subprocess.run([compiler, '-Wall', '-Wextra', '-Werror', *args, str(out / 'context-contract.c'), '-o', str(out / output)], capture_output=True, text=True, env=dict(os.environ, STAGING_DIR=str(tc)))
        assert p.returncode == 0, p.stderr
logs = {}
for name, cmd in [('native', [str(out / 'context-native')]), ('ARM', ['qemu-aarch64-static', '-L', str(root), str(out / 'context-arm')])]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    (out / (name + '.log')).write_text(p.stdout + p.stderr)
    assert p.returncode == 0, (name, p.stdout, p.stderr)
    logs[name] = p.stdout.strip()
unchanged = {}
for signature in ['static bool airoha_ppe_l2_actions(', 'static bool airoha_ppe_l2_rule_exact(', 'static bool airoha_ppe_skb_l2_key(', 'static bool airoha_ppe_l2_snapshot(', 'static void airoha_ppe_l2_revoke(', 'static int\nairoha_ppe_foe_l2_flow_commit_entry(']:
    a, b = fn(source, signature), fn(old, signature)
    assert a == b, signature
    unchanged[signature] = hashlib.sha256(a.encode()).hexdigest()
report = {'passed': True, 'candidateSHA256': hashlib.sha256(source.encode()).hexdigest(),
          'nativeASanUBSan': True, 'actualArmABI': True, 'kernelAPIsModeled': True,
          'oldCodeNegativeControls': True, 'logs': logs, 'unchangedFunctions': unchanged,
          'contextEvidenceSupersedesPriorContext': True, 'fullPolicyOrHardwareQualified': False}
(out / 'qa.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'unchangedFunctions'}))
