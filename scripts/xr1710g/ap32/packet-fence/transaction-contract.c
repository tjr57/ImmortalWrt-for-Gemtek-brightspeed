
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#include <assert.h>
#include <pthread.h>
typedef uint64_t u64;
struct notifier_block {int (*notifier_call)(struct notifier_block*,unsigned long,void*);};
struct airoha_flow_table_entry;
struct list_head {struct airoha_flow_table_entry*entry;};
struct airoha_flow_table_entry {int type;struct list_head l2_gc_node;int l2_node;bool l2_cached;u64 l2_generation;};
struct airoha_ppe {struct notifier_block l2_bridge_nb;uint32_t l2_bridge_writers;bool l2_policy_latched;u64 l2_generation,l2_invalidations;struct list_head l2_templates;int l2_flows;};
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
static DEFINE_SPINLOCK(br_fwd_policy_lock);
static ATOMIC_NOTIFIER_HEAD(br_fwd_policy_chain);
static struct br_fwd_policy_state br_fwd_policy_state;

int br_fwd_policy_register(struct notifier_block *nb)
{
	int err;

	spin_lock_bh(&br_fwd_policy_lock);
	err = atomic_notifier_chain_register(&br_fwd_policy_chain, nb);
	if (!err)
		nb->notifier_call(nb, BR_FWD_POLICY_INIT, &br_fwd_policy_state);
	spin_unlock_bh(&br_fwd_policy_lock);
	return err;
}
EXPORT_SYMBOL_GPL(br_fwd_policy_register);

void br_fwd_policy_unregister(struct notifier_block *nb)
{
	/* This waits for RCU readers and must run without our spinlock held. */
	atomic_notifier_chain_unregister(&br_fwd_policy_chain, nb);
}
EXPORT_SYMBOL_GPL(br_fwd_policy_unregister);

void br_fwd_policy_begin(void)
{
	spin_lock_bh(&br_fwd_policy_lock);
	br_fwd_policy_state.writers++;
	atomic_notifier_call_chain(&br_fwd_policy_chain, BR_FWD_POLICY_BEGIN,
				  &br_fwd_policy_state);
	spin_unlock_bh(&br_fwd_policy_lock);
}

void br_fwd_policy_end(void)
{
	spin_lock_bh(&br_fwd_policy_lock);
	br_fwd_policy_state.writers--;
	atomic_notifier_call_chain(&br_fwd_policy_chain, BR_FWD_POLICY_END,
				  &br_fwd_policy_state);
	spin_unlock_bh(&br_fwd_policy_lock);
}
static void airoha_ppe_l2_revoke_locked(struct airoha_ppe *ppe)
{
	struct airoha_flow_table_entry *e, *tmp;
	/* Conservative global revocation is intentional: do not keep a hardware
	 * subflow alive after bridge membership, ifindex lifetime or bearer change.
	 * No flow_offload_mutex acquisition under RTNL; the cache has one spinlock.
	 */
	lockdep_assert_held(&ppe_lock);
	ppe->l2_generation++;
	list_for_each_entry_safe(e, tmp, &ppe->l2_templates, l2_gc_node) {
		airoha_ppe_foe_remove_l2_flow(ppe, e);
		ppe->l2_invalidations++;
	}
}

static void airoha_ppe_l2_revoke(struct airoha_ppe *ppe)
{
	spin_lock_bh(&ppe_lock);
	airoha_ppe_l2_revoke_locked(ppe);
	spin_unlock_bh(&ppe_lock);
}

static int airoha_ppe_l2_bridge_event(struct notifier_block *nb,
				      unsigned long event, void *ptr)
{
	struct airoha_ppe *ppe = container_of(nb, struct airoha_ppe, l2_bridge_nb);
	const struct br_fwd_policy_state *state = ptr;

	spin_lock_bh(&ppe_lock);
	ppe->l2_bridge_writers = state->writers;
	/* INIT also invalidates any pre-registration snapshot. END advances the
	 * generation so a snapshot from inside the mutation cannot be reused.
	 */
	airoha_ppe_l2_revoke_locked(ppe);
	spin_unlock_bh(&ppe_lock);
	return NOTIFY_OK;
}

static bool airoha_ppe_l2_snapshot(struct airoha_ppe *ppe, u64 *generation)
{
 bool allowed;
 spin_lock_bh(&ppe_lock);
 allowed = !ppe->l2_policy_latched && !ppe->l2_bridge_writers;
 *generation = ppe->l2_generation;
 spin_unlock_bh(&ppe_lock);
 return allowed;
}

static bool airoha_ppe_l2_ready_locked(struct airoha_ppe *ppe, u64 generation)
{
	lockdep_assert_held(&ppe_lock);
	return !ppe->l2_policy_latched && !ppe->l2_bridge_writers &&
	       generation == ppe->l2_generation;
}

static int
airoha_ppe_foe_l2_flow_commit_entry(struct airoha_ppe *ppe,
                                 struct airoha_flow_table_entry *e)
{
	struct airoha_flow_table_entry *prev;
	int err = 0;

	e->type = FLOW_TYPE_L2;
	INIT_LIST_HEAD(&e->l2_gc_node);
	spin_lock_bh(&ppe_lock);
	if (!airoha_ppe_l2_ready_locked(ppe, e->l2_generation)) {
		spin_unlock_bh(&ppe_lock);
		return -EOPNOTSUPP;
	}
	prev = rhashtable_lookup_get_insert_fast(&ppe->l2_flows, &e->l2_node,
					 airoha_l2_flow_table_params);
	if (prev) {
		err = IS_ERR(prev) ? PTR_ERR(prev) : -EEXIST;
	} else {
		e->l2_cached = true;
		list_add_tail(&e->l2_gc_node, &ppe->l2_templates);
	}
	spin_unlock_bh(&ppe_lock);
	return err;
}

static bool old_snapshot(struct airoha_ppe *ppe, u64 *generation)
{
 bool allowed;
 spin_lock_bh(&ppe_lock);
 allowed = !ppe->l2_policy_latched;
 *generation = ppe->l2_generation;
 spin_unlock_bh(&ppe_lock);
 return allowed;
}

static int
old_commit(struct airoha_ppe *ppe,
                                 struct airoha_flow_table_entry *e)
{
	struct airoha_flow_table_entry *prev;
	int err = 0;

	e->type = FLOW_TYPE_L2;
	INIT_LIST_HEAD(&e->l2_gc_node);
	spin_lock_bh(&ppe_lock);
	if (ppe->l2_policy_latched || e->l2_generation != ppe->l2_generation) {
		spin_unlock_bh(&ppe_lock);
		return -EOPNOTSUPP;
	}
	prev = rhashtable_lookup_get_insert_fast(&ppe->l2_flows, &e->l2_node,
					 airoha_l2_flow_table_params);
	if (prev) {
		err = IS_ERR(prev) ? PTR_ERR(prev) : -EEXIST;
	} else {
		e->l2_cached = true;
		list_add_tail(&e->l2_gc_node, &ppe->l2_templates);
	}
	spin_unlock_bh(&ppe_lock);
	return err;
}

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
