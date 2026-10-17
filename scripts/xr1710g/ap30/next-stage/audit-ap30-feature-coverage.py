"""Refresh scoped feature coverage against current source and frozen AP30 evidence."""
from pathlib import Path
from datetime import datetime
import hashlib, json

w=Path('D:/ChatGPT/XR1710G')
r=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt')
ld=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581'
mt=ld/'mt76-2026.09.01~be5ce791'
bp=ld/'mac80211-regular/backports-7.2'
k=ld/'linux-6.18.54'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
j=lambda p:json.loads(p.read_text(encoding='utf-8'))
old=j(w/'development/ap19-candidate-audit/current-topology-decisions.json')
evidence=[]
for label,item in old['effectiveSourceEvidence'].items():
    p=Path('//wsl.localhost/Debian-XR1710G'+item['path'])
    digest=sha(p)
    assert digest==item['SHA256'],label
    evidence.append({'check':label,'path':item['path'],'SHA256':digest,'unchangedSinceSemanticReview':True})
packed=j(w/'development/ap30/packed-files-qa.json')
assert packed['passed']
cac=j(w/'development/ap22/compiled-cac-qa.json')
assert cac['passed']
assert packed['matchedFiles']['lib/modules/6.18.54/cfg80211.ko']==cac['packedCfg80211SHA256']
for name,digest in cac['sourceSHA256'].items():assert sha(bp/name)==digest
functions=j(w/'development/ap18/compiled-source-qa.json')['functionHashes']
def fn(p,sig):
    t=p.read_text();start=t.index(sig)
    return t[start:t.index('\n}\n',start)+3]
current={}
for name,p,sig in [
    ('STA PP',mt/'mt7996/mcu.c','int mt7996_mcu_set_pp_sta_dscb('),
    ('PPE revocation',k/'drivers/net/ethernet/airoha/airoha_ppe.c','static int airoha_ppe_l2_policy_event('),
    ('PPE predicates',k/'drivers/net/ethernet/airoha/airoha_ppe.c','static bool airoha_ppe_l3_rule_exact(')]:
    current[name]=hashlib.sha256(fn(p,sig).encode()).hexdigest()
    assert current[name]==functions[name]
current['MCU stats whole source']=sha(mt/'mt7996/xr_stats.c')
assert current['MCU stats whole source']==functions['MCU stats whole source']
prior_ft=j(w/'development/ap24/packed-files-qa.json')['matchedFiles']
ft_files=['usr/libexec/xr1710g-ft-proxy-send','usr/libexec/xr1710g-ft-proxy-loop','etc/init.d/xr1710g_ft_proxy']
assert all(packed['matchedFiles'][p]==prior_ft[p] for p in ft_files)
t=(mt/'mt7996/main.c').read_text();start=t.index('mt7996_mac_sta_init_link(');end=t.index('\nvoid mt7996_mac_sta_remove_link(',start)
assert 'CONN_STATE_DISCONNECT' not in t[start:end]
groups=old['groups']
for group in groups:
    group['hardwareAcceptanceProvenByThisAudit']=False
    if group['name']=='后台 CAC／零等待 DFS':
        group.update(coverage='AP22 overlap geometry, cancellation, completion ownership and IRQ abort fixes remain in AP30 source and identical packed cfg80211.',
                     decision='Applicable implementation present; retain disabled pending physical radar/channel validation.',
                     covered='implemented and offline-tested; physical radar not accepted',
                     portNeededForCurrentTopology=False)
    if group['name']=='MRU／MURU':
        group['portNeededForCurrentTopology']=False
        group['decision']='Automatic OFDMA/MU-MIMO and the reconnect fix remain present. Do not claim unverified firmware MRU scheduling or force engineering allocations.'
ppe_old=j(w/'development/ap26/ppe-topology-audit.json')
ppe_sources={'mac80211':bp/'net/mac80211/iface.c','mt7996':mt/'mt7996/main.c',
             'netfilter':k/'net/netfilter/core.c','ppe':k/'drivers/net/ethernet/airoha/airoha_ppe.c'}
assert {key:sha(p) for key,p in ppe_sources.items()}==ppe_old['sourceSHA256']
report={
    'at':datetime.now().astimezone().isoformat(),'version':packed['version'],
    'scope':'Current separated-band AP topology and pinned previously reviewed source snapshots',
    'sourceEvidence':evidence,'unchangedTestedFunctions':current,
    'FTPackedFilesIdenticalToAP24':True,'OFDMAReconnectFixPresent':True,
    'CACFiveSourcesAndPackedModuleMatchAP22':True,
    'originalFive':[
        {'feature':'FT Mesh bootstrap/refresh','implementation':'present in AP30','remaining':'phone/cold-start/roaming acceptance separately; no missing code identified by this review'},
        {'feature':'NPU TXFREE','implementation':'AP24 startup-prefill fix present','remaining':'new AP30 NPU transit and stability qualification; historical other faults not declared fixed'},
        {'feature':'PPE policy/transit','implementation':'exact rule predicates, policy revocation and software fallback present','remaining':'applicable exact-rule publication and real-path hardware acceptance; Mesh header/egress capability unresolved'},
        {'feature':'MCU statistics','implementation':'bounded opt-in parser and polling present, exact tested source unchanged','remaining':'firmware ABI and live statistics acceptance; default off'},
        {'feature':'STA/automatic/MLO puncturing','implementation':'STA transport and automatic per-link work already ported','remaining':'physical firmware/RF and client acceptance; current Mesh is not an extender STA or user MLD'}],
    'candidateGroups':groups,
    'PPE':{'sourceUnchangedSinceAP26Audit':True,'meshEgressAndHeaderOffloadSupportedByCurrentMac80211':False,
           'firmwareMeshHeaderCapability':'unproven; software rejection is not proof of immutable hardware inability',
           'wirelessDmaSeparateFromPpe':True,'policyPublicationAndLiveQualificationRemain':True},
    'allInternetProjectsExhaustivelyReviewed':False,'physicalFeatureAcceptance':False,
    'newDeviceOperations':False,
    'next':'Finish AP30 NPU trial and PPE applicable-path implementation; do not reimplement completed candidate ports or claim disabled experimental features passed hardware tests.'}
p=w/'development/ap30/feature-coverage.json';assert not p.exists()
p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':True,'semanticSourceChecksRebound':len(evidence),'originalFive':5,'candidateGroups':len(groups),'CACImplementationPresent':True,'PPEStillIncomplete':True}))
