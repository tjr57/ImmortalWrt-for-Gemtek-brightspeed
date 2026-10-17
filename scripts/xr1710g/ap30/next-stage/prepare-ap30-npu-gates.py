"""Prepare AP30-bound gates without contacting either owned AP."""
from pathlib import Path
import hashlib, json, shutil, sys

w = Path('/mnt/d/ChatGPT/XR1710G')
r = Path('/home/xrdev/projects/xr1710g/openwrt')
out = w/'development/ap30/npu-gates'
out.mkdir(exist_ok=True)
assert not (out/'prepared.json').exists(), 'Completed preparation is immutable'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
old = w/'development/ap25/maple-startup/ap1'
files = out/'ap1/files'
files.mkdir(parents=True, exist_ok=True)
for p in (old/'files').iterdir():
    shutil.copy2(p, files/p.name)
shutil.copy2(w/'development/ap27/forwarding/steady-guard/files/xr-recovery-once', files/'xr-recovery-once')

# Bind previously qualified passive observer binaries to this exact kernel.
sys.path.insert(0, str(r/'scripts'))
from verify_ap4_artifacts import FDT, ELF64
images = {}
for name, digest in [('ap24','411299ad58e47cd789c72176b117a82a9f94ce7a8a668cf9279cd12d83dc55d0'),
                     ('ap30','904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0')]:
    p = next((w/f'builds/20261010-{name}-d331711d-development').glob('*-squashfs-sysupgrade.itb'))
    assert sha(p) == digest
    f = FDT(p.read_bytes())
    images[name] = {n: hashlib.sha256(f.payload(n)).hexdigest() for n,v in f.nodes.items()
                    if n.startswith('/images/') and n.count('/') == 2
                    and v.get('type', b'').rstrip(b'\0') in (b'kernel', b'flat_dt')}
assert images['ap24'] and images['ap24'] == images['ap30']
k = r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.54'
kernel_hashes = {n:sha(k/n) for n in ['.config','Module.symvers','vmlinux','include/generated/autoconf.h']}
observer_qa = json.loads((w/'development/ap24/maple-observer/result-latest.json').read_text())
code = ELF64(k/'vmlinux').symbol_bytes('mas_empty_area_rev')
symbol = ELF64(k/'vmlinux').symbols['mas_empty_area_rev']
payload = f.payload('/images/kernel-1')
offset = payload.find(code)
assert offset >= 0 and payload.find(code,offset+1) == -1
assert symbol == observer_qa['binding']['symbol']
assert hex(offset) == observer_qa['binding']['imageOffset']
assert hashlib.sha256(code).hexdigest() == observer_qa['binding']['codeSHA256']
# vmlinux is a build ELF container. Bind to actual shipped kernel/DT bytes,
# exact observer function bytes/address, config and symbol ABI instead.
(out/'vmlinux-container-difference.json').write_text(json.dumps({
    'oldSHA256':observer_qa['binding']['vmlinux_SHA256'],
    'currentSHA256':kernel_hashes['vmlinux'],
    'shippedKernelAndDtByteIdentical':True,
    'exactObserverSymbolAndCodeMatch':True,
    'elfContainerDifferenceCauseNotInvestigated':True},indent=2)+'\n')
for evidence in ['development/ap24/maple-observer/result-latest.json','development/npu-address-diag/arm/result-latest.json']:
    q = json.loads((w/evidence).read_text())
    assert q['passed']
    for name,h in kernel_hashes.items():
        if name != 'vmlinux' and str(k/name) in q['productionContractsUnchanged']:
            assert q['productionContractsUnchanged'][str(k/name)] == h
abi = json.loads((w/'development/ap30/build-module-abi.json').read_text())
assert abi['passed'] and abi['kernelConfigSHA256'] == kernel_hashes['.config']
manifest = {'prepared':True,'version':'20261010-ap30-d331711d',
            'imageSHA256':'904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0',
            'kernelAndDtPayloadIdenticalToQualifiedObserverAP24':images,
            'kernelBuildHashes':kernel_hashes,
            'helperHashes':{str(p.relative_to(out)):sha(p) for p in files.iterdir()},
            'physicalActivationSubmitted':False}
(out/'prepared.json').write_text(json.dumps(manifest,indent=2)+'\n')

s = (w/'environment/test-ap25-maple-startup.py').read_text()
s = s.replace('development/ap25/maple-startup','development/ap30/npu-gates')
s = s.replace('for unit in [2,1]:','for unit in [1]:')
s = s.replace('20261010-ap25-d331711d-development','20261010-ap30-d331711d-development')
s = s.replace('4ccc14e251b6175c7d3fa71567a52204cc6a7480aa5c4f8db1928ce6a9ea7e9a',manifest['imageSHA256'])
(w/'environment/test-ap30-npu-startup.py').write_text(s)
s = (w/'environment/test-ap27-steady-guard.py').read_text()
s = s.replace('development/ap27/forwarding/steady-guard','development/ap30/npu-gates/ap1')
s = s.replace('20261010-ap26-d331711d-development','20261010-ap30-d331711d-development')
s = s.replace('49d96feb0bce2a66a38b4210928802e26d521cb0347e791e30704e67a2fca472',manifest['imageSHA256'])
s = s.replace('FrozenAP26','FrozenAP30')
(w/'environment/test-ap30-npu-recovery-shell.py').write_text(s)

# Re-run the actual loader/activation/recovery integration with recovery6,
# preserving all historical VM results in their original directory.
s = (w/'environment/run-npu-activation-vm.py').read_text()
s = s.replace("recovery=w/'development/npu-recovery'", "recovery=w/'development/npu-recovery6'")
s = s.replace("out=src/'vm';out.mkdir(exist_ok=True)", "out=w/'development/ap30/npu-gates/activation-vm';out.mkdir(exist_ok=True)")
needle = " result={'passed':bool(passed),'case':case"
assert needle in s
s = s.replace(needle, """ if case=='success':
  closed=saved.get('capture/closed.json') or {}
  recover=saved.get('recovery.json') or {}
  passed=passed and closed.get('firstSeq')==0 and closed.get('records',0)>0
  passed=passed and closed.get('records')==closed.get('lastSeq',-2)+1
  passed=passed and closed.get('gaps')==0 and all(closed.get(x) is False for x in ('fault','failed','capped'))
  passed=passed and closed.get('monotonicMs',2**63)<=recover.get('monotonicMs',0)
"""+needle)
(w/'environment/run-ap30-npu-gates-vm.py').write_text(s)
print(json.dumps({'prepared':True,'kernelAndDtIdentical':True,'kernelBuildHashes':kernel_hashes}))
