from pathlib import Path
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap27'
assert json.loads((out/'packed-files-qa.json').read_text())['passed']
p=w/'environment/ap27-deploy.py';assert not p.exists()
s=(w/'environment/ap26-deploy.py').read_text().replace('ap26','ap27').replace('AP26','AP27').replace('20261010-ap25-d331711d','20261010-ap26-d331711d')
s=s.replace("gate['vmPrecheckPassed']","gate['preflashChecksPassed']")
s=s.replace("assert json.loads((root/'rpc-qa.json').read_text())['passed'] and json.loads((root/'ui-packed-qa.json').read_text())['passed']", "assert json.loads((root/'ping-rxbuf/live-queue-qa.json').read_text())['passed'] and json.loads((root/'mesh-rx-audit/qa/result.json').read_text())['passed']")
s=s.replace("('lib/modules/','etc/init.d/','usr/','www/')", "('bin/','lib/modules/','etc/init.d/','usr/','www/')")
anchor=" assert all(absent(c,p) for p in markers)"
assert anchor in s
s=s.replace(anchor," assert read(c,'cat /sys/module/mac80211/parameters/mesh_rx_drop_audit')=='N'\n assert read(c,'cat /sys/module/mac80211/parameters/mesh_rx_drop_events').startswith('schema=1 enabled=0 total=0 retained=0')\n"+anchor,1)
p.write_text(s);assert "BASELINE='20261010-ap26-d331711d'" in s
dest=r/'scripts/xr1710g/ap27'
for n in ['check-ap27-build.py','prepare-ap27-deployment.py','ap27-deploy.py']:shutil.copy2(w/'environment'/n,dest/n)
p=r/'AGENTS.md';s=p.read_text();start=s.index('<!-- owner-pause-for-appeal-20261010 -->');end=s.index('<!-- authorized-diagnostics-policy-20261010 -->')
note='''<!-- owner-pause-for-appeal-20261010 -->
## AP27 forwarding-loss investigation resumed; candidate ready for AP2 then AP1

- Owner resumed on2026-10-10; all experiments use only the two owned APs.
- Current stable AP26 boot AP1 d2698d50-eb8b-4cc9-8b88-7cccc47290af;
  AP2 1e877aa4-b206-48bd-bd43-6ddaa1b22505. No pending NPU activation.
- AP27 software baseline20s/P4 935.36/1137.86Mbps;105/105 each peer.
  Later low-rate software-only rounds reproduced two distinct loss stages:
  local raw ICMP receive-queue overflow and egress-to-peer-ingress Mesh loss.
- BusyBox receive-queue fix proven in controlled ARM hardware A/B: old4/6
  twice with all replies already at all4 observation points; candidate6/6
  twice, zero socket drops. Does NOT repair/prove root of wireless-stage loss.
- AP27 image eb960f6f290db9092608be716ee3de69d126ab0ae4a7e093cc197d33b3aa159f
  built-j12, ABI passed, kernel/DT unchanged; only BusyBox/mac80211 binaries
  and package/version metadata differ. Default-off32-entry scalar Mesh drop
  recorder passed nativeASan/UBSan, actual ARM and concurrent recorder tests.
- Upgrade AP2 first, verify normal return before AP1. State is
  development/ap27/deployment/apN; never repeat any scheduled.json operation.
- All earlier AP27 trials are complete; do not rerun one-shot journals.
  Prepared steady-npu-3 was NOT run and MUST be replaced before future use:
  old recovery helper races hard deadline, and forwarding loss unresolved.
- Recovery6 repair passed18 real VM reboot-pair cases and package compilation;
  not live-qualified and not included in AP27 image. Healthy collector does
  not save full kernel.kmsg; closure metadata is required for completeness.
- Evidence: development/ap27/forwarding, ping-rxbuf/live-queue-qa.json,
  mesh-rx-audit/qa/result.json and development/npu-recovery6.

'''
p.write_text(s[:start]+note+s[end:])
subprocess.run(['git','add','--','AGENTS.md','xr1710g-ap.config','scripts/xr1710g/ap27','package/utils/busybox/Makefile','package/utils/busybox/patches/901-ping-receive-queue-headroom.patch','package/kernel/mac80211/Makefile','package/kernel/mac80211/patches/subsys/9999d-XR-opt-in-Mesh-RX-drop-metadata.patch'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
subprocess.run(['python3',str(w/'environment/record-ap-build.py'),'--version','20261010-ap27-d331711d','--destination-name','20261010-ap27-d331711d-development','--artifact-report',str(out/'artifact-qa.json'),'--defaults-qa',str(out/'defaults-qa.json'),'--build-log','build-ap27.log'],check=True)
