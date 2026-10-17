"""Record immutable built-image gates; never submit or repeat an upgrade."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap33'
packed=json.loads((out/'packed-files-qa.json').read_text())
process=json.loads((out/'build-process.json').read_text())
gate=json.loads((out/'boot-lab/result.json').read_text())
image=next((w/('builds/'+packed['version']+'-development')).glob('*gemtek_xr1710g-squashfs-sysupgrade.itb'))
assert packed['passed'] and gate['preflashChecksPassed'] and process['exitCode']==0
assert process['wirelessKernelABIValidated'] and gate['imageSHA256']==packed['imageSHA256']==hashlib.sha256(image.read_bytes()).hexdigest()
assert not (out/'image-qualified.json').exists(),'Qualification already recorded'
now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
record={'at':now,'passed':True,'version':packed['version'],'imageSHA256':packed['imageSHA256'],
 'imageSize':packed['imageSize'],'bundle':str(image.parent.relative_to(w)),
 'kernelContractSHA256':process['kernelContractSHA256'],'jobs':12,'packedFiles':len(packed['matchedFiles']),
 'rootfsChanges':json.loads((out/'rootfs-delta.json').read_text())['changedPaths'],
 'evidence':{'image':'development/ap33/packed-files-qa.json','ABI':'development/ap33/build-module-abi.json',
 'defaults':'development/ap33/defaults-qa.json','VM':'development/ap33/bridge-policy/vm-result.json'},
 'automaticPublisherShipped':False,'NpuPpeDefaultsChanged':False,'wholeHardwareQualification':False}
(out/'image-qualified.json').write_text(json.dumps(record,indent=2)+'\n')
p=w/'development/current-goal.json';g=json.loads(p.read_text())
g['latestAP33ImageBuild'].update(imageQualified=True,qualification=record)
g['preflashPolicy'].update(currentCandidate=packed['version'],currentCandidateRequiresVM=True,
 currentCandidateVMGatePassed=True,currentCandidateVMGateEvidence='development/ap33/boot-lab/result.json',
 currentCandidateVMGateScope=gate['scope'],currentCandidateImageSHA256=packed['imageSHA256'])
g['lastDevelopmentUpdate']=now;p.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record))
