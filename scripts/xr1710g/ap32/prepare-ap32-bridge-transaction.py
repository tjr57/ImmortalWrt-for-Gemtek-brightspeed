"""Prepare private AP32 bridge mutation fence; do not edit production/any AP."""
from pathlib import Path
import difflib, hashlib, json

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
k = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out = w / 'development/ap32/bridge-transaction'
out.mkdir(parents=True, exist_ok=True)
assert not (out / 'prepared.json').exists(), 'candidate already prepared'
paths = ['drivers/net/ethernet/airoha/airoha_ppe.c',
         'drivers/net/ethernet/airoha/airoha_eth.h', 'include/linux/if_bridge.h',
         'net/bridge/br_fdb.c', 'net/bridge/br_stp.c', 'net/bridge/br_private.h',
         'net/bridge/Makefile']
before = {p: (k / p).read_text() for p in paths}
files = dict(before)
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()
expected = {'airoha_ppe.c': '7188f4e44e313ee4be7d6b3fbf148b2b966c8210538d4456080a918c200ce57e',
            'airoha_eth.h': 'fb5e961a1380cd7bf05272a5e0e5f12ec97b75e17ada389be6f1de7d613b615c',
            'br_fdb.c': 'fc2346556bbc822641bd4ca461cdd49fd3057bb00bf0263c821fd7c1a53aee30',
            'if_bridge.h': '2612218bec087334417016472ee8cce769d7ee56aaa36fc5f885d7b34d1e26d9'}
for p, s in before.items():
    if Path(p).name in expected:
        assert sha(s) == expected[Path(p).name], p

def replace(path, a, b):
    s = files[path]
    assert s.count(a) == 1, (path, a[:90], s.count(a))
    files[path] = s.replace(a, b, 1)

public = '''/* Synchronous bridge forwarding mutation fence. Callbacks are atomic and
 * must not acquire RTNL, bridge locks, sleep, or stop notification propagation.
 * BEGIN has drained dependent caches before the writer may mutate; END makes
 * the completed change visible. Nested/concurrent writers remain fenced.
 * INIT is delivered while registration is serialized with BEGIN/END, including
 * writers already in progress. Receivers must mirror the absolute count.
 */
enum br_fwd_policy_event {
	BR_FWD_POLICY_INIT,
	BR_FWD_POLICY_BEGIN,
	BR_FWD_POLICY_END,
};

struct br_fwd_policy_state {
	u32 writers;
};

struct notifier_block;
'''
decl = '''int br_fwd_policy_register(struct notifier_block *nb);
void br_fwd_policy_unregister(struct notifier_block *nb);
'''
replace('include/linux/if_bridge.h', '#if IS_ENABLED(CONFIG_BRIDGE)\n', public + '\n#if IS_ENABLED(CONFIG_BRIDGE)\n' + decl)
stub = '''static inline int br_fwd_policy_register(struct notifier_block *nb)
{
	return -EOPNOTSUPP;
}

static inline void br_fwd_policy_unregister(struct notifier_block *nb)
{
}

'''
replace('include/linux/if_bridge.h', '#else\nstatic inline bool br_fdb_forward_to_rcu', '#else\n' + stub + 'static inline bool br_fdb_forward_to_rcu')
replace('net/bridge/br_private.h', '#include <linux/refcount.h>\n', '''#include <linux/refcount.h>
#include <linux/cleanup.h>

void br_fwd_policy_begin(void);
void br_fwd_policy_end(void);
/* A real bridge device makes the guard non-NULL. Its lifetime is protected by
 * the existing caller's RTNL/RCU/bridge lock, not by this scope guard.
 */
DEFINE_GUARD(br_fwd_change, struct net_device *,
	     br_fwd_policy_begin(), br_fwd_policy_end());
''')
files['net/bridge/br_fwd_policy.c'] = '''// SPDX-License-Identifier: GPL-2.0-or-later
/* Serialize dependent offload caches with bridge forwarding mutations.
 * The lock is never held across the mutation. Callbacks only revoke/mirror
 * state under their own cache lock; publishers never acquire this lock.
 */
#include <linux/export.h>
#include <linux/if_bridge.h>
#include <linux/notifier.h>
#include <linux/spinlock.h>
#include "br_private.h"

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
'''
replace('net/bridge/Makefile', 'br_ioctl.o br_stp.o br_stp_bpdu.o', 'br_ioctl.o br_stp.o br_stp_bpdu.o br_fwd_policy.o')
replace('net/bridge/br_stp.c', '\tp->state = state;\n', '\tguard(br_fwd_change)(p->br->dev);\n\tp->state = state;\n')
replace('net/bridge/br_fdb.c', '\ttrace_fdb_delete(br, f);\n', '\tguard(br_fwd_change)(br->dev);\n\ttrace_fdb_delete(br, f);\n')
replace('net/bridge/br_fdb.c', '\t/* Maybe another port has same hw addr? */', '\tguard(br_fwd_change)(br->dev);\n\n\t/* Maybe another port has same hw addr? */')
replace('net/bridge/br_fdb.c', '\terr = rhashtable_lookup_insert_fast(&br->fdb_hash_tbl, &fdb->rhnode,', '\tguard(br_fwd_change)(br->dev);\n\terr = rhashtable_lookup_insert_fast(&br->fdb_hash_tbl, &fdb->rhnode,')
replace('net/bridge/br_fdb.c', '\t\t\t\tbr_switchdev_fdb_notify(br, fdb, RTM_DELNEIGH);', '\t\t\t\tguard(br_fwd_change)(br->dev);\n\t\t\t\tbr_switchdev_fdb_notify(br, fdb, RTM_DELNEIGH);')
replace('net/bridge/br_fdb.c', '\tfdb = br_fdb_find(br, addr, vid);\n\tif (fdb == NULL) {', '\tguard(br_fwd_change)(br->dev);\n\tfdb = br_fdb_find(br, addr, vid);\n\tif (fdb == NULL) {')
replace('net/bridge/br_fdb.c', '\tif (locked && (!p || !(p->flags & BR_PORT_MAB)))\n\t\treturn -EINVAL;\n', '\tif (locked && (!p || !(p->flags & BR_PORT_MAB)))\n\t\treturn -EINVAL;\n\n\tguard(br_fwd_change)(br->dev);\n')

ppe = 'drivers/net/ethernet/airoha/airoha_ppe.c'
replace(ppe, 'static void airoha_ppe_l2_revoke(struct airoha_ppe *ppe)\n', 'static void airoha_ppe_l2_revoke_locked(struct airoha_ppe *ppe)\n')
replace(ppe, '''	spin_lock_bh(&ppe_lock);
	ppe->l2_generation++;''', '''	lockdep_assert_held(&ppe_lock);
	ppe->l2_generation++;''')
replace(ppe, '''	spin_unlock_bh(&ppe_lock);
}

/* Any bridge filtering policy''', '''}

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

/* Any bridge filtering policy''')
replace(ppe, 'if (ppe->l2_policy_latched || !bridge_eligible)', 'if (ppe->l2_policy_latched || ppe->l2_bridge_writers || !bridge_eligible)')
replace(ppe, 'if (ppe->l2_policy_latched || e->l2_generation != ppe->l2_generation)', 'if (ppe->l2_policy_latched || ppe->l2_bridge_writers ||\n\t    e->l2_generation != ppe->l2_generation)')
replace(ppe, ' allowed = !ppe->l2_policy_latched;', ' allowed = !ppe->l2_policy_latched && !ppe->l2_bridge_writers;')
replace(ppe, '\t/* Register first, then scan. A racing callback may only latch true. */', '''	ppe->l2_bridge_nb.notifier_call = airoha_ppe_l2_bridge_event;
	err = br_fwd_policy_register(&ppe->l2_bridge_nb);
	if (err) {
		nf_bridge_policy_notifier_unregister(&ppe->l2_policy_nb);
		unregister_switchdev_notifier(&ppe->l2_switchdev_atomic_nb);
		unregister_switchdev_blocking_notifier(&ppe->l2_switchdev_nb);
		unregister_netdevice_notifier(&ppe->l2_netdev_nb);
		debugfs_remove(ppe->debugfs_dir);
		goto error_l2_flow_table_destroy;
	}
	/* Register first, then scan. A racing callback may only latch true. */''')
replace(ppe, '\tdebugfs_create_u64("xr_l2_generation",', '\tdebugfs_create_u32("xr_l2_bridge_writers", 0400, ppe->debugfs_dir,\n\t\t\t   &ppe->l2_bridge_writers);\n\tdebugfs_create_u64("xr_l2_generation",')
replace(ppe, '\tnf_bridge_policy_notifier_unregister(&eth->ppe->l2_policy_nb);', '\tbr_fwd_policy_unregister(&eth->ppe->l2_bridge_nb);\n\tnf_bridge_policy_notifier_unregister(&eth->ppe->l2_policy_nb);')
replace('drivers/net/ethernet/airoha/airoha_eth.h', '\tstruct notifier_block l2_policy_nb;\n', '\tstruct notifier_block l2_policy_nb;\n\tstruct notifier_block l2_bridge_nb;\n\tu32 l2_bridge_writers;\n')

patch = 'Subject: [PATCH] XR: fence PPE publication across FDB and STP mutations\n\n'
for path, s in files.items():
    (out / Path(path).name).write_text(s)
    (out / ('before-' + Path(path).name)).write_text(before.get(path, ''))
    patch += ''.join(difflib.unified_diff(before.get(path, '').splitlines(True), s.splitlines(True),
                                         fromfile='a/' + path if path in before else '/dev/null', tofile='b/' + path))
(out / '99999h-XR-PPE-bridge-mutation-fence.patch').write_text(patch)
report = {'prepared': True, 'baseline': '20261011-ap31-d331711d',
          'sources': {p: {'before': sha(before.get(p, '')), 'after': sha(s)} for p, s in files.items()},
          'productionSourceOrDeviceChanged': False,
          'scope': 'FDB create/delete/move/admin flags and STP state mutations; not all bridge/TC policies',
          'fullPolicyHandoffOrHardwareQualified': False}
(out / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
