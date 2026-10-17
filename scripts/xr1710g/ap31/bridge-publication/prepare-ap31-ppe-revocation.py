"""Add generation validation to private AP31 publication candidate."""
from pathlib import Path
import difflib,json,hashlib
w=Path('/mnt/d/ChatGPT/XR1710G');parent=w/'development/ap31/ppe-vlan';out=w/'development/ap31/ppe-revocation';out.mkdir()
def rep(s,a,b):
 assert s.count(a)==1,(a[:90],s.count(a));return s.replace(a,b,1)
t=(parent/'airoha_ppe.c').read_text();h=(parent/'airoha_eth.h').read_text()
# Every context revocation invalidates in-flight preparation, including when
# no template has reached the cache yet.
a=t.index('static void airoha_ppe_l2_revoke(');b=t.index('static int airoha_ppe_l2_policy_event(',a)
s=t[a:b];s=rep(s,'\tspin_lock_bh(&ppe_lock);','\tspin_lock_bh(&ppe_lock);\n\tppe->l2_generation++;')
t=t[:a]+s+t[b:]
a=t.index('static int\nairoha_ppe_foe_l2_flow_commit_entry(')
b=t.index('static int airoha_ppe_foe_flow_commit_entry(',a)
s=t[a:b];s=rep(s,'if (ppe->l2_policy_latched) {','if (ppe->l2_policy_latched || e->l2_generation != ppe->l2_generation) {')
t=t[:a]+s+t[b:]
snapshot='''/* Capture before reading context; commit verifies under the same cache
 * lock. A VLAN/FDB/netdevice revoke must invalidate in-flight preparation,
 * even if the template list was empty when the notification arrived.
 */
static bool airoha_ppe_l2_snapshot(struct airoha_ppe *ppe, u64 *generation)
{
 bool allowed;
 spin_lock_bh(&ppe_lock);
 allowed = !ppe->l2_policy_latched;
 *generation = ppe->l2_generation;
 spin_unlock_bh(&ppe_lock);
 return allowed;
}

'''
t=rep(t,'static int airoha_ppe_flow_offload_replace(',snapshot+'static int airoha_ppe_flow_offload_replace(')
t=rep(t,'\tstruct airoha_l2_flow_key l2_key = {};','\tstruct airoha_l2_flow_key l2_key = {};\n\tu64 l2_generation = 0;')
t=rep(t,'if (offload_type == PPE_PKT_TYPE_BRIDGE &&\n\t    !airoha_ppe_l2_context(rule, odev, &data, &l2_key)) {',
'''if (offload_type == PPE_PKT_TYPE_BRIDGE &&
\t    (!airoha_ppe_l2_snapshot(eth->ppe, &l2_generation) ||
\t     !airoha_ppe_l2_context(rule, odev, &data, &l2_key))) {''')
t=rep(t,'\tif (offload_type == PPE_PKT_TYPE_BRIDGE)\n\t\te->l2_key = l2_key;',
'''\tif (offload_type == PPE_PKT_TYPE_BRIDGE) {
\t\te->l2_key = l2_key;
\t\te->l2_generation = l2_generation;
\t}''')
h=rep(h,'\tstruct airoha_l2_flow_key l2_key;','\tstruct airoha_l2_flow_key l2_key;\n\tu64 l2_generation;')
h=rep(h,'\tu64 l2_invalidations;','\tu64 l2_invalidations;\n\tu64 l2_generation;')
new={'airoha_ppe.c':t,'airoha_eth.h':h}
patch='Subject: [PATCH] XR: exact bridge actions and revoke in-flight PPE rules\n\n'
for n,s in new.items():
 old=(parent/('before-'+n)).read_text()
 (out/('before-'+n)).write_text(old);(out/n).write_text(s)
 path='drivers/net/ethernet/airoha/'+n
 patch+=''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
(out/'99999g-XR-exact-PPE-bridge-publication.patch').write_text(patch)
report={'prepared':True,'parent':'development/ap31/ppe-vlan','candidateSHA256':{n:hashlib.sha256(s.encode()).hexdigest() for n,s in new.items()},'productionOrDeviceChanged':False,'policyExceptionOrRulePublisherImplemented':False}
(out/'prepared.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
