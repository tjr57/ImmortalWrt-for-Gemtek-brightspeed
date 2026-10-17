from pathlib import Path
import json,shutil,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap26'
assert json.loads((out/'packed-files-qa.json').read_text())['passed']
dest=w/'environment/ap26-deploy.py';assert not dest.exists()
s=(w/'environment/ap25-deploy.py').read_text().replace('ap25','ap26').replace('AP25','AP26').replace('20261010-ap24-d331711d','20261010-ap25-d331711d')
s=s.replace("assert json.loads((root/'guard-qa.json').read_text())['passed'] and json.loads((root/'negative-control.json').read_text())['passed']", "assert json.loads((root/'rpc-qa.json').read_text())['passed'] and json.loads((root/'ui-packed-qa.json').read_text())['passed']")
anchor=" (out/'accepted-kernel.txt').write_bytes(clean(c));current_checks(c,state)"
assert anchor in s
s=s.replace(anchor,""" policy=json.loads(read(c,"ubus call luci.airoha_npu getDeviceMode '{}'"))
 assert policy['ppe_binding_enabled'] is False and policy['ppe_bridge_binding_enabled'] is False
 assert policy['ppe_bridge_policy_latched'] is True and policy['bridge_offload_block_reason']=='ppe_boot_policy_disabled'
 save('ppe-policy-live.json',policy)
"""+anchor)
dest.write_text(s)
assert "BASELINE='20261010-ap25-d331711d'" in s
d=r/'scripts/xr1710g/ap26'
for name in ['test-ap26-ppe-control.py','run-ap26-ui-only.py','check-ap26-build.py','prepare-ap26-deployment.py','ap26-deploy.py']:
 shutil.copy2(w/'environment'/name,d/name)
p=r/'AGENTS.md';s=p.read_text();marker='<!-- ap26-current -->';assert marker not in s
note='''<!-- ap26-current -->
## AP26 PPE bridge policy UI/RPC integration

- Built 20261010-ap26-d331711d with make world-j12. SHA256
  49d96feb0bce2a66a38b4210928802e26d521cb0347e791e30704e67a2fca472.
- Enforces separate bridge boot permission and kernel policy latch. Kernels
  requiring explicit TC templates reject legacy sysctl-only enable controls.
  Route/global PPE and WLAN DMA remain independent; defaults unchanged.
- RPC158 calls /14 scenarios include old-code negative control. Seven UI
  modes pass in source and packed/minified view. Full rootfs delta9 files;
  kernel/DT/modules/boot/SSH/Mesh/guard/defaults byte-identical to AP25.
- AP25 software transit baseline PC->switch->AP1 bridge->6GHz->AP2 endpoint:
  998.10Mbps forward /1240.58Mbps reverse,30s/P4 each. Both healthy, no
  configuration change. This is not hardware acceleration qualification.
- Deployment state is development/ap26/deployment/apN/result.json. Each
  scheduled.json is one-shot; never repeat a submitted flash. AP2 first,
  healthy return before AP1. Maple owner deferral above remains controlling.

'''
pos=s.index('<!-- owner-home-');s=s[:pos]+note+s[pos:];p.write_text(s)
subprocess.run(['git','add','--','scripts/xr1710g/ap26','AGENTS.md'],cwd=r,check=True)
subprocess.run(['git','-c','core.whitespace=cr-at-eol','diff','--cached','--check'],cwd=r,check=True)
subprocess.run(['python3',str(w/'environment/record-ap-build.py'),'--version','20261010-ap26-d331711d','--destination-name','20261010-ap26-d331711d-development','--artifact-report',str(out/'artifact-qa.json'),'--defaults-qa',str(out/'defaults-qa.json'),'--build-log','build-ap26.log'],check=True)
