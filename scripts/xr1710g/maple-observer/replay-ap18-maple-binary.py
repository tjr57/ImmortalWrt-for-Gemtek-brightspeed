"""Execute frozen AP18 AArch64 instructions against explicitly synthetic trees.

This locates instruction paths consistent with saved registers. Injected corruption
is a hypothesis test, NOT evidence of a physical writer or a hardware qualification.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm64_const import *

W = Path(__file__).resolve().parents[1]
O = W / 'development/ap24/maple-binary'
B = 0xffffffc080000000
F = B + 0x8ac3e0
FAULT = F + 0xd4
LR = B + 0x1e8e30
SP = 0xffffffc086253b70
MAS = 0xffffffc086253bc8
ROOT = 0xffffff8001b00000
CHILD = 0xffffff8001a2a400
TREE = 0xffffff8001c00040
MASK = (1 << 64) - 1
BIT = 1 << 63
image = (O / 'AP18-r2-Image').read_bytes()
extract = json.loads((O / 'extraction.json').read_text())
assert hashlib.sha256(image).hexdigest() == extract['imageSHA256']
assert image[0x8ac3e0:0x8aca20] == (O / 'mas-empty-area-rev.bin').read_bytes()
cs = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
instructions = {i.address: i for i in cs.disasm(image[0x8ac3e0:0x8aca20], F)}
old_log = (W / 'development/ap18/npu-hardware/baseline-mode0-v4/kernel-before.txt').read_text()
observed = {int(k): int(v, 16) for k, v in re.findall(r'x(\d+)\s*:\s*([0-9a-f]{16})', old_log)}
assert len(observed) == 30
observed_sp = int(re.search(r'sp : ([0-9a-f]{16})', old_log)[1], 16)
observed_nzcv = int(re.search(r'pstate: ([0-9a-f]{8})', old_log)[1], 16) & 0xf0000000
regs = [globals()['UC_ARM64_REG_X' + str(i)] for i in range(31)]


def replay(kind='none', injection_pc=None, stop_at_fault_pc=False):
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    u.mem_map(B, (len(image) + 4095) & ~4095)
    u.mem_write(B, image)
    for address in (SP, ROOT, CHILD, TREE):
        u.mem_map(address & ~4095, 4096)
    def q(a, value):
        u.mem_write(a, struct.pack('<Q', value & MASK))
    def b(a, value):
        u.mem_write(a, bytes([value]))
    # A fresh VMA iterator, matching the old caller's zeroing and ma_start=1.
    q(MAS, TREE)
    u.mem_write(MAS + 72, struct.pack('<I', 1))
    # Synthetic root (arange64, two slots) and child (leaf64, end=8).
    q(TREE + 8, ROOT | 0x1e)
    q(ROOT, TREE | 1)
    q(ROOT + 8, 0x7f990bcfff)
    q(ROOT + 16, MASK)
    q(ROOT + 0x50 + 8, CHILD | 0x0c)
    q(ROOT + 0xa0 + 8, 0x7f990d9000 - 0x7f990bd000)
    b(ROOT + 0xf0, 1)
    q(CHILD, ROOT | 0x08)
    # Monotone populated leaf entries; final unused pivot zero and metadata end 8.
    for j in range(8):
        q(CHILD + 8 + j * 8, 0x7f990bdfff + j * 0x2000)
        q(CHILD + 0x80 + j * 8, 0xffffff8002c00000 + j * 0x100)
    q(CHILD + 8 + 8 * 8, MASK)
    b(CHILD + 0xf8, 8)
    for i in (17, 25, 26, 27, 28):
        u.reg_write(regs[i], observed[i])
    u.reg_write(UC_ARM64_REG_SP, SP)
    u.reg_write(UC_ARM64_REG_LR, LR)
    for i, value in enumerate((MAS, 0x1000, 0x7f990d8fff, 0x1000)):
        u.reg_write(regs[i], value)
    trace, events, faults = [], [], []
    done = False
    def hook_code(uc, pc, size, _):
        nonlocal done
        if pc == LR:
            uc.emu_stop()
            return
        trace.append(pc)
        if len(trace) > 2000 or pc not in instructions:
            raise AssertionError('Unexpected external path or unbounded loop: ' + hex(pc))
        if pc == injection_pc and not done:
            done = True
            if kind in ('stack-node', 'root-pointer', 'child-slot'):
                at = {'stack-node': MAS + 24, 'root-pointer': TREE + 8,
                      'child-slot': ROOT + 0x50 + 8}[kind]
                before = struct.unpack('<Q', uc.mem_read(at, 8))[0]
                q(at, before & ~BIT)
                events.append({'at': hex(at), 'before': hex(before), 'after': hex(before & ~BIT)})
            elif kind.startswith('x'):
                ri = int(kind[1:])
                before = uc.reg_read(regs[ri])
                uc.reg_write(regs[ri], before & ~BIT)
                events.append({'register': kind, 'before': hex(before), 'after': hex(before & ~BIT)})
            else:
                raise AssertionError(kind)
        if stop_at_fault_pc and pc == FAULT and len(trace) > 100:
            uc.emu_stop()
    def invalid(uc, access, address, size, value, _):
        faults.append({'address': hex(address), 'size': size,
                       'pc': hex(uc.reg_read(UC_ARM64_REG_PC))})
        return False
    u.hook_add(UC_HOOK_CODE, hook_code)
    u.hook_add(UC_HOOK_MEM_INVALID, invalid)
    error = None
    try:
        u.emu_start(F, LR, count=3000)
    except UcError as exc:
        error = str(exc)
    actual = {i: u.reg_read(regs[i]) for i in observed}
    delta = {f'x{i}': {'expected': hex(value), 'actual': hex(actual[i])}
             for i, value in observed.items() if actual[i] != value}
    controls = {'sp': u.reg_read(UC_ARM64_REG_SP), 'lr': u.reg_read(UC_ARM64_REG_LR),
                'nzcv': u.reg_read(UC_ARM64_REG_NZCV) & 0xf0000000}
    control_match = controls == {'sp': observed_sp, 'lr': LR, 'nzcv': observed_nzcv}
    return {'kind': kind, 'injectionBeforePC': hex(injection_pc) if injection_pc else None,
            'injected': done, 'events': events, 'faults': faults,
            'instructionCount': len(trace), 'trace': [hex(x) for x in trace],
            'registerDifferences': delta, 'error': error,
            'controlRegisters': {k: hex(v) for k, v in controls.items()},
            'returnValue': hex(actual[0]),
            'exactSavedRegisterMatch': not delta and control_match and bool(faults) and
              faults[0] == {'address': '0x7fffff8001a2a440', 'size': 8, 'pc': hex(FAULT)}}


def main():
    cases = [replay()]
    assert not cases[0]['faults'] and cases[0]['returnValue'] == '0x0'
    cases += [replay('root-pointer', F), replay('child-slot', F)]
    # Enumerate every instruction boundary from publishing to final fault;
    # separate memory corruption from transient CPU-register corruption.
    candidates = [a for a in instructions if B + 0x8ac5dc <= a <= B + 0x8ac650]
    for kind in ('stack-node', 'x9', 'x10', 'x2'):
        for pc in candidates:
            cases.append(replay(kind, pc))
    (O / 'replay-cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    matches = [{'kind': r['kind'], 'injectionBeforePC': r['injectionBeforePC']}
               for r in cases if r['exactSavedRegisterMatch']]
    assert matches, 'The candidate path must reproduce every saved register, not just the PC'
    assert len(matches) == 25
    assert not cases[1]['exactSavedRegisterMatch'] and not cases[2]['exactSavedRegisterMatch']
    caller = image[0x1e8d80:0x1e8ec0]
    (O / 'old-unmapped-area-topdown.asm').write_text('\n'.join(
        f'{i.address:016x}: {i.mnemonic} {i.op_str}' for i in cs.disasm(caller, B + 0x1e8d80)) + '\n')
    result = {'frozenImageSHA256': extract['imageSHA256'], 'cases': len(cases),
              'matches': matches, 'baseline': {k: v for k, v in cases[0].items() if k != 'trace'},
              'physicalCorruptionWriterProven': False, 'rootCauseProven': False,
              'treeMemory': 'synthetic fixtures, not a historical memory dump',
              'initialRegistersTakenFromLog': ['x17', 'x25', 'x26', 'x27', 'x28'],
              'comparison': 'x0-x29, SP, LR, NZCV, fault PC, read address and size',
              'assumptions': ['Synthetic valid two-level tree; one injected bit-63 clear.',
                              'No interrupts, DMA, cache, physical RAM errors or alternative corrupted tree modeled.',
                              'Matching hypotheses are not an exhaustive proof of the historical execution path.'],
              'deviceChanged': False}
    (O / 'replay-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
