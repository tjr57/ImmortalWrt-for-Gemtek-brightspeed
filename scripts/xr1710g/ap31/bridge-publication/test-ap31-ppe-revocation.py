"""Validate actual publication/revocation functions with controlled interleavings."""
from pathlib import Path
import subprocess,json,hashlib,os,fcntl
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap31/ppe-revocation';parent=w/'development/ap31/ppe-vlan'
r=Path('/home/xrdev/projects/xr1710g/openwrt');tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
old=(out/'before-airoha_ppe.c').read_text();new=(out/'airoha_ppe.c').read_text()
def fn(s,marker):
 a=s.index(marker);return s[a:s.index('\n}\n',a)+3]
revoke=fn(new,'static void airoha_ppe_l2_revoke(')
snap=fn(new,'static bool airoha_ppe_l2_snapshot(')
commit=fn(new,'static int\nairoha_ppe_foe_l2_flow_commit_entry(')
oldcommit=fn(old,'static int\nairoha_ppe_foe_l2_flow_commit_entry(').replace('airoha_ppe_foe_l2_flow_commit_entry','old_commit')
mock=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#include <assert.h>
#include <pthread.h>
typedef uint64_t u64;
struct airoha_flow_table_entry;
struct list_head {struct airoha_flow_table_entry*entry;};
struct airoha_flow_table_entry {int type;struct list_head l2_gc_node;int l2_node;bool l2_cached;u64 l2_generation;};
struct airoha_ppe {bool l2_policy_latched;u64 l2_generation,l2_invalidations;struct list_head l2_templates;int l2_flows;};
static pthread_mutex_t ppe_lock=PTHREAD_MUTEX_INITIALIZER;
static struct airoha_ppe ppe;
#define spin_lock_bh(m) assert(pthread_mutex_lock(m)==0)
#define spin_unlock_bh(m) assert(pthread_mutex_unlock(m)==0)
#define FLOW_TYPE_L2 1
#define INIT_LIST_HEAD(p) ((p)->entry=NULL)
#define list_for_each_entry_safe(e,t,h,m) for((e)=(h)->entry,(t)=NULL;(e);(e)=(t))
#define IS_ERR(p) false
#define PTR_ERR(p) (-EINVAL)
static int airoha_l2_flow_table_params;
static void* rhashtable_lookup_get_insert_fast(int*a,int*b,int c){(void)a;(void)b;(void)c;return ppe.l2_templates.entry;}
static void list_add_tail(struct list_head*node,struct list_head*head){
 (void)node;extern struct airoha_flow_table_entry entry;head->entry=&entry;
}
static void airoha_ppe_foe_remove_l2_flow(struct airoha_ppe*p,struct airoha_flow_table_entry*e){p->l2_templates.entry=NULL;e->l2_cached=false;}
struct airoha_flow_table_entry entry;
'''
tests=r'''
static int checks,commit_result;
#define CHECK(x) do{assert(x);checks++;}while(0)
static pthread_barrier_t prepared,revoked;
static bool use_old;
static void reset(void){ppe=(struct airoha_ppe){0};entry=(struct airoha_flow_table_entry){0};}
static void*publisher(void*unused){
 (void)unused;
 assert(airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation));
 pthread_barrier_wait(&prepared);pthread_barrier_wait(&revoked);
 commit_result=use_old?old_commit(&ppe,&entry):airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry);
 return NULL;
}
static void*invalidator(void*unused){
 (void)unused;pthread_barrier_wait(&prepared);airoha_ppe_l2_revoke(&ppe);pthread_barrier_wait(&revoked);return NULL;
}
int main(void){
 u64 epoch;
 reset();CHECK(airoha_ppe_l2_snapshot(&ppe,&epoch));CHECK(epoch==0);
 entry.l2_generation=epoch;CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==0);CHECK(entry.l2_cached);
 airoha_ppe_l2_revoke(&ppe);CHECK(!entry.l2_cached&&!ppe.l2_templates.entry);CHECK(ppe.l2_generation==1);
 reset();ppe.l2_policy_latched=true;CHECK(!airoha_ppe_l2_snapshot(&ppe,&epoch));CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==-EOPNOTSUPP);
 reset();airoha_ppe_l2_revoke(&ppe);CHECK(airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation));CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==0);
 /* Both loops use the same exact snapshot/revoke sequence. Old code inserts
  * a stale template after the notification; new code refuses publication. */
 for(int old=0;old<2;old++)for(int round=0;round<10;round++){
  pthread_t a,b;reset();use_old=old;
  CHECK(pthread_barrier_init(&prepared,NULL,2)==0);CHECK(pthread_barrier_init(&revoked,NULL,2)==0);
  CHECK(pthread_create(&a,NULL,publisher,NULL)==0);CHECK(pthread_create(&b,NULL,invalidator,NULL)==0);
  CHECK(pthread_join(a,NULL)==0);CHECK(pthread_join(b,NULL)==0);
  CHECK(commit_result==(old?0:-EOPNOTSUPP));CHECK(entry.l2_cached==!!old);
  CHECK(pthread_barrier_destroy(&prepared)==0);CHECK(pthread_barrier_destroy(&revoked)==0);
 }
 printf("%d checks; old stale publication reproduced; new candidate rejects in-flight revoked generations\n",checks);return 0;
}
'''
(out/'publication-contract.c').write_text(mock+revoke+snap+oldcommit+commit+tests)
cc=tc/'bin/aarch64-openwrt-linux-musl-gcc'
commands=[['gcc','-Wall','-Wextra','-Werror','-g','-pthread','-fsanitize=address,undefined',str(out/'publication-contract.c'),'-o',str(out/'publication-native')],
 [str(cc),'-Wall','-Wextra','-Werror','-pthread','-Os',str(out/'publication-contract.c'),'-o',str(out/'publication-arm')]]
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for cmd in commands:
  p=subprocess.run(cmd,env=dict(os.environ,STAGING_DIR=str(tc)),capture_output=True,text=True);assert p.returncode==0,p.stderr
logs={}
for name,cmd in [('native',[str(out/'publication-native')]),('ARM',['qemu-aarch64-static','-L',str(r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'),str(out/'publication-arm')])]:
 p=subprocess.run(cmd,capture_output=True,text=True);(out/(name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(name,p.stderr);logs[name]=p.stdout.strip()
# The prior action/context/packet-key checks apply only if exact tested
# functions, and the packet key layout, are byte-identical in this candidate.
equivalent={}
def key_struct(path):
 s=path.read_text();a=s.index('struct airoha_l2_flow_key {');return s[a:s.index('\n};',a)+3]
assert key_struct(parent/'airoha_eth.h')==key_struct(out/'airoha_eth.h')
for name in ['airoha_ppe_l2_actions','airoha_ppe_l2_context','airoha_ppe_skb_l2_key','airoha_ppe_l2_rule_exact','airoha_ppe_rule_has_single_redirect']:
 a=fn((parent/'airoha_ppe.c').read_text(),'static bool '+name+'(');b=fn(new,'static bool '+name+'(')
 assert a==b;equivalent[name]=hashlib.sha256(a.encode()).hexdigest()
section=new[new.index('static int airoha_ppe_flow_offload_replace('):]
assert section.index('!airoha_ppe_l2_snapshot(')<section.index('!airoha_ppe_l2_context(')<section.index('airoha_ppe_foe_entry_prepare(')<section.index('e->l2_generation = l2_generation;')<section.index('airoha_ppe_foe_flow_commit_entry(')
report={'passed':True,'sourceSHA256':hashlib.sha256(new.encode()).hexdigest(),'oldStalePublicationReproduced':True,'nativeASanUBSan':True,'actualArmABI':True,'pthreadOrderedInterleavings':True,'kernelCacheAndNotificationAPIsModeled':True,'inheritedFunctionsIdentical':equivalent,'inheritedEvidence':['development/ap31/ppe-vlan/qa.json','development/ap31/ppe-vlan/packet-qa.json'],'logs':logs,'fullPolicyAndHardwareQualification':False}
(out/'qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='inheritedFunctionsIdentical'}))
