"""Planner/ownership tests, plus real Linux TC syntax and skip_sw rejection."""
from pathlib import Path
from dataclasses import asdict, replace
import copy, hashlib, importlib.util, json, os, subprocess, sys, uuid

w = Path('/mnt/d/ChatGPT/XR1710G')
out = w / 'development/ap31/publisher'
spec = importlib.util.spec_from_file_location('xr_ppe_rules', out / 'xr_ppe_rules.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
checks = 0

def check(value):
    global checks
    assert value
    checks += 1

def reject(call):
    try:
        call()
    except (m.Ineligible, KeyError, TypeError):
        check(True)
    else:
        raise AssertionError('unexpected acceptance')

boot = '00000000-0000-0000-0000-000000000001'
port = dict(bridge_index=10, up=True, carrier=True, state='forwarding',
            policies={x: False for x in m.UNSUPPORTED}, kind='ethernet',
            ppe_path_qualified=True, tc_ingress_supported=True, pvid=50,
            vlans={'50': {'untagged': True}})
view = dict(schema='xr-ppe-snapshot-v1', boot=boot, generation_before=1, generation_after=1,
            policy_latched=False, tc_policy_handoff_qualified=True, ppe_enabled=True,
            foreign_filters=[], foreign_qdisc_policy=False,
            bridge={'ifindex': 10, 'mst': False, 'vlan_filtering': True, 'protocol': '802.1Q'},
            ports={'pin': dict(port, ifindex=11), 'pout': dict(port, ifindex=12)},
            fdb=[dict(mac='02:00:00:00:00:01', vid=50, port_index=11, local=False, locked=False, expired=False),
                 dict(mac='02:00:00:00:00:02', vid=50, port_index=12, local=False, locked=False, expired=False)])
intent = dict(ingress='pin', egress='pout', source='02:00:00:00:00:01', destination='02:00:00:00:00:02', vid=50, tagged_in=False)
rule = m.plan(view, intent)
check(rule.pref == m.PREF and 'skip_sw' in rule.add_argv())
check(rule.del_argv()[:3] == ['tc', 'filter', 'del'])
for field, bad in [('policy_latched', True), ('tc_policy_handoff_qualified', False),
                   ('ppe_enabled', False), ('foreign_filters', [{}]), ('foreign_qdisc_policy', True),
                   ('generation_after', 2)]:
    v = copy.deepcopy(view); v[field] = bad
    reject(lambda: m.plan(v, intent))
    del v[field]
    reject(lambda: m.plan(v, intent))
for side in ('pin', 'pout'):
    for field, bad in [('up', False), ('carrier', False), ('state', 'blocking'),
                       ('bridge_index', 99), ('ppe_path_qualified', False), ('kind', 'mesh')]:
        v = copy.deepcopy(view); v['ports'][side][field] = bad
        reject(lambda: m.plan(v, intent))
    for flag in m.UNSUPPORTED:
        v = copy.deepcopy(view); v['ports'][side]['policies'][flag] = True
        reject(lambda: m.plan(v, intent))
for i in range(2):
    for field, bad in [('local', True), ('locked', True), ('expired', True), ('port_index', 99)]:
        v = copy.deepcopy(view); v['fdb'][i][field] = bad
        reject(lambda: m.plan(v, intent))
v = copy.deepcopy(view); v['fdb'].append(v['fdb'][0]); reject(lambda: m.plan(v, intent))
v = copy.deepcopy(view); v['ports']['pout']['vlans']['50']['untagged'] = False
push = m.plan(v, intent); check(push.tagged_out)
tagged_intent = dict(intent, tagged_in=True)
pop = m.plan(view, tagged_intent); check(pop.tagged_in and pop.pref != rule.pref)
reject(lambda: m.plan(v, tagged_intent))
for kw in [dict(ingress='pin;reboot'), dict(egress='x\nreboot'), dict(vid=-1), dict(vid=4095),
           dict(source='ff:ff:ff:ff:ff:ff'), dict(destination='00:00:00:00:00:00'),
           dict(generation=-1), dict(generation=True), dict(tagged_in=1), dict(ingress_index=0)]:
    reject(lambda: replace(rule, **kw))

def observation(r):
    return dict(boot=r.boot, ifindex=r.ingress_index, rule=asdict(r), cookies=[r.cookie] * (1 + int(r.tagged_in or r.tagged_out)),
                pref=r.pref, chain=0, handle=r.handle, kind='flower', skip_sw=True, skip_hw=False, in_hw=True)

o = observation(rule)
check(m.owned(rule, o))
ops = m.reconcile([rule], [o], [rule], boot, 1, True)
check(ops['delete'] == ops['add'] == [] and not ops['hardware_binding_proven'])
new = replace(rule, generation=2)
ops = m.reconcile([rule], [o], [new], boot, 2, True)
check(ops['delete'] == [rule.del_argv()] and ops['add'] == [new.add_argv()])
check(m.reconcile([rule], [o], [], boot, 2, False)['delete'] == [rule.del_argv()])
check(m.reconcile([rule], [], [new], boot, 2, True)['delete'] == [])
for key, bad in [('boot', 'other'), ('ifindex', 99), ('cookies', ['00'*16]), ('pref', 1),
                 ('chain', 1), ('handle', '0xffff'), ('kind', 'bpf'), ('skip_sw', False),
                 ('skip_hw', True), ('rule', {})]:
    bad_o = dict(o, **{key: bad})
    check(not m.owned(rule, bad_o))
    reject(lambda: m.reconcile([rule], [bad_o], [], boot, 1, False))
reject(lambda: m.reconcile([rule], [o, o], [], boot, 1, False))
reject(lambda: m.reconcile([], [], [rule, rule], boot, 1, True))
reject(lambda: m.reconcile([], [], [rule], boot, 2, True))
reject(lambda: m.reconcile([], [], [rule], boot, 1, False))
check(m.reconcile([rule], [dict(o, in_hw=False)], [rule], boot, 1, True)['delete'] == [rule.del_argv()])

if '--unit-only' in sys.argv:
    report = {'passed': True, 'checks': checks, 'sourceSHA256': hashlib.sha256((out / 'xr_ppe_rules.py').read_bytes()).hexdigest(),
              'scope': 'pure planner and ownership/reconciliation', 'deviceOrNetworkChanged': False,
              'realKernelOrHardwareQualified': False}
    (out / 'unit-qa.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    raise SystemExit(0)

# A dedicated namespace has no external links, IP addresses, or route changes.
# Its veth ports can exercise the real flower parser and hardware-only failure.
namespace = 'xr-ap31-' + uuid.uuid4().hex[:10]
created = False
live = []

def run(args, ok=True, inside=True):
    command = ['sudo', '-n', *(['ip', 'netns', 'exec', namespace] if inside else []), *args]
    p = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if ok:
        assert p.returncode == 0, (command, p.stderr)
    return p

try:
    run(['ip', 'netns', 'add', namespace], inside=False)
    created = True
    run(['ip', 'link', 'add', 'pin', 'type', 'veth', 'peer', 'name', 'pout'])
    for device in ('pin', 'pout'):
        run(['ip', 'link', 'set', device, 'up'])
    run(['tc', 'qdisc', 'add', 'dev', 'pin', 'clsact'])
    for r in (rule, pop, push):
        # Exact planned argv is parsed by real Linux/iproute2. Veth has no
        # PPE; skip_sw must fail without leaving an active software redirect.
        p = run(r.add_argv(), ok=False)
        check(p.returncode != 0)
        actual = json.loads(run(['tc', '-j', 'filter', 'show', 'dev', 'pin', 'ingress']).stdout)
        check(not any('options' in f for f in actual))
        live.append({'kind': 'hardware-only-unavailable', 'argv': r.add_argv(), 'rc': p.returncode, 'stderr': p.stderr, 'filters': actual})
        # Fixture-only software action exercises the same VLAN/mirred/cookie
        # grammar; it is never accepted by the ownership checker as ours.
        args = ['skip_hw' if x == 'skip_sw' else x for x in r.add_argv()]
        run(args)
        actual = json.loads(run(['tc', '-j', 'filter', 'show', 'dev', 'pin', 'ingress']).stdout)
        check(any('options' in f for f in actual))
        live.append({'kind': 'fixture-software-parser-control', 'argv': args, 'filters': actual})
        run(r.del_argv())
finally:
    if created:
        run(['ip', 'netns', 'del', namespace], inside=False)
remaining = run(['ip', 'netns', 'list'], inside=False).stdout
check(namespace not in remaining)
(out / 'real-tc-fixture.json').write_text(json.dumps(live, indent=2) + '\n')
report = {'passed': True, 'checks': checks, 'sourceSHA256': hashlib.sha256((out / 'xr_ppe_rules.py').read_bytes()).hexdigest(),
          'realKernelTcParserAndSkipSwFailure': True, 'isolatedNamespaceRemoved': True,
          'APOrExistingNetworkChanged': False, 'hardwareBindingOrKernelPolicyLeaseQualified': False,
          'dependencySelection': ['tc-tiny', 'kmod-sched-core', 'kmod-sched-flower', 'kmod-sched-act-vlan']}
(out / 'qa.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
