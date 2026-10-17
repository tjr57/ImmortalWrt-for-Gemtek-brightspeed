"""Prepare private bridge eligibility candidate; never edit production sources."""
from pathlib import Path
import difflib, hashlib, json

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
k = r / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
parent = w / 'development/ap31/ppe-revocation'
out = w / 'development/ap31/ppe-context'
out.mkdir()

def replace(s, a, b):
    assert s.count(a) == 1, (a[:80], s.count(a))
    return s.replace(a, b, 1)

ppe = (parent / 'airoha_ppe.c').read_text()
header = (parent / 'airoha_eth.h').read_text()
bridge_header = (k / 'include/linux/if_bridge.h').read_text()
fdb = (k / 'net/bridge/br_fdb.c').read_text()

helper = '''/* Only a learned/remote forwarding entry may authorize a PPE redirect.
 * Keep the lookup and flags inside the caller's RCU section. Unlike
 * br_fdb_find_port(), this API never returns an unreferenced device and does
 * not mistake an FDB entry for a local address for a forwarding permission.
 */
bool br_fdb_forward_to_rcu(const struct net_device *br_dev,
                          const struct net_device *port_dev,
                          const unsigned char *addr, u16 vid)
{
 const struct net_bridge_port *dst;
 struct net_bridge_fdb_entry *f;
 struct net_bridge *br;

 if (!netif_is_bridge_master(br_dev) || !is_valid_ether_addr(addr))
  return false;
 br = netdev_priv(br_dev);
 f = br_fdb_find_rcu(br, addr, vid);
 if (!f || test_bit(BR_FDB_LOCAL, &f->flags) ||
     test_bit(BR_FDB_LOCKED, &f->flags) || has_expired(br, f))
  return false;
 dst = READ_ONCE(f->dst);
 return dst && dst->dev == port_dev;
}
EXPORT_SYMBOL_GPL(br_fdb_forward_to_rcu);

'''
fdb = replace(fdb, 'EXPORT_SYMBOL_GPL(br_fdb_find_port);\n', 'EXPORT_SYMBOL_GPL(br_fdb_find_port);\n\n' + helper)
decl = '''bool br_fdb_forward_to_rcu(const struct net_device *br_dev,
                          const struct net_device *port_dev,
                          const unsigned char *addr, u16 vid);
'''
bridge_header = replace(bridge_header, '#if IS_ENABLED(CONFIG_BRIDGE)\n', '#if IS_ENABLED(CONFIG_BRIDGE)\n' + decl)
stub = '''static inline bool br_fdb_forward_to_rcu(const struct net_device *br_dev,
                                        const struct net_device *port_dev,
                                        const unsigned char *addr, u16 vid)
{
 return false;
}

'''
bridge_header = replace(bridge_header, '#else\nstatic inline struct net_device *\nbr_fdb_find_port', '#else\n' + stub + 'static inline struct net_device *\nbr_fdb_find_port')

port_helper = '''/* Unsupported per-port policy stays in the software bridge. MST can
 * have a per-VLAN forwarding state distinct from the port STP state.
 */
static bool airoha_ppe_l2_port_eligible(struct net_device *dev)
{
 const unsigned long unsupported = BR_ISOLATED | BR_PORT_LOCKED | BR_PORT_MAB |
  BR_VLAN_TUNNEL | BR_PROXYARP | BR_PROXYARP_WIFI | BR_NEIGH_SUPPRESS |
  BR_NEIGH_VLAN_SUPPRESS | BR_MRP_AWARE;

 return netif_running(dev) && netif_carrier_ok(dev) &&
        br_port_get_stp_state(dev) == BR_STATE_FORWARDING &&
        !br_port_flag_is_set(dev, unsupported);
}

'''
ppe = replace(ppe, '/* Use actual bridge port membership, PVID and output tag policy. */', port_helper + '/* Use actual bridge port membership, PVID and output tag policy. */')
ppe = replace(ppe, '!netif_is_bridge_port(indev) || !netif_is_bridge_port(odev))', '!netif_is_bridge_port(indev) || !netif_is_bridge_port(odev) ||\n     !airoha_ppe_l2_port_eligible(indev) ||\n     !airoha_ppe_l2_port_eligible(odev))')
ppe = replace(ppe, 'if (!master || !net_eq(dev_net(indev), dev_net(odev)) ||', 'if (!master || br_mst_enabled(master) ||\n     !net_eq(dev_net(indev), dev_net(odev)) ||')
ppe = replace(ppe, ' if (!airoha_ppe_l2_actions(rule, vid, tagged, untagged, data))', ''' /* A normal bridge preserves PCP/DEI on tagged-to-tagged forwarding.
  * POP/PUSH with priority zero is a valid explicit TC action, but does not
  * preserve that bridge policy for all packets of a MAC-only template.
  */
 if (tagged && !untagged)
  goto out;
 if (!br_fdb_forward_to_rcu(master, indev, data->eth.h_source, vid) ||
     !br_fdb_forward_to_rcu(master, odev, data->eth.h_dest, vid))
  goto out;
 if (!airoha_ppe_l2_actions(rule, vid, tagged, untagged, data))''')
ppe = replace(ppe, '\tif (!airoha_ppe_rule_has_single_redirect(rule)) {', '''\t/* FOE has no classifier chain/goto context. */
\tif (f->common.chain_index) {
\t\tNL_SET_ERR_MSG_MOD(f->common.extack, "PPE only represents TC chain zero");
\t\treturn -EOPNOTSUPP;
\t}

\tif (!airoha_ppe_rule_has_single_redirect(rule)) {''')
ppe = replace(ppe, '\tdebugfs_create_u64("xr_l2_invalidations",', '''\tdebugfs_create_u64("xr_l2_generation", 0400, ppe->debugfs_dir,
\t\t\t   &ppe->l2_generation);
\tdebugfs_create_u64("xr_l2_invalidations",''')

files = {
 'drivers/net/ethernet/airoha/airoha_ppe.c': ppe,
 'drivers/net/ethernet/airoha/airoha_eth.h': header,
 'include/linux/if_bridge.h': bridge_header,
 'net/bridge/br_fdb.c': fdb,
}
patch = 'Subject: [PATCH] XR: validate PPE bridge context before publication\n\n'
hashes = {}
for path, contents in files.items():
    n = Path(path).name
    before = (parent / ('before-' + n)).read_text() if n.startswith('airoha_') else (k / path).read_text()
    (out / n).write_text(contents)
    (out / ('before-' + n)).write_text(before)
    hashes[n] = hashlib.sha256(contents.encode()).hexdigest()
    patch += ''.join(difflib.unified_diff(before.splitlines(True), contents.splitlines(True), fromfile='a/' + path, tofile='b/' + path))
(out / '99999g-XR-exact-PPE-bridge-publication.patch').write_text(patch)
report = {'prepared': True, 'parent': 'development/ap31/ppe-revocation', 'candidateSHA256': hashes,
          'productionOrDeviceChanged': False, 'rulePublisherOrCompletePolicyHandoff': False}
(out / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
