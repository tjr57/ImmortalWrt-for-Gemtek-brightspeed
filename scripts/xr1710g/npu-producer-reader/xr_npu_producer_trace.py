"""Strict offline parser for complete, bounded recovery5 producer snapshots.

This accepts only scalar metadata. A parse result is not root-cause or hardware
acceptance evidence; the caller must bind firmware, collector and epoch gates.
"""
import re

UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
HEADER = 'schema=2 atomic=0 source=producer-scalar record_words=12'

def _parse_payload(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 65536:
        raise ValueError('payload size or type')
    try:
        text = data.decode('ascii')
    except UnicodeDecodeError as e:
        raise ValueError('non-ASCII payload') from e
    lines = text.splitlines(keepends=True)
    if len(lines) < 9 or any(not line.endswith('\n') or '\r' in line or '\x00' in line for line in lines):
        raise ValueError('incomplete or invalid payload line')
    if lines[0] != HEADER+'\n':
        raise ValueError('producer schema')
    cursor, records, counts = 1, [], []
    for hart in range(8):
        if cursor >= len(lines):
            raise ValueError('missing hart')
        count = re.fullmatch(r'hart='+str(hart)+r' count=([0-9]{1,2})\n', lines[cursor])
        if not count or int(count[1]) > 32:
            raise ValueError('hart order or count')
        count = int(count[1])
        counts.append(count)
        cursor += 1
        for row in range(count):
            if cursor >= len(lines):
                raise ValueError('missing row')
            pattern = 'hart='+str(hart)+' record='+str(row)+''.join(r' w'+str(w)+r'=([0-9a-f]{8})' for w in range(12))+'\n'
            match = re.fullmatch(pattern, lines[cursor])
            if not match:
                raise ValueError('row order or shape')
            words = [int(word, 16) for word in match.groups()]
            if words[10] or words[11] != row+1 or words[3] >> 27 != 6:
                raise ValueError('reserved word, commit or type')
            length = (words[1] >> 16) & 0x3fff
            if (length < 8 and words[4] != 0xffffffff) or (length >= 8 and words[4] > 7):
                raise ValueError('version length bound')
            records.append({
                'hart': hart, 'record': row, 'ringIndex': words[0],
                'descriptorBytes': length, 'announcedBytes': words[3] & 0xffff,
                'encodedCount': (words[3] >> 16) & 0xff,
                'sourceLast': bool(words[1] & (1 << 30)),
                'controlChangedDuringObservation': words[1] != words[2],
                'poolPointerMatchesDescriptor': words[5] == words[6],
                'twoViewsDiffer': words[3] != words[7],
                'view8Header': f'{words[3]:08x}', 'view4Header': f'{words[7]:08x}',
                'sourceShorterThanAnnounced': length < (words[3] & 0xffff),
            })
            cursor += 1
    if cursor != len(lines):
        raise ValueError('trailing or duplicate records')
    return records, counts


def parse_live_snapshot(data, observation):
    """Parse raw debugfs bytes bound to successful before/after SSH observations.

    This does not claim to be a recovery5 envelope. The caller verifies the
    actual artifact/module hashes and continuous collector for the same boot.
    """
    boot = observation.get('bootBefore')
    if not isinstance(boot, str) or not re.fullmatch(UUID, boot) or observation.get('bootAfter') != boot:
        raise ValueError('live epoch mismatch')
    before, after = observation.get('monotonicMsBefore'), observation.get('monotonicMsAfter')
    if type(before) is not int or type(after) is not int or not 0 <= before <= after or after-before > 6000:
        raise ValueError('live read time bound')
    if type(observation.get('readCode')) is not int or observation['readCode'] != 0 or observation.get('npuEnable') != 'Y':
        raise ValueError('live read/activation not confirmed')
    records, counts = _parse_payload(data)
    return {'schema': 1, 'source': 'direct-debugfs-SSH', 'bootID': boot,
            'monotonicMsBefore': before, 'monotonicMsAfter': after,
            'rows': records, 'countsPerHart': counts, 'complete': True,
            'nonAtomic': True, 'rootCauseProven': False,
            'limits': ['Caller must verify actual firmware/module and collector epoch',
                       'First32/hart only; successful stream read is not an atomic hardware snapshot']}


def parse_snapshot(data, expected_boot):
    if not isinstance(data, bytes) or not 0 < len(data) <= 65536+512:
        raise ValueError('snapshot size or type')
    if not re.fullmatch(UUID, expected_boot):
        raise ValueError('expected boot identity')
    try:
        text = data.decode('ascii')
    except UnicodeDecodeError as e:
        raise ValueError('non-ASCII snapshot') from e
    lines = text.splitlines(keepends=True)
    if any(not line.endswith('\n') or '\r' in line or '\x00' in line for line in lines):
        raise ValueError('incomplete or invalid line')
    if len(lines) < 11:
        raise ValueError('incomplete snapshot')
    head = re.fullmatch(r'schema=1 bootID=('+UUID+r') monotonicMs=([0-9]{1,20})\n', lines[0])
    if not head or head[1] != expected_boot:
        raise ValueError('epoch mismatch')
    tail = re.fullmatch(r'snapshot_status=complete bytes=([0-9]{1,5})\n', lines[-1])
    payload = ''.join(lines[1:-1]).encode('ascii')
    if not tail or int(tail[1]) != len(payload) or len(payload) > 65536:
        raise ValueError('incomplete, capped, failed or wrong byte count')
    records, counts = _parse_payload(payload)
    return {'schema': 1, 'bootID': head[1], 'monotonicMs': int(head[2]),
            'rows': records, 'countsPerHart': counts, 'complete': True,
            'nonAtomic': True, 'rootCauseProven': False,
            'limits': ['Observed view disagreement does not prove cache semantics',
                       'Caller must verify candidate hash and collector/recovery epoch',
                       'First 32 records per hart may not include a later anomaly']}
