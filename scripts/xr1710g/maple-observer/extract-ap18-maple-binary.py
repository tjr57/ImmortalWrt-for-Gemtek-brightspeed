"""Read-only extraction from the frozen AP18-r2 FIT, never the mutable vmlinux."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

W = Path('/mnt/d/ChatGPT/XR1710G')
R = Path('/home/xrdev/projects/xr1710g/openwrt')
O = W / 'development/ap24/maple-binary'
sys.path.insert(0, str(R / 'scripts'))
from verify_ap4_artifacts import FDT

def sha(data):
    return hashlib.sha256(data).hexdigest()

fit_path = next((W / 'builds/20261010-ap18-d331711d-r2-development').glob('*sysupgrade.itb'))
fit_data = fit_path.read_bytes()
assert sha(fit_data) == 'ff1e3c848cc7e63fcd4699283476c96e640c9744345921adf6a6ee83c9bee77f'
fit = FDT(fit_data)
image = fit.payload('/images/kernel-1')
assert image[0x38:0x3c] == b'ARM\x64'
old = W / 'development/ap18/npu-hardware/baseline-mode0-v4/oops-analysis'
asm_data = (old / 'mas-empty-area-rev.asm').read_bytes()
rows = [(int(a, 16), int(b, 16)) for a, b in re.findall(
    r'^([0-9a-f]{16}):\s+([0-9a-f]{8})\s', asm_data.decode(), re.M)]
assert len(rows) == 0x640 // 4
assert all(a == rows[0][0] + i * 4 for i, (a, _) in enumerate(rows))
code = b''.join(struct.pack('<I', op) for _, op in rows)
offset = image.find(code)
assert offset >= 0 and image.find(code, offset + 1) == -1
base = rows[0][0] - offset
assert rows[0][0] == 0xffffffc0808ac3e0
assert struct.unpack_from('<I', code, 0xd4)[0] == 0xf8607864
callers = []
for pos in range(0, len(image) - 3, 4):
    op = struct.unpack_from('<I', image, pos)[0]
    if op & 0xfc000000 == 0x94000000:
        imm = op & 0x3ffffff
        if imm & (1 << 25):
            imm -= 1 << 26
        if base + pos + imm * 4 == rows[0][0]:
            callers.append(base + pos)
O.mkdir(exist_ok=True)
(O / 'AP18-r2-Image').write_bytes(image)
(O / 'mas-empty-area-rev.bin').write_bytes(code)
result = {
    'frozenFIT': str(fit_path.relative_to(W)), 'fitSHA256': sha(fit_data),
    'imageSHA256': sha(image), 'imageBytes': len(image),
    'oldAssemblySHA256': sha(asm_data), 'functionSHA256': sha(code),
    'functionBytes': len(code), 'functionVA': hex(rows[0][0]),
    'imageOffset': hex(offset), 'inferredImageVA': hex(base),
    'all400InstructionsMatchFrozenImage': True,
    'faultOpcodeMatches': True, 'directBLCallsites': [hex(a) for a in callers],
    'mutableVmlinuxUsed': False, 'deviceChanged': False,
    'limitations': ['BL scan covers all Image words; candidate callsites require instruction/context review.'],
}
(O / 'extraction.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
