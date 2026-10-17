"""Prepare exact egress validation for owned AP PPE development; no device I/O."""
from pathlib import Path
import hashlib,json,difflib
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
out=w/'development/ap31/ppe-target';out.mkdir(parents=True,exist_ok=False)
name='drivers/net/ethernet/airoha/airoha_ppe.c';before=(k/name).read_text()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
helper='''/* A hardware entry has exactly one egress. An absent redirect must not
 * reach DSA lookup with a NULL netdev, and multiple redirects cannot be
 * represented by retaining only the last action's target.
 */
static bool airoha_ppe_rule_has_single_redirect(const struct flow_rule *rule)
{
 const struct flow_action_entry *act;
 bool found = false;
 int i;

 flow_action_for_each(i, act, &rule->action) {
  if (act->id != FLOW_ACTION_REDIRECT)
   continue;
  if (found || !act->dev)
   return false;
  found = true;
 }
 return found;
}

'''
anchor='static int airoha_ppe_flow_offload_replace('
assert before.count(anchor)==1
after=before.replace(anchor,helper+anchor)
anchor='\tif (rhashtable_lookup(&eth->flow_table, &f->cookie,'
assert after.count(anchor)==1
guard='''\tif (!airoha_ppe_rule_has_single_redirect(rule)) {
\t\tNL_SET_ERR_MSG_MOD(f->common.extack,
\t\t\t\t   "PPE requires exactly one valid redirect target");
\t\treturn -EOPNOTSUPP;
\t}

'''
after=after.replace(anchor,guard+anchor)
# Reject absent targets before the initializer performs any DSA lookup.
anchor='\tint wlan_etype = -EINVAL, dsa_port = airoha_get_dsa_port(&netdev);'
assert after.count(anchor)==1
after=after.replace(anchor,'\tint wlan_etype = -EINVAL, dsa_port;')
anchor='\tu8 smac_id = 0xf;\n\n\tmemset(hwe, 0, sizeof(*hwe));\n\t*egress_dev = NULL;'
assert after.count(anchor)==1
after=after.replace(anchor,'''\tu8 smac_id = 0xf;

\t*egress_dev = NULL;
\tif (!netdev)
\t\treturn -EOPNOTSUPP;
\tdsa_port = airoha_get_dsa_port(&netdev);
\tmemset(hwe, 0, sizeof(*hwe));''')
(out/'before.c').write_text(before);(out/'after.c').write_text(after)
patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(out/'99999g-PPE-require-one-valid-egress.patch').write_text(patch)
report={'prepared':True,'baseSHA256':sha(k/name),'candidateSHA256':sha(out/'after.c'),
 'scope':'Validate exactly one non-null redirect before hardware flow preparation; keep all existing match/context/policy gates.',
 'observedInSource':['The action loop overwrites odev on each redirect.','L2 odev validation occurs after airoha_ppe_foe_entry_prepare.','Entry preparation calls DSA lookup before its later optional netdev branch.'],
 'historicalCrashRootCauseProven':False,'liveMalformedRulesSubmitted':False,'productionSourceChanged':False,
 'otherGaps':['VLAN action equivalence and exact template publication still require review.','Inactive bridge-policy hooks and Mesh hardware header capability remain unresolved.']}
(out/'prepared.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
