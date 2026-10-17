"""AP31 experimental host-side rule planner; no subprocesses or device writes.

The executor remains separate until kernel TC-policy handoff is qualified.
`in_hw` means classifier registration, never proof of a bound PPE subflow.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re

PREF = 49171
MAX_RULES = 128
UNSUPPORTED = {'isolated', 'locked', 'mab', 'vlan_tunnel', 'proxy_arp',
               'proxy_arp_wifi', 'neigh_suppress', 'neigh_vlan_suppress', 'mrp'}


class Ineligible(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Ineligible(reason)


def name(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', value), 'interface name')
    return value


def mac(value):
    require(isinstance(value, str) and re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', value), 'MAC format')
    require(not int(value[:2], 16) & 1 and value != '00:00:00:00:00:00', 'unicast MAC required')
    return value


@dataclass(frozen=True)
class Rule:
    boot: str
    generation: int
    ingress: str
    ingress_index: int
    egress: str
    egress_index: int
    bridge_index: int
    source: str
    destination: str
    vid: int
    tagged_in: bool
    tagged_out: bool

    def __post_init__(self):
        require(isinstance(self.boot, str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', self.boot), 'boot ID')
        for value in (self.generation, self.ingress_index, self.egress_index, self.bridge_index, self.vid):
            require(type(value) is int, 'integer context required')
        require(0 <= self.generation < 2**64, 'generation')
        require(all(0 < i < 2**31 for i in (self.ingress_index, self.egress_index, self.bridge_index)), 'ifindex')
        name(self.ingress); name(self.egress); mac(self.source); mac(self.destination)
        require(self.ingress != self.egress and self.ingress_index != self.egress_index, 'hairpin path')
        require(self.source != self.destination, 'identical MACs')
        require(type(self.tagged_in) is bool and type(self.tagged_out) is bool, 'tag state')
        require(0 <= self.vid < 4095 and (self.vid or not (self.tagged_in or self.tagged_out)), 'VLAN')
        require(not (self.tagged_in and self.tagged_out), 'PCP/DEI preservation unavailable')

    @property
    def cookie(self):
        # 16 bytes fits the kernel action-cookie bound. All action cookies
        # include the boot, generation, both ifindices and the full rule.
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:32]

    @property
    def handle(self):
        # Handle zero requests automatic allocation in TC and would break
        # exact ownership/readback. Reserve bit 31 instead.
        return hex(int(self.cookie[:8], 16) | 0x80000000)

    @property
    def pref(self):
        # One TC priority has one classifier protocol. Tagged and untagged
        # rules therefore cannot share a priority on the same ingress.
        return PREF + int(self.tagged_in)

    @property
    def protocol(self):
        return '802.1Q' if self.tagged_in else 'ip'

    def selector(self):
        return ['dev', self.ingress, 'ingress', 'chain', '0', 'protocol', self.protocol,
                'pref', str(self.pref), 'handle', self.handle]

    def add_argv(self):
        args = ['tc', 'filter', 'add', *self.selector(), 'flower', 'indev', self.ingress,
                'src_mac', self.source, 'dst_mac', self.destination, 'skip_sw']
        if self.tagged_in:
            args += ['vlan_id', str(self.vid), 'vlan_ethtype', 'ipv4', 'action', 'vlan', 'pop', 'cookie', self.cookie]
        elif self.tagged_out:
            args += ['action', 'vlan', 'push', 'id', str(self.vid), 'protocol', '802.1Q', 'priority', '0', 'cookie', self.cookie]
        args += ['action', 'mirred', 'egress', 'redirect', 'dev', self.egress, 'cookie', self.cookie]
        return args

    def del_argv(self):
        # Delete one verified owned filter, never a qdisc or an entire chain.
        return ['tc', 'filter', 'del', *self.selector(), 'flower']


def plan(view, intent):
    """A coherent, normalized readback is required; missing facts reject."""
    require(view.get('schema') == 'xr-ppe-snapshot-v1', 'snapshot schema')
    require(view.get('generation_before') == view.get('generation_after') and
            type(view.get('generation_before')) is int, 'context changed during collection')
    require(view.get('policy_latched') is False, 'bridge policy requires software')
    require(view.get('tc_policy_handoff_qualified') is True, 'TC policy handoff not qualified')
    require(view.get('ppe_enabled') is True, 'PPE disabled')
    require(view.get('foreign_filters') == [] and view.get('foreign_qdisc_policy') is False, 'foreign TC policy')
    bridge = view['bridge']
    require(bridge.get('mst') is False, 'MST state unsupported')
    require(bridge.get('protocol') == '802.1Q', 'bridge VLAN protocol')
    ports = view['ports']
    ingress, egress = ports[intent['ingress']], ports[intent['egress']]
    for p in (ingress, egress):
        require(p.get('bridge_index') == bridge['ifindex'], 'different bridge')
        require(p.get('up') is True and p.get('carrier') is True and p.get('state') == 'forwarding', 'port not forwarding')
        require(p.get('policies') == {x: False for x in UNSUPPORTED}, 'unsupported or unknown port policy')
        require(p.get('kind') in ('ethernet', 'wlan_ap', 'wlan_sta') and p.get('ppe_path_qualified') is True, 'unqualified path, including Mesh')
    require(ingress.get('tc_ingress_supported') is True, 'no ingress callback')
    vid = intent['vid']
    tagged = intent['tagged_in']
    if bridge.get('vlan_filtering') is True:
        require(type(vid) is int and 1 <= vid < 4095, 'VLAN')
        require(str(vid) in ingress['vlans'] and str(vid) in egress['vlans'], 'VLAN membership')
        if not tagged:
            require(ingress.get('pvid') == vid, 'PVID differs')
        untag = egress['vlans'][str(vid)].get('untagged')
        require(type(untag) is bool, 'unknown egress tag policy')
        tagged_out = not untag
    else:
        require(bridge.get('vlan_filtering') is False and vid == 0 and tagged is False, 'unfiltered VLAN context')
        tagged_out = False
    for address, port in [(intent['source'], ingress), (intent['destination'], egress)]:
        matches = [f for f in view['fdb'] if f.get('mac') == address and f.get('vid') == vid]
        require(len(matches) == 1, 'missing or ambiguous FDB')
        f = matches[0]
        require(f.get('port_index') == port['ifindex'] and f.get('local') is False and
                f.get('locked') is False and f.get('expired') is False, 'FDB does not authorize forwarding')
    return Rule(view['boot'], view['generation_before'], intent['ingress'], ingress['ifindex'],
                intent['egress'], egress['ifindex'], bridge['ifindex'], intent['source'],
                intent['destination'], vid, tagged, tagged_out)


def owned(rule, observed):
    """Normalized readback must retain the full selectors/actions and cookie.

    The reader must reject unknown match/action keys before constructing this
    normalized representation. A cookie alone or an in_hw flag is insufficient.
    """
    return (observed.get('boot') == rule.boot and
            observed.get('ifindex') == rule.ingress_index and
            observed.get('rule') == asdict(rule) and
            observed.get('cookies') == [rule.cookie] * (1 + int(rule.tagged_in or rule.tagged_out)) and
            observed.get('pref') == rule.pref and observed.get('chain') == 0 and
            observed.get('handle') == rule.handle and observed.get('kind') == 'flower' and
            observed.get('skip_sw') is True and observed.get('skip_hw') is False)


def readback(rule, raw, boot, ifindex):
    """Validate one actual iproute2 expanded flower row, without broadening it."""
    require(set(raw) == {'protocol', 'pref', 'kind', 'chain', 'options'}, 'unknown TC row fields')
    require((raw['protocol'], raw['pref'], raw['kind'], raw['chain']) ==
            (rule.protocol, rule.pref, 'flower', 0), 'TC selector changed')
    options = raw['options']
    permitted = {'handle', 'indev', 'keys', 'skip_sw', 'skip_hw', 'in_hw', 'not_in_hw', 'in_hw_count', 'actions'}
    require(set(options) <= permitted, 'unknown TC options')
    require(options.get('handle') == int(rule.handle, 16) and options.get('indev') == rule.ingress, 'TC handle/ingress changed')
    require(options.get('skip_sw') is True and options.get('skip_hw', False) is False, 'software filter is not owned')
    require(not (options.get('in_hw') and options.get('not_in_hw')), 'inconsistent hardware status')
    keys = {'src_mac': rule.source, 'dst_mac': rule.destination, 'eth_type': 'ipv4'}
    if rule.tagged_in:
        keys.update(vlan_id=rule.vid, vlan_ethtype='ip')
    require(options.get('keys') == keys, 'TC match differs')
    expected_actions = []
    if rule.tagged_in:
        expected_actions.append({'kind': 'vlan', 'vlan_action': 'pop', 'control_action': {'type': 'pipe'}})
    elif rule.tagged_out:
        expected_actions.append({'kind': 'vlan', 'vlan_action': 'push', 'id': rule.vid, 'protocol': '802.1Q',
                                 'priority': 0, 'control_action': {'type': 'pipe'}})
    expected_actions.append({'kind': 'mirred', 'mirred_action': 'redirect', 'direction': 'egress',
                             'to_dev': rule.egress, 'control_action': {'type': 'stolen'}})
    actual = options.get('actions', [])
    require(len(actual) == len(expected_actions), 'TC action count differs')
    # These are reported counters/indices, not permission-changing actions.
    metadata = {'index', 'ref', 'bind', 'stats', 'used_hw_stats', 'hw_stats'}
    for i, (a, expected) in enumerate(zip(actual, expected_actions), 1):
        semantics = {k: v for k, v in a.items() if k not in metadata}
        require(semantics == dict(expected, order=i, cookie=rule.cookie), 'TC action or ownership differs')
    normalized = {'boot': boot, 'ifindex': ifindex, 'rule': asdict(rule),
                  'cookies': [a['cookie'] for a in actual], 'pref': rule.pref, 'chain': 0,
                  'handle': rule.handle, 'kind': 'flower', 'skip_sw': True, 'skip_hw': False,
                  'in_hw': options.get('in_hw', False) is True}
    require(owned(rule, normalized), 'device identity changed')
    return normalized


def reconcile(previous, observed, desired, boot, generation, allow_add):
    """Return deletes then adds, or reject ownership ambiguity without writes.

    This is planning only. Execution needs an exclusive kernel policy lease;
    a userspace precheck cannot prevent another writer changing a TC chain.
    """
    require(len(previous) <= MAX_RULES and len(desired) <= MAX_RULES, 'rule budget')
    require(type(allow_add) is bool, 'allow_add must be boolean')
    require(allow_add or not desired, 'publication closed')
    selectors = [(r.ingress_index, r.protocol, r.handle) for r in desired]
    require(len(selectors) == len(set(selectors)), 'handle collision')
    require(len({r.cookie for r in previous}) == len(previous), 'duplicate ledger record')
    require(all(r.boot == boot and r.generation == generation for r in desired), 'stale desired context')
    removals = []
    additions = list(desired)
    expected = {r.cookie: r for r in previous}
    seen = set()
    for o in observed:
        cookies = o.get('cookies', [])
        require(cookies and cookies[0] in expected, 'foreign filter observed')
        r = expected[cookies[0]]
        require(r.boot == boot and owned(r, o), 'ownership changed; no deletion')
        require(r.cookie not in seen, 'duplicate observed filter')
        seen.add(r.cookie)
        if r in desired and o.get('in_hw') is True and r.generation == generation:
            additions.remove(r)
        else:
            removals.append(r.del_argv())
    # Missing old filters need no delete. A surviving but revoked tc entry is
    # explicitly deleted/readded even if tc still reports in_hw from install.
    return {'delete': removals, 'add': [r.add_argv() for r in additions],
            'hardware_binding_proven': False, 'requires_kernel_policy_lease': bool(additions)}
