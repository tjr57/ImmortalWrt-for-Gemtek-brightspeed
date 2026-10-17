"""Exact candidate broker/PPE functions with deterministic concurrent schedules."""
from pathlib import Path
import argparse, fcntl, hashlib, json, os, subprocess
w = Path('/mnt/d/ChatGPT/XR1710G')
parser = argparse.ArgumentParser()
parser.add_argument('--candidate', choices=['bridge-transaction', 'packet-fence'], default='bridge-transaction')
args = parser.parse_args()
out = w / 'development/ap32' / args.candidate
r = Path('/home/xrdev/projects/xr1710g/openwrt')
tc = r / 'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
new = (out / 'airoha_ppe.c').read_text()
old = (out / 'before-airoha_ppe.c').read_text()
def fn(s, marker):
    a = s.index(marker)
    return s[a:s.index('\n}\n', a) + 3]
mock = (w / 'development/ap31/ppe-revocation/publication-contract.c').read_text().split('static void airoha_ppe_l2_revoke(')[0]
mock = mock.replace('struct airoha_ppe {bool', 'struct airoha_ppe {struct notifier_block l2_bridge_nb;uint32_t l2_bridge_writers;bool')
mock = mock.replace('struct airoha_flow_table_entry;', '''struct notifier_block {int (*notifier_call)(struct notifier_block*,unsigned long,void*);};
struct airoha_flow_table_entry;''')
mock += r'''
#include <stddef.h>
typedef uint32_t u32;
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define lockdep_assert_held(x) ((void)(x))
#define EXPORT_SYMBOL_GPL(x)
#define NOTIFY_OK 1
#define DEFINE_SPINLOCK(x) pthread_mutex_t x=PTHREAD_MUTEX_INITIALIZER
#define ATOMIC_NOTIFIER_HEAD(x) struct notifier_block*x
enum br_fwd_policy_event {BR_FWD_POLICY_INIT,BR_FWD_POLICY_BEGIN,BR_FWD_POLICY_END};
struct br_fwd_policy_state {u32 writers;};
static bool registration_error;
static int atomic_notifier_chain_register(struct notifier_block**c,struct notifier_block*n){
 if(registration_error)return -ENOMEM;assert(!*c);*c=n;return 0;
}
static void atomic_notifier_chain_unregister(struct notifier_block**c,struct notifier_block*n){assert(*c==n);*c=NULL;}
static int atomic_notifier_call_chain(struct notifier_block**c,unsigned long e,void*p){return *c?(*c)->notifier_call(*c,e,p):0;}
'''
broker = (out / 'br_fwd_policy.c').read_text()
broker = broker[broker.index('static DEFINE_SPINLOCK'):]
functions = [fn(new, marker) for marker in ['static void airoha_ppe_l2_revoke_locked(',
             'static void airoha_ppe_l2_revoke(', 'static int airoha_ppe_l2_bridge_event(',
             'static bool airoha_ppe_l2_snapshot(', 'static int\nairoha_ppe_foe_l2_flow_commit_entry(']]
if args.candidate == 'packet-fence':
    functions.insert(-1, fn(new, 'static bool airoha_ppe_l2_ready_locked('))
functions += [fn(old, 'static bool airoha_ppe_l2_snapshot(').replace('airoha_ppe_l2_snapshot','old_snapshot'),
              fn(old, 'static int\nairoha_ppe_foe_l2_flow_commit_entry(').replace('airoha_ppe_foe_l2_flow_commit_entry','old_commit')]
tests = r'''
static int checks;
#define CHECK(x) do {assert(x);checks++;} while(0)
static void reset(void){
 assert(!br_fwd_policy_chain && !br_fwd_policy_state.writers);
 ppe=(struct airoha_ppe){.l2_bridge_nb={.notifier_call=airoha_ppe_l2_bridge_event}};
 entry=(struct airoha_flow_table_entry){0};
}
static pthread_barrier_t started,observed,finished;
static bool old_mode, snapshot_ok;
static int result;
static void*writer(void*u){
 (void)u;br_fwd_policy_begin();pthread_barrier_wait(&started);
 pthread_barrier_wait(&observed);br_fwd_policy_end();pthread_barrier_wait(&finished);return NULL;
}
static void*reader(void*u){
 (void)u;pthread_barrier_wait(&started);
 snapshot_ok=old_mode?old_snapshot(&ppe,&entry.l2_generation):airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation);
 result=old_mode?old_commit(&ppe,&entry):airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry);
 pthread_barrier_wait(&observed);pthread_barrier_wait(&finished);return NULL;
}
int main(void){
 u64 epoch;
 reset();registration_error=true;CHECK(br_fwd_policy_register(&ppe.l2_bridge_nb)==-ENOMEM);
 CHECK(!ppe.l2_generation&&!br_fwd_policy_chain);registration_error=false;
 /* Registration while a writer is already active must observe the count. */
 br_fwd_policy_begin();CHECK(br_fwd_policy_state.writers==1);
 CHECK(br_fwd_policy_register(&ppe.l2_bridge_nb)==0);CHECK(ppe.l2_bridge_writers==1);
 CHECK(!airoha_ppe_l2_snapshot(&ppe,&epoch));br_fwd_policy_end();CHECK(!ppe.l2_bridge_writers);
 CHECK(airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation));
 CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==0);CHECK(entry.l2_cached);
 br_fwd_policy_begin();CHECK(!entry.l2_cached);CHECK(ppe.l2_bridge_writers==1);
 br_fwd_policy_begin();CHECK(ppe.l2_bridge_writers==2);
 br_fwd_policy_end();CHECK(ppe.l2_bridge_writers==1);CHECK(!airoha_ppe_l2_snapshot(&ppe,&epoch));
 br_fwd_policy_end();CHECK(!ppe.l2_bridge_writers);
 CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==-EOPNOTSUPP);
 CHECK(airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation));
 CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==0);
 airoha_ppe_l2_revoke(&ppe);CHECK(!entry.l2_cached);
 ppe.l2_policy_latched=true;br_fwd_policy_begin();br_fwd_policy_end();
 CHECK(!airoha_ppe_l2_snapshot(&ppe,&epoch));CHECK(ppe.l2_policy_latched);
 br_fwd_policy_unregister(&ppe.l2_bridge_nb);CHECK(!br_fwd_policy_chain);
 for(int mode=0;mode<2;mode++)for(int round=0;round<30;round++){
  pthread_t a,b;reset();old_mode=mode;
  CHECK(br_fwd_policy_register(&ppe.l2_bridge_nb)==0);
  CHECK(pthread_barrier_init(&started,NULL,2)==0);
  CHECK(pthread_barrier_init(&observed,NULL,2)==0);
  CHECK(pthread_barrier_init(&finished,NULL,2)==0);
  CHECK(pthread_create(&a,NULL,writer,NULL)==0);CHECK(pthread_create(&b,NULL,reader,NULL)==0);
  CHECK(pthread_join(a,NULL)==0);CHECK(pthread_join(b,NULL)==0);
  CHECK(snapshot_ok==!!mode);CHECK(result==(mode?0:-EOPNOTSUPP));
  CHECK(!ppe.l2_bridge_writers);CHECK(!entry.l2_cached);
  CHECK(airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation));
  CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==0);
  airoha_ppe_l2_revoke(&ppe);br_fwd_policy_unregister(&ppe.l2_bridge_nb);
  CHECK(pthread_barrier_destroy(&started)==0);CHECK(pthread_barrier_destroy(&observed)==0);
  CHECK(pthread_barrier_destroy(&finished)==0);
 }
 printf("%d checks; AP31 in-mutation publication reproduced; AP32 rejects busy/stale, joins active writers, balances nested writers\n",checks);
 return 0;
}
'''
if args.candidate == 'packet-fence':
    tests = tests.replace(' for(int mode=0;', r'''
 /* Same port/MAC/VID key may be reused after a mutation. The old RX path's
  * current !latched/!writers check accepts it; the new path rejects its epoch.
  */
 reset();CHECK(br_fwd_policy_register(&ppe.l2_bridge_nb)==0);
 CHECK(airoha_ppe_l2_snapshot(&ppe,&epoch));
 br_fwd_policy_begin();br_fwd_policy_end();
 CHECK(airoha_ppe_l2_snapshot(&ppe,&entry.l2_generation));
 CHECK(airoha_ppe_foe_l2_flow_commit_entry(&ppe,&entry)==0);
 CHECK(!ppe.l2_policy_latched&&!ppe.l2_bridge_writers); /* old negative control */
 CHECK(!airoha_ppe_l2_ready_locked(&ppe,epoch));
 CHECK(airoha_ppe_l2_ready_locked(&ppe,entry.l2_generation));
 airoha_ppe_l2_revoke(&ppe);br_fwd_policy_unregister(&ppe.l2_bridge_nb);
 for(int mode=0;''')
(out / 'transaction-contract.c').write_text(mock + broker + '\n'.join(functions) + tests)
flags = ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-misleading-indentation', '-pthread']
cmds = [['gcc', *flags, '-g', '-fsanitize=address,undefined', str(out / 'transaction-contract.c'), '-o', str(out / 'transaction-native')],
        [str(tc / 'bin/aarch64-openwrt-linux-musl-gcc'), *flags, '-Os', str(out / 'transaction-contract.c'), '-o', str(out / 'transaction-arm')]]
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for cmd in cmds:
        p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, STAGING_DIR=str(tc)))
        assert p.returncode == 0, p.stderr
logs = {}
for name, cmd in [('native', [str(out / 'transaction-native')]), ('ARM', ['qemu-aarch64-static', '-L',
                  str(r / 'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'), str(out / 'transaction-arm')])]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    (out / (name + '.log')).write_text(p.stdout + p.stderr)
    assert p.returncode == 0, (name, p.stdout, p.stderr)
    logs[name] = p.stdout.strip()
equivalent = {}
for name in ['airoha_ppe_l2_actions', 'airoha_ppe_l2_context', 'airoha_ppe_skb_l2_key',
             'airoha_ppe_l2_rule_exact', 'airoha_ppe_rule_has_single_redirect', 'airoha_ppe_l2_port_eligible']:
    value = fn(new, 'static bool ' + name + '(')
    assert value == fn(old, 'static bool ' + name + '(')
    equivalent[name] = hashlib.sha256(value.encode()).hexdigest()
report = {'passed': True, 'sourceSHA256': hashlib.sha256(new.encode()).hexdigest(),
          'brokerSHA256': hashlib.sha256((out / 'br_fwd_policy.c').read_bytes()).hexdigest(),
          'oldCodeNegativeControl': True, 'nativeASanUBSanAndARM': True,
          'kernelCacheAndNotifierAPIsModeled': True, 'logs': logs, 'inheritedFunctions': equivalent,
          'fullPolicyOrHardwareQualified': False}
if args.candidate == 'packet-fence':
    insert = fn(new, 'static void airoha_ppe_foe_insert_entry(')
    assert insert.index('airoha_ppe_l2_snapshot(') < insert.index('airoha_ppe_skb_l2_key(') < insert.index('spin_lock_bh(&ppe_lock)')
    assert insert.index('airoha_ppe_l2_ready_locked(') < insert.index('airoha_ppe_foe_commit_subflow_entry(')
    parent = w / 'development/ap32/bridge-transaction'
    for name in ['br_fdb.c', 'br_stp.c', 'br_private.h', 'br_fwd_policy.c', 'if_bridge.h', 'Makefile']:
        assert (parent / name).read_bytes() == (out / name).read_bytes()
    report['packetPreparedBeforeMutationRejected'] = True
    report['VMSourceByteIdenticalTo'] = 'development/ap32/bridge-transaction/vm-result.json'
(out / 'qa.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'inheritedFunctions'}))
