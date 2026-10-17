"""Extend qualified bridge writer fence to packet-key preparation ordering."""
from pathlib import Path
import difflib, hashlib, json, shutil
w = Path('/mnt/d/ChatGPT/XR1710G')
parent = w / 'development/ap32/bridge-transaction'
out = w / 'development/ap32/packet-fence'
out.mkdir()
prep = json.loads((parent / 'prepared.json').read_text())
assert json.loads((parent / 'qa.json').read_text())['passed']
assert json.loads((parent / 'vm-result.json').read_text())['passed']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for path, hashes in prep['sources'].items():
    name = Path(path).name
    assert sha(parent / name) == hashes['after']
    shutil.copy2(parent / name, out / name)
    shutil.copy2(parent / ('before-' + name), out / ('before-' + name))
s = (out / 'airoha_ppe.c').read_text()
def replace(a, b):
    global s
    assert s.count(a) == 1, (a[:80], s.count(a))
    s = s.replace(a,b,1)
a = s.index('/* Capture before reading context; commit verifies under the same cache')
b = s.index('\nstatic int airoha_ppe_flow_offload_replace(', a)
snapshot = s[a:b]
s = s[:a] + s[b:]
ready = '''/* Must also validate packet-key preparation: a packet may have read the
 * old bridge/PVID before a writer and arrive at ppe_lock after a new template
 * was published. A current writer count of zero alone misses that race.
 */
static bool airoha_ppe_l2_ready_locked(struct airoha_ppe *ppe, u64 generation)
{
	lockdep_assert_held(&ppe_lock);
	return !ppe->l2_policy_latched && !ppe->l2_bridge_writers &&
	       generation == ppe->l2_generation;
}

'''
replace('static void airoha_ppe_foe_insert_entry(', snapshot + '\n' + ready + 'static void airoha_ppe_foe_insert_entry(')
replace('''	bool bridge_eligible = airoha_ppe_skb_l2_key(skb, &key);''', '''	u64 bridge_generation;
	bool bridge_eligible = airoha_ppe_l2_snapshot(ppe, &bridge_generation) &&
		airoha_ppe_skb_l2_key(skb, &key);''')
replace('if (ppe->l2_policy_latched || ppe->l2_bridge_writers || !bridge_eligible)',
        'if (!bridge_eligible ||\n\t    !airoha_ppe_l2_ready_locked(ppe, bridge_generation))')
replace('if (ppe->l2_policy_latched || ppe->l2_bridge_writers ||\n\t    e->l2_generation != ppe->l2_generation)',
        'if (!airoha_ppe_l2_ready_locked(ppe, e->l2_generation))')
(out / 'airoha_ppe.c').write_text(s)
patch = 'Subject: [PATCH] XR: fence PPE templates and packet keys across bridge mutations\n\n'
for path, hashes in prep['sources'].items():
    n = Path(path).name
    before = (out / ('before-' + n)).read_text()
    after = (out / n).read_text()
    hashes['after'] = sha(out / n)
    patch += ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                         fromfile='a/' + path if before else '/dev/null', tofile='b/' + path))
(out / '99999h-XR-PPE-bridge-mutation-fence.patch').write_text(patch)
prep['parent'] = str(parent.relative_to(w))
prep['scope'] += '; packet-key generation must still match at subflow bind'
(out / 'prepared.json').write_text(json.dumps(prep, indent=2) + '\n')
print(json.dumps({'prepared':True,'candidateSHA256':sha(out/'airoha_ppe.c'),'productionOrDeviceChanged':False}))
