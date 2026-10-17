// SPDX-License-Identifier: GPL-2.0-or-later
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
