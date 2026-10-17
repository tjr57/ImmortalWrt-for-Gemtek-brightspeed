from pathlib import Path
import hashlib,json
w=Path('D:/ChatGPT/XR1710G');r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt')
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581';out=w/'development/ap26'
files={
 'mac80211':b/'mac80211-regular/backports-7.2/net/mac80211/iface.c',
 'mt7996':b/'mt76-2026.09.01~be5ce791/mt7996/main.c',
 'netfilter':b/'linux-6.18.54/net/netfilter/core.c',
 'ppe':b/'linux-6.18.54/drivers/net/ethernet/airoha/airoha_ppe.c',
}
def function(text,name):
 start=text.index(name+'(');opening=text.index('{',start);depth=0
 for i in range(opening,len(text)):
  depth+=(text[i]=='{')-(text[i]=='}')
  if depth==0:return text[start:i+1]
 raise ValueError(name)
source={k:p.read_text() for k,p in files.items()}
forward=function(source['mac80211'],'ieee80211_netdev_fill_forward_path')
header=function(source['mac80211'],'ieee80211_iftype_supports_hdr_offload')
assert 'case NL80211_IFTYPE_MESH_POINT:' not in forward and 'case NL80211_IFTYPE_MESH_POINT:' not in header
assert 'case NL80211_IFTYPE_AP:' in forward and 'case NL80211_IFTYPE_STATION:' in forward
assert 'if (pf == NFPROTO_BRIDGE)' in source['netfilter'] and 'blocking_notifier_call_chain(&nf_bridge_policy_chain' in source['netfilter']
live=json.loads((out/'bridge-live-context.json').read_text())
assert live['ppePolicy']['stdout'].strip()=='Y' and live['bridgeTable']['stdout'].strip()=='table bridge fw4 {\n}'
assert all(row.endswith('=0') for row in live['bridgeSysctls']['stdout'].splitlines())
report={'status':'remaining-paths-identified','version':'20261010-ap26-d331711d',
 'wirelessDmaAndPpeAreSeparate':True,
 'meshFullPpeEgressSupportedByCurrentMac80211':False,
 'facts':[
  'Actual mac80211 forward-path resolver handles AP_VLAN/AP/STATION, but has no MESH_POINT case.',
  'Header encapsulation/decapsulation offload helper allows AP/STATION only; Mesh does not get this Ethernet-header offload path.',
  'PPE bridge binding requires explicit context-matched TC templates; legacy bridge sysctl switches do not publish them.',
  'AP1 live bridge fw4 table is empty and all six bridge-nf sysctls are zero, yet the driver policy latch is Y.',
  'Current netfilter notifier latches software fallback on any bridge hook registration, irrespective of sysctl activity.',
  'PPE options belong to built-in airoha_eth and are boot-only; /etc/modules.d is not an activation path for this built-in driver.',
 ],
 'nextWork':[
  'Measure WLAN NPU DMA on the real wired/Mesh transit path independently of PPE.',
  'For full Mesh PPE, establish firmware capability for 802.11s header, mesh path, TTL/sequence and peer lifetime before changing the software rejection.',
  'Implement exact permitted-rule publication and retain VLAN/namespace/FDB/firewall policy revocation; avoid broad MAC-only bypass of active policy.',
  'Review inactive bridge hooks separately from active filtering, with ordered revocation before policy activation.',
 ],
 'limits':['No claim that firmware has or lacks undocumented Mesh header support','No PPE options or firewall policies were changed in this audit'],
 'sourceSHA256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in files.items()},
 'functions':{'mac80211ForwardPath':forward,'mac80211HeaderOffload':header}}
(out/'ppe-topology-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'recorded':True,'currentMeshFullPpePath':False,'wirelessNpuDmaTestIsSeparate':True,'devicesChanged':False}))
