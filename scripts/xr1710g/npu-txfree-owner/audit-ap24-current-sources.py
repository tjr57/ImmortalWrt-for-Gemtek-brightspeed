"""Bind inherited actual-function tests and compiled code to AP24 artifacts."""
from pathlib import Path
import hashlib,json,importlib.util
from elftools.elf.elffile import ELFFile
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap24/current-source-audit';out.mkdir(exist_ok=True)
ld=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581';mt=ld/'mt76-2026.09.01~be5ce791';k=ld/'linux-6.18.54';rf=r/'build_dir/target-aarch64_cortex-a53_musl/root-airoha'
j=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def fn(p,sig):
 t=p.read_text();s=t.index(sig);return t[s:t.index('\n}\n',s)+3]
previous=j(w/'development/ap18/compiled-source-qa.json')['functionHashes'];matched={}
for name,p,sig in [('STA PP',mt/'mt7996/mcu.c','int mt7996_mcu_set_pp_sta_dscb('),('NPU anomaly',mt/'npu.c','static void mt76_npu_rx_anomaly('),('NPU chain',mt/'npu.c','static int mt76_npu_txfree_chain('),('PPE revocation',k/'drivers/net/ethernet/airoha/airoha_ppe.c','static int airoha_ppe_l2_policy_event('),('PPE predicates',k/'drivers/net/ethernet/airoha/airoha_ppe.c','static bool airoha_ppe_l3_rule_exact(')]:
 digest=hashlib.sha256(fn(p,sig).encode()).hexdigest();assert digest==previous[name],name;matched[name]=digest
matched['MCU stats whole source']=sha(mt/'mt7996/xr_stats.c');assert matched['MCU stats whole source']==previous['MCU stats whole source']
# Fresh FT sanitizer test uses today's source and writes only a new report.
t=(w/'environment/test-ap18-ft-proxy.py').read_text().replace('development/ap18/ft-proxy','development/ap24/current-source-audit/ft-proxy');exec(compile(t,'AP24-current-FT-source','exec'),{})
src=r/'package/network/config/xr1710g-ft-proxy/src/proxy.c';bd=r/'build_dir/target-aarch64_cortex-a53_musl/xr1710g-ft-proxy';assert src.read_bytes()==(bd/'proxy.c').read_bytes()
spec=importlib.util.spec_from_file_location('lab',w/'environment/build-npu-diagnostic-lab.py');lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)
ft_sections=lab.match_executable(bd/'xr1710g-ft-proxy-send',rf/'usr/libexec/xr1710g-ft-proxy-send')
packed=j(w/'development/ap24/packed-files-qa.json')['matchedFiles'];assert sha(rf/'usr/libexec/xr1710g-ft-proxy-send')==packed['usr/libexec/xr1710g-ft-proxy-send']
def sections(p):
 with p.open('rb') as f:
  e=ELFFile(f);assert e['e_machine']=='EM_AARCH64';return {s.name:hashlib.sha256(s.data()).hexdigest() for s in e.iter_sections() if s['sh_flags']&4 and s['sh_size']}
modules={}
for name,compiled in [('mt76.ko',mt/'mt76.ko'),('mt7996e.ko',mt/'mt7996/mt7996e.ko')]:
 shipped=rf/'lib/modules/6.18.54'/name;assert sections(compiled)==sections(shipped);assert sha(shipped)==packed['lib/modules/6.18.54/'+name];modules[name]=sha(shipped)
pub=j(w/'development/ap19-driver-fixes/npu-publication-qa.json');assert hashlib.sha256(fn(mt/'npu.c','int mt76_npu_dma_add_buf(').encode()).hexdigest()==pub['sourceFunctionSHA256']
t=(mt/'mt7996/main.c').read_text();s=t.index('mt7996_mac_sta_init_link(');z=t.index('\nvoid mt7996_mac_sta_remove_link(',s);assert 'CONN_STATE_DISCONNECT' not in t[s:z] and t.count('CONN_STATE_DISCONNECT')>=2
control=j(out/'control-qa.json');assert control['passed'] and control['programSHA256']==packed['usr/sbin/xr1710g-ap-feature-control'] and control['configuratorSHA256']==packed['usr/sbin/xr1710g-ap-configure']
# Candidate decisions are scoped to the current topology, not all Internet code.
candidates=j(w/'development/ap19-candidate-audit/current-topology-decisions.json');assert candidates['reviewCompleteForCurrentTopology'] and len(candidates['groups'])==7
cac=j(w/'development/ap24/compiled-cac-qa.json');backports=ld/'mac80211-regular/backports-7.2'
for p,h in cac['sourceSHA256'].items():assert sha(backports/p)==h
report={'passed':True,'version':'20261010-ap24-d331711d','actualFunctionHashes':matched,'FTSourceSHA256':sha(src),'FTSanitizerCases':10,'FTExecutableSectionsMatched':ft_sections,'moduleHashes':modules,'controlCases':len(control['checks']),'currentControllerAndConfiguratorTestedTogether':True,'OFDMAReconnectFixPresent':True,'CACFiveSourcesStillMatchQualifiedSource':True,'candidateGroupCount':7,'candidateDecisions':candidates['groups'],'limits':['Offline behavior and artifact provenance, not phone/physical RF acceptance','PPE compiled-in kernel is bound by the accepted AP22/AP24 kernel payload checks','Deferred MLD features remain explicitly unavailable for the current single-link user topology']}
(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'passed':True,'functions':len(matched),'controlCases':len(control['checks']),'FTChecks':10,'candidates':7}))
