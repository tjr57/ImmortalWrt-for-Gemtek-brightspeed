"""Pin current source and fresh software-state observations for PPE scope."""
from pathlib import Path
from datetime import datetime
import json,hashlib
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581'
files={'mac80211':b/'mac80211-regular/backports-7.2/net/mac80211/iface.c',
 'mt7996':b/'mt76-2026.09.01~be5ce791/mt7996/main.c',
 'PPE':b/'linux-6.18.54/drivers/net/ethernet/airoha/airoha_ppe.c',
 'netfilter':b/'linux-6.18.54/net/netfilter/core.c',
 'br_netfilter':b/'linux-6.18.54/net/bridge/br_netfilter_hooks.c'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
src={k:p.read_text() for k,p in files.items()}
def fn(t,name):
 start=t.index(name+'(');opening=t.index('{',start);depth=0
 for i in range(opening,len(t)):
  depth+=(t[i]=='{')-(t[i]=='}')
  if depth==0:return t[start:i+1]
 raise ValueError(name)
forward=fn(src['mac80211'],'ieee80211_netdev_fill_forward_path')
header=fn(src['mac80211'],'ieee80211_iftype_supports_hdr_offload')
wdma=fn(src['mt7996'],'mt7996_net_fill_forward_path')
key=fn(src['PPE'],'airoha_ppe_skb_l2_key')
assert all('case NL80211_IFTYPE_MESH_POINT:' not in text for text in (forward,header))
assert all('case NL80211_IFTYPE_AP:' in text and 'case NL80211_IFTYPE_STATION:' in text for text in (forward,header))
assert '!mtk_wed_device_active(wed)' in wdma and '!mt76_npu_device_active(&dev->mt76)' in wdma
assert 'eh->h_proto != htons(ETH_P_IP)' in key and 'IPPROTO_TCP' in key and 'IPPROTO_UDP' in key
assert 'if (ppe->l2_policy_latched || !bridge_eligible)' in src['PPE']
assert 'blocking_notifier_call_chain(&nf_bridge_policy_chain' in src['netfilter']
live_path='development/ap30/forwarding/software-after-npu2/ap2-to-pc-after.json'
live=json.loads((w/live_path).read_text())
assert all(x['ppe']=='N' and x['ppeBridge']=='N' and x['npu']=='N' for x in live.values())
report={'at':datetime.now().astimezone().isoformat(),'sourceScope':'Current AP30 compiled source, before unintegrated AP31 candidate',
 'sourceSHA256':{k:sha(p) for k,p in files.items()},'functionsSHA256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in {'forward':forward,'headerOffload':header,'wdma':wdma,'bridgeKey':key}.items()},
 'freshLiveEvidence':live_path,'freshLivePolicy':{u:{k:row[k] for k in ['bootID','ppe','ppeBridge','npu','ppePolicy','bridgeFirewall']} for u,row in live.items()},
 'paths':[
  {'path':'wired to wired bridge','softwareForwarding':'available','PPE':'conditional code exists, not hardware-qualified',
   'requires':['both boot permissions','exact ingress/bridge/namespace/MAC/VLAN rule','representable action sequence','no active incompatible policy','real flow binding and traffic evidence']},
  {'path':'wired to ordinary5GHz AP client','softwareForwarding':'available','PPE':'forward resolver exists; not qualified',
   'requires':['valid live station/link/WCID','active NPU or WED transport','eligible exact rule and policy state','client-side evidence']},
  {'path':'wired to6GHz802.11s Mesh egress','softwareForwarding':'verified in AP30','PPE':'current mac80211 forward resolver and header-offload helper exclude Mesh',
   'requires':['firmware proof of802.11s header/TTL/sequence/peer-lifetime semantics before implementing a new path']},
  {'path':'Mesh ingress to wired/client egress','softwareForwarding':'available','PPE':'incoming Mesh DMA is not proof of an Ethernet-header hardware path',
   'requires':['separate ingress/header/context verification; do not infer symmetry from the AP egress resolver']},
  {'path':'IoT VLAN50','softwareForwarding':'current tagged bridge configuration preserved','PPE':'context key support exists; tagged/untagged action equivalence and real transit unqualified',
   'requires':['VLAN membership and egress-tag behavior','no widening into nativeLAN','FDB/VLAN/netns/policy revocation']},
  {'path':'IPv6 bridge','softwareForwarding':'software path retained','PPE':'current bridge eligibility only accepts IPv4 TCP/UDP; noIPv6 bridge qualification'}],
 'nextImplementation':['Complete exact rule publication with per-context ownership and revocation.',
  'Prove VLAN action sequence matches bridge egress tagging before accepting those templates.',
  'If inactive br_netfilter hooks are exempted, serialize any reauthorization against hook,sysctl and per-bridge policy activation before publication; never simply clear a latch.',
  'Keep unknown hooks and unrepresented constraints in software.'],
 'firmwareMeshCapability':'unproven; software exclusion does not prove immutable hardware inability',
 'NpuDmaNotEquivalentToPpeForwarding':True,'hardwareOffloadQualified':False,'liveDevicesModified':False}
(w/'development/ap30/ppe-path-scope.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'paths':len(report['paths']),'liveNpuPpeOffAtControlTime':True,'meshFullPpeSupportedByCurrentSource':False,'hardwareCapabilityUnproven':True}))
