"""Malformed-record and diagnostic-meaning checks; no network or AP access."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
from xr_npu_producer_trace import parse_snapshot, HEADER

w = Path(__file__).resolve().parent.parent
out = w/'development/npu-producer-reader'
boot = '11111111-1111-1111-1111-111111111111'
prefix = f'schema=1 bootID={boot} monotonicMs=35000\n'
cases = []
def wrap(payload):
    return (prefix+payload+f'snapshot_status=complete bytes={len(payload.encode())}\n').encode()
def build(count=32):
    lines = [HEADER+'\n']
    for h in range(8):
        lines.append(f'hart={h} count={count}\n')
        for r in range(count):
            words = [r, 0xc0140000, 0xc0140000, 0x300a005c, 5, 0x8a000080,
                     0x8a000080, 0x30010014, 0x420ce000, 0, 0, r+1]
            lines.append(f'hart={h} record={r}'+''.join(f' w{i}={word:08x}' for i,word in enumerate(words))+'\n')
    return ''.join(lines)
payload = build()
valid = wrap(payload)
result = parse_snapshot(valid, boot)
assert len(result['rows']) == 256 and len(valid) > 16384
assert all(row['twoViewsDiffer'] and row['sourceShorterThanAnnounced'] and row['sourceLast'] for row in result['rows'])
assert not result['rootCauseProven']
cases.append('full-256-rows-shorter-input-different-views-not-root-proof')
assert not parse_snapshot(wrap(build(0)), boot)['rows']
cases.append('zero-records-valid-but-not-anomaly-evidence')
negative = {
    'missing-footer': valid[:valid.rfind(b'snapshot_status=')],
    'failed-footer': valid.replace(b'snapshot_status=complete', b'snapshot_status=failed'),
    'capped-footer': valid.replace(b'snapshot_status=complete', b'snapshot_status=capped'),
    'wrong-boot': valid.replace(boot.encode(), b'22222222-2222-2222-2222-222222222222'),
    'bad-byte-count': valid.replace(b'bytes=', b'bytes=1'),
    'nul': valid.replace(b'source=', b'source=\x00'),
    'extra-footer': valid+b'snapshot_status=complete bytes=0\n',
    'newline-missing': valid[:-1],
    'missing-hart': wrap(payload[:payload.index('hart=7 count=')]),
    'oversized': b'x'*66049,
}
for name, a, b in [
    ('wrong-schema', 'schema=2', 'schema=3'),
    ('oversized-count', 'hart=0 count=32', 'hart=0 count=33'),
    ('duplicate-hart', 'hart=1 count=32', 'hart=0 count=32'),
    ('wrong-record', 'hart=0 record=0', 'hart=0 record=1'),
    ('uncommitted', 'w11=00000001', 'w11=00000000'),
    ('reserved-nonzero', 'w10=00000000', 'w10=00000001'),
    ('wrong-type', 'w3=300a005c', 'w3=200a005c'),
    ('bad-version', 'w4=00000005', 'w4=00000008'),
    ('extra-word', ' w11=00000001', ' w11=00000001 w12=00000000'),
]:
    negative[name] = wrap(payload.replace(a, b, 1))
for name, data in negative.items():
    try:
        parse_snapshot(data, boot)
    except ValueError:
        cases.append(name)
    else:
        raise AssertionError(name+' was accepted')
short = payload.replace('w1=c0140000', 'w1=c0040000').replace('w4=00000005', 'w4=ffffffff')
assert len(parse_snapshot(wrap(short), boot)['rows']) == 256
cases.append('short-descriptor-version-read-skipped')
for name in ['w5=8a000080', 'w2=c0140000']:
    changed = payload.replace(name, name[:-1]+'1', 1)
    first = parse_snapshot(wrap(changed), boot)['rows'][0]
    assert first['controlChangedDuringObservation'] if name.startswith('w2') else not first['poolPointerMatchesDescriptor']
    cases.append('retain-diagnostic-difference-'+name[:2])
report = {'at': datetime.now().astimezone().isoformat(), 'passed': True, 'cases': cases,
          'sourceSHA256': hashlib.sha256((w/'environment/xr_npu_producer_trace.py').read_bytes()).hexdigest(),
          'testSHA256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'syntheticFixturesOnly': True, 'historicalRootProven': False}
(out/'parser-qa.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
