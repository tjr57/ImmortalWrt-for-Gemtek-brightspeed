"""Record exact-source remaining policy mutation sites without changing devices."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
items=[
 ('net/bridge/br_vlan.c','br_vlan_filter_toggle','br_opt_toggle(br, BROPT_VLAN_ENABLED, !!val);','switchdev_port_attr_set(br->dev, &attr, extack);',
  'Software filtering flag changes before switchdev revocation. Add pre-change fence including rollback; cover PVID, protocol, VLAN membership and flush as separate entry points.'),
 ('net/bridge/br_netlink.c','br_setport','br_set_port_flag(p, tb, IFLA_BRPORT_MODE, BR_HAIRPIN_MODE);','br_switchdev_set_port_flag(p, p->flags, changed_mask, extack);',
  'Port flags change before switchdev notification; MAB validation failures restore flags. Fence the whole mutating scope and test rollback, isolation, locked/MAB and tunnel changes.'),
 ('net/bridge/br_sysfs_if.c','store_flag','br_switchdev_set_port_flag(p, flags, mask, &extack);','p->flags = flags;',
  'Opposite order to netlink: notification occurs before mutation. RTNL serializes TC callbacks, but packet bind must stay fenced through completed mutation.'),
]
findings=[]
for path,fn,a,b,note in items:
 s=(k/path).read_text();pos=s.index(fn+'(');first=s.index(a,pos);second=s.index(b,pos);assert first<second
 findings.append({'path':path,'sha256':hashlib.sha256(s.encode()).hexdigest(),'function':fn,
  'firstLine':s[:first].count('\n')+1,'secondLine':s[:second].count('\n')+1,
  'finding':note,'codeOnlyEvidence':True,'hardwareFaultReproduced':False})
report={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'baseline':'20261011-ap32-d331711d',
 'findings':findings,'nextImplementation':'Extend existing br_fwd_change scope to VLAN/port policies, with VM transitions and failure cleanup; assess other netdevice/MST/MRP writers.',
 'TCRemaining':'skip_hw filters and generic actions may never call Airoha offload callbacks; mere TC notifier/readback polling cannot qualify automatic publication. Review mutation ordering and owner-aware policy before executor activation.',
 'LifetimeRemaining':'Review permanent revocation before notifier unregistration/driver teardown, not only registration.',
 'currentAP32Scope':'FDB/STP and packet context epoch; not a complete bridge/TC policy handoff',
 'devicesOrProductionCodeChanged':False}
p=w/'development/ap32/next-policy-audit.json';p.write_text(json.dumps(report,indent=2)+'\n')
dest=r/'scripts/xr1710g/ap32'
shutil.copy2(p,dest/p.name);shutil.copy2(w/'environment/record-ap32-next-policy-audit.py',dest/'record-ap32-next-policy-audit.py')
subprocess.run(['git','add','--','scripts/xr1710g/ap32'],cwd=r,check=True)
print(json.dumps({'recorded':True,'findings':len(findings),'deviceChanged':False}))
