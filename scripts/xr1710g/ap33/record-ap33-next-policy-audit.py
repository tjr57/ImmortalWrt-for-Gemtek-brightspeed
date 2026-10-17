"""Record source-level remaining policy work without changing live settings."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
k=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54';out=w/'development/ap33'
paths=['net/core/dev.c','net/core/rtnetlink.c','net/sched/cls_api.c','net/sched/act_api.c','net/sched/sch_api.c',
 'net/bridge/br_fdb.c','net/bridge/br_input.c','drivers/net/ethernet/airoha/airoha_ppe.c']
sources={p:(k/p).read_text() for p in paths}
def lines(p,needles):
 s=sources[p];ret={}
 for needle in needles:
  assert needle in s,(p,needle)
  ret[needle]=[i for i,line in enumerate(s.splitlines(),1) if needle in line]
 return ret
evidence={p:{'sha256':hashlib.sha256(s.encode()).hexdigest()} for p,s in sources.items()}
evidence['net/core/dev.c']['locations']=lines('net/core/dev.c',['NETDEV_PRECHANGEUPPER','NETDEV_PRECHANGEMTU','NETDEV_PRE_CHANGEADDR','NETDEV_GOING_DOWN'])
evidence['net/sched/cls_api.c']['locations']=lines('net/sched/cls_api.c',['RTNL_FLAG_DOIT_UNLOCKED','lockeddevcnt'])
evidence['net/core/rtnetlink.c']['locations']=lines('net/core/rtnetlink.c',['CAP_NET_ADMIN','rtnetlink_rcv_msg'])
ppe=sources[paths[-1]];a=ppe.index('static int airoha_ppe_l2_netdev_event(');b=ppe.index('\n}',a)+2
callback=ppe[a:b]
assert all(x in callback for x in ['NETDEV_DOWN','NETDEV_CHANGEUPPER','NETDEV_CHANGEADDR','NETDEV_CHANGEMTU'])
assert all(x not in callback for x in ['NETDEV_GOING_DOWN','NETDEV_PRE_CHANGEADDR','NETDEV_PRECHANGEMTU'])
report={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'sourceVersion':'20261011-ap33-d331711d',
 'sourceEvidence':evidence,'AP33Solved':['VLAN and port flags mutation/rollback scope','per-VLAN state eligibility','bridge membership/MST enable scope','L2 revocation before observer unregister'],
 'remainingFindings':[
 {'area':'netdevice mutation','finding':'PPE currently revokes on post-change notifications. Core provides pre-change events, but failed changes may omit matching post events; a simple begin-on-pre/end-on-post counter can leak or permit republishing during rollback.',
  'nextImplementation':'Review whole mutation scopes or a policy owner design; test MTU/address/upper-link success, rejection, rollback, and device close. Do not replace with polling.'},
 {'area':'TC policy','finding':'Generic filters can mutate without RTNL. lockeddevcnt serializes driver callbacks, but skip_hw policy need not call the offload driver at all. Exact own-rule parser/readback is insufficient to prove the entire ingress/egress policy.',
  'nextImplementation':'Kernel-observed TC policy lifetime/ownership must cover qdisc/filter/chain/actions and preexisting policy before an executor may publish. A dedicated non-TC publisher is a design option, not implemented or approved as a final design.'},
 {'area':'FDB expiry scope','finding':'The ordinary unicast bridge path calls br_fdb_find_rcu and forwards an existing nonlocal entry until actual deletion; has_expired is an extra conservative check in PPE qualification. AP32 fences actual FDB deletion. An ageing-time assignment alone is not proof of a software/hardware forwarding mismatch.',
  'nextImplementation':'Keep actual delete/move fence; review aging/refresh performance and hardware lease separately. Do not label an unproven cache-age root cause.'}],
 'unchangedConstraints':['No automatic publisher or hardware-binding acceptance','br_netfilter policy latch stays active','Mesh header path remains unqualified','NPU/PPE default off'],
 'hardwareFaultReproduced':False,'productionOrDeviceChanged':False}
(out/'next-policy-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'recorded':True,'findings':len(report['remainingFindings']),'hardwareTested':False}))
