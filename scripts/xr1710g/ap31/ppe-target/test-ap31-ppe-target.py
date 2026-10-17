"""Actual candidate helper, production action loop and prepare ordering tests."""
from pathlib import Path
import subprocess,json,hashlib,fcntl,os
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap31/ppe-target'
r=Path('/home/xrdev/projects/xr1710g/openwrt');tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
cc=tc/'bin/aarch64-openwrt-linux-musl-gcc';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=(out/'before.c').read_text();after=(out/'after.c').read_text()
def fn(s,name):
 start=s.index('static bool '+name+'(');opening=s.index('{',start);depth=0
 for i in range(opening,len(s)):
  depth+=(s[i]=='{')-(s[i]=='}')
  if depth==0:return s[start:i+1]
 raise ValueError(name)
helper=fn(after,'airoha_ppe_rule_has_single_redirect')
# Check real production call ordering; don't use a test-only guard.
replace=after[after.index('static int airoha_ppe_flow_offload_replace('):]
assert replace.index('if (!airoha_ppe_rule_has_single_redirect(rule))')<replace.index('airoha_ppe_foe_entry_prepare(')
prepare=after[after.index('static int airoha_ppe_foe_entry_prepare('):after.index('static int airoha_ppe_foe_entry_set_ipv4_tuple(')]
assert prepare.index('*egress_dev = NULL;')<prepare.index('if (!netdev)')<prepare.index('dsa_port = airoha_get_dsa_port(&netdev);')
start=before.index('\tflow_action_for_each(i, act, &rule->action) {',before.index('static int airoha_ppe_flow_offload_replace('))
stop=before.index('\n\tif (offload_type != PPE_PKT_TYPE_BRIDGE',start)
old_loop=before[start:stop]
mock=r'''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <arpa/inet.h>
enum { FLOW_ACTION_MANGLE, FLOW_ACTION_REDIRECT, FLOW_ACTION_CSUM,
 FLOW_ACTION_VLAN_PUSH,FLOW_ACTION_VLAN_POP,FLOW_ACTION_PPPOE_PUSH,FLOW_ACTION_DROP };
enum {PPE_PKT_TYPE_BRIDGE=7,FLOW_ACT_MANGLE_HDR_TYPE_ETH=3,ETH_P_8021Q=0x8100};
struct net_device {int id;};
struct flow_action_entry {int id;struct net_device*dev;struct {int htype;}mangle;
 struct {uint16_t proto,vid;}vlan;struct {uint16_t sid;}pppoe;};
struct flow_action {int num_entries;struct flow_action_entry entries[8];};
struct flow_rule {struct flow_action action;};
#define flow_action_for_each(i,a,f) for((i)=0;(i)<(f)->num_entries&&((a)=&(f)->entries[i],1);(i)++)
static void airoha_ppe_flow_mangle_eth(struct flow_action_entry*a,int*b){(void)a;(void)b;}
static int old_interpret(struct flow_rule*rule,struct net_device**output){
 struct {int eth;struct {int num;struct {uint16_t id,proto;}hdr[2];}vlan;struct {int num;uint16_t sid;}pppoe;}data={0};
 int offload_type=PPE_PKT_TYPE_BRIDGE,i;struct flow_action_entry*act;struct net_device*odev=NULL;
OLD_LOOP
 *output=odev;return 0;
}
'''.replace('OLD_LOOP',old_loop)
test=r'''
int main(void){
 struct net_device a={1},b={2};struct net_device*out;struct flow_rule rule={0};int cases=0;
 #define CHECK(x) do{assert(x);cases++;}while(0)
 CHECK(old_interpret(&rule,&out)==0&&out==NULL);
 CHECK(!airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.num_entries=1;rule.action.entries[0].id=FLOW_ACTION_CSUM;
 CHECK(old_interpret(&rule,&out)==0&&out==NULL);
 CHECK(!airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.entries[0].id=FLOW_ACTION_REDIRECT;
 CHECK(old_interpret(&rule,&out)==0&&out==NULL);
 CHECK(!airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.entries[0].dev=&a;
 CHECK(airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.num_entries=2;rule.action.entries[1].id=FLOW_ACTION_REDIRECT;rule.action.entries[1].dev=&b;
 CHECK(old_interpret(&rule,&out)==0&&out==&b);
 CHECK(!airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.entries[1].dev=&a;CHECK(!airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.entries[0].dev=NULL;CHECK(!airoha_ppe_rule_has_single_redirect(&rule));
 rule.action.entries[0].dev=&a;rule.action.entries[1].id=FLOW_ACTION_CSUM;
 CHECK(airoha_ppe_rule_has_single_redirect(&rule));
 // The target check does not claim to validate other actions: the existing
 // action switch still rejects unsupported DROP after this narrow predicate.
 rule.action.entries[1].id=FLOW_ACTION_DROP;
 CHECK(airoha_ppe_rule_has_single_redirect(&rule));CHECK(old_interpret(&rule,&out)==-EOPNOTSUPP);
 // Exhaust all redirect positions in short lists, including duplicate and
 // null targets. Unrelated accepted checksum entries keep the target count.
 for(int n=0;n<=8;n++)for(int mask=0;mask<(1<<n);mask++)for(int nulls=0;nulls<2;nulls++){
  rule=(struct flow_rule){0};rule.action.num_entries=n;int count=0;
  for(int i=0;i<n;i++) {rule.action.entries[i].id=(mask&(1<<i))?FLOW_ACTION_REDIRECT:FLOW_ACTION_CSUM;
   rule.action.entries[i].dev=nulls?NULL:&a;count+=!!(mask&(1<<i));}
  CHECK(airoha_ppe_rule_has_single_redirect(&rule)==(count==1&&!nulls));
 }
 printf("%d actual helper/action-loop egress checks passed\n",cases);return 0;
}
'''
(out/'contract.c').write_text(mock+helper+test)
(out/'Makefile').write_text(f'''all: contract-host contract-arm
contract-host: contract.c
\tgcc -Wall -Wextra -Werror -g -fsanitize=address,undefined contract.c -o $@
contract-arm: contract.c
\t{cc} -Wall -Wextra -Werror -Os contract.c -o $@
''')
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p=subprocess.run(['make','-j12'],cwd=out,env=dict(os.environ,STAGING_DIR=str(tc)),capture_output=True,text=True)
(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
logs={}
for name,cmd in [('native',[str(out/'contract-host')]),('ARM',['qemu-aarch64-static','-L',str(r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'),str(out/'contract-arm')])]:
 p=subprocess.run(cmd,capture_output=True,text=True);(out/(name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr;logs[name]=p.stdout.strip()
result={'passed':True,'candidateSHA256':sha(out/'after.c'),'baseSHA256':sha(out/'before.c'),
 'helperSHA256':hashlib.sha256(helper.encode()).hexdigest(),'nativeASanUBSan':True,'actualArmABI':True,
 'oldLoopMissingAndDuplicateTargetDemonstrated':True,'guardBeforePreparationAndDSALookup':True,
 'logs':logs,'hardwareOffloadAccepted':False,'historicalRootCauseProven':False,'kernelAPIBoundariesMocked':True}
(out/'qa.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
