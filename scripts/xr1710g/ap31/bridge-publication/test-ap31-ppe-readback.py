"""Strict ownership parsing using real VM TC JSON, plus labeled flag models."""
from pathlib import Path
from dataclasses import replace
import copy, hashlib, importlib.util, json, sys

out = Path('/mnt/d/ChatGPT/XR1710G/development/ap31/publisher')
spec = importlib.util.spec_from_file_location('xr_ppe_rules', out / 'xr_ppe_rules.py')
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
evidence = json.loads((out / 'vm-result.json').read_text())
assert evidence['passed'] and evidence['sourceSHA256'] == hashlib.sha256((out / 'xr_ppe_rules.py').read_bytes()).hexdigest()
rule = m.Rule('00000000-0000-0000-0000-000000000001', 1, 'pin', 11, 'pout', 12, 10,
              '02:00:00:00:00:01', '02:00:00:00:00:02', 50, False, False)
rules = [rule, replace(rule, tagged_in=True), replace(rule, tagged_out=True)]
checks = 0

def check(value):
    global checks
    assert value
    checks += 1

def reject(call):
    try:
        call()
    except m.Ineligible:
        check(True)
    else:
        raise AssertionError('unexpected ownership acceptance')

for rule, rows in zip(rules, evidence['tcReadbacks']):
    raw = next(r for r in rows if 'options' in r)
    # Real software-control output must never be adopted as a hardware-only
    # owned rule, even though it uses the exact same action cookie.
    reject(lambda: m.readback(rule, raw, rule.boot, rule.ingress_index))
    modeled = copy.deepcopy(raw)
    modeled['options'].pop('skip_hw')
    modeled['options'].pop('not_in_hw')
    modeled['options'].update(skip_sw=True, in_hw=True)
    parsed = m.readback(rule, modeled, rule.boot, rule.ingress_index)
    check(m.owned(rule, parsed))
    check(not m.reconcile([rule], [parsed], [rule], rule.boot, 1, True)['add'])
    reject(lambda: m.readback(rule, modeled, rule.boot, 999))
    reject(lambda: m.readback(rule, modeled, 'another-boot', rule.ingress_index))
    mutations = [lambda x: x.update(unrecognized_policy=True),
                 lambda x: x.update(chain=1), lambda x: x.update(pref=1),
                 lambda x: x['options'].update(classid='1:1'),
                 lambda x: x['options']['keys'].update(ip_proto='tcp'),
                 lambda x: x['options']['keys'].update(src_mac='02:00:00:00:00:ff'),
                 lambda x: x['options']['actions'][-1].update(to_dev='foreign'),
                 lambda x: x['options']['actions'][-1].update(cookie='00'*16),
                 lambda x: x['options']['actions'][-1].update(control_action={'type': 'continue'}),
                 lambda x: x['options']['actions'].append(copy.deepcopy(x['options']['actions'][-1])),
                 lambda x: x['options']['actions'][0].update(goto_chain=7),
                 lambda x: x['options'].update(skip_hw=True),
                 lambda x: x['options'].update(not_in_hw=True)]
    for mutate in mutations:
        bad = copy.deepcopy(modeled); mutate(bad)
        reject(lambda: m.readback(rule, bad, rule.boot, rule.ingress_index))
    counters = copy.deepcopy(modeled)
    counters['options']['actions'][-1]['stats'] = {'bytes': 100, 'packets': 2}
    check(m.owned(rule, m.readback(rule, counters, rule.boot, rule.ingress_index)))
report = {'passed': True, 'checks': checks, 'sourceSHA256': evidence['sourceSHA256'],
          'actualTCReadbackEvidence': 'development/ap31/publisher/vm-result.json',
          'actualSoftwareRulesRejected': True, 'positiveHardwareFlagsModeledOnly': True,
          'actualPPEBindingOrPolicyLeaseQualified': False}
(out / 'readback-qa.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
