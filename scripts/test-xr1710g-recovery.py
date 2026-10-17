#!/usr/bin/env python3
"""Exercise the actual recovery shell code against filesystem-only mocks."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'feeds/app_airoha/luci-app-airoha-recovery/root/usr/libexec/rpcd/luci.airoha_recovery'
OUT = Path(os.environ.get('XR1710G_ARTIFACTS', str(Path.home() / 'artifacts/xr1710g')))
OUT.mkdir(parents=True, exist_ok=True)
MOCK = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p=Path(os.environ['MOCK_STATE'])
s=json.loads(p.read_text())
args=sys.argv[1:]
if sys.argv[0].endswith('fw_setenv'):
    s['writes'].append(args[-2:])
    if s.get('writeRc',0):
        p.write_text(json.dumps(s)); sys.exit(s['writeRc'])
    s['values'][args[-2]]=args[-1]
    if not s.get('keepInvalid'): s['mode']='valid'
    p.write_text(json.dumps(s)); sys.exit(0)
if '-n' in args:
    v=args[-1]
    if v not in s['values']: sys.exit(1)
    print(s['values'][v]); sys.exit(s.get('readbackRc',0))
if s['mode']=='invalid': print(s.get('diagnostic','Warning: Bad CRC, using default environment'),file=sys.stderr)
elif s['mode']=='io': print('Cannot read environment',file=sys.stderr)
elif s['mode']=='warning': print('Unexpected read diagnostic',file=sys.stderr)
sys.exit(s.get('probeRc',2 if s['mode']=='io' else 0))
'''


def main():
    source = SOURCE.read_text()
    # Do not source /lib/functions.sh or allow real reboot, UBI, envtools access.
    body = source.rsplit('\ncase "$1" in\n', 1)[0]
    defaults = source.split("cat <<-'EOF'\n", 1)[1].split('\n\tEOF', 1)[0]
    values = dict(line.strip().split(' ', 1) for line in defaults.splitlines() if line.strip())
    cases = []
    with tempfile.TemporaryDirectory(prefix='xr-recovery-qa-') as folder:
        directory = Path(folder)
        state = directory / 'state.json'
        for tool in ('fw_printenv', 'fw_setenv'):
            path = directory / tool
            path.write_text(MOCK)
            path.chmod(0o755)
            body = body.replace(f'/usr/sbin/{tool}', str(path))
        body = body.replace('. /lib/functions.sh', ':')
        body = body.replace('ENV_LOG="/tmp/airoha-recovery.log"', f'ENV_LOG="{directory}/env.log"')
        body = body.replace('\tsync\n', '\t:\n')
        body = body.replace('( sleep 1; /sbin/reboot ) >/dev/null 2>&1 </dev/null &',
                            f'printf armed > "{directory}/reboot-marker"')
        body += '\nboard_name() { printf "gemtek,xr1710g\\n"; }\n'
        body += f'ensure_env_conf() {{ ENV_CONF="{directory}/fw_env.config"; return 0; }}\n'
        script = directory / 'test.sh'
        environment = dict(os.environ, MOCK_STATE=str(state))

        def run(name, configuration, command, check):
            config = dict(mode='valid', values=values.copy(), writes=[])
            config.update(configuration)
            state.write_text(json.dumps(config))
            script.write_text(body + '\n' + command + '\n')
            result = subprocess.run(['sh', str(script)], env=environment,
                                    text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (name, result.stderr)
            actual = json.loads(state.read_text())
            check(result.stdout.strip(), actual)
            cases.append({'name': name, 'passed': True})

        def equals(expected):
            def check(output, state):
                assert output == expected, (output, expected)
            return check

        probe = 'env_crc_ok; rc=$?; printf "%s %s %s\\n" "$rc" "$ENV_STATE" "$ENV_REASON"'
        run('valid stored CRC', {}, probe, equals('0 ok'))
        run('Bad CRC with exit zero', {'mode': 'invalid'}, probe,
            equals('1 invalid-crc uboot-env-invalid-crc'))
        run('lowercase CRC warning', {'mode': 'invalid', 'diagnostic': 'bad crc'}, probe,
            equals('1 invalid-crc uboot-env-invalid-crc'))
        run('fallback warning without CRC text', {'mode': 'invalid', 'diagnostic': 'Using default environment'}, probe,
            equals('1 invalid-crc uboot-env-invalid-crc'))
        run('I/O failure', {'mode': 'io'}, probe, equals('2 unreadable uboot-env-unreadable'))
        run('CRC text plus failed read does not authorize initialization',
            {'mode': 'invalid', 'probeRc': 1}, probe, equals('2 unreadable uboot-env-unreadable'))
        run('unrecognized successful-read warning', {'mode': 'warning'}, probe,
            equals('2 unreadable uboot-env-unreadable'))

        def invalid_status(output, state):
            status = json.loads(output)
            assert status['supported'] == 1 and status['env_state'] == 'invalid-crc'
            assert status['reason'] == 'uboot-env-invalid-crc' and status['recovery_active'] == 0
            assert not state['writes']
        run('status ignores fallback recovery trigger',
            {'mode': 'invalid', 'values': {'recovery_trigger': '1', 'bootcmd': 'http_recovery'}},
            'get_status', invalid_status)

        def io_status(output, state):
            status = json.loads(output)
            assert status['supported'] == 0 and status['env_state'] == 'unreadable'
            assert not state['writes']
        run('status reports unreadable', {'mode': 'io'}, 'get_status', io_status)

        def no_initialization(output, state):
            assert output == '1' and not state['writes']
        run('I/O fault never initializes boot environment', {'mode': 'io'},
            'ensure_boot_env; printf "%s\\n" "$?"', no_initialization)

        def initialized(output, state):
            assert output == '0' and state['mode'] == 'valid'
            assert len(state['writes']) == len(values) and state['values'] == values
        run('CRC-invalid environment initializes known defaults', {'mode': 'invalid', 'values': {}},
            'ensure_boot_env; printf "%s\\n" "$?"', initialized)

        custom = values.copy()
        custom.update(bootcmd='run owner_boot', bootargs='owner arguments')
        def preserved(output, state):
            assert output == '0' and not state['writes'] and state['values'] == custom
        run('valid owner boot command and arguments preserved', {'values': custom},
            'ensure_boot_env; printf "%s\\n" "$?"', preserved)
        run('CRC-invalid fallback value never verifies a write', {'mode': 'invalid', 'keepInvalid': True},
            'env_write recovery_trigger 1; printf "%s\\n" "$?"', equals('2'))
        run('readback exit failure never verifies matching text', {'readbackRc': 1},
            'env_write recovery_trigger 1; printf "%s\\n" "$?"', equals('2'))
        run('valid write and readback', {}, 'env_write recovery_trigger 1; printf "%s\\n" "$?"', equals('0'))

        def refused_reboot(output, state):
            assert json.loads(output)['success'] is False and not state['writes']
            assert not (directory / 'reboot-marker').exists()
        run('recovery refuses read failure without writes or reboot', {'mode': 'io'},
            'reboot_to_uboot', refused_reboot)

    report = {'passed': True, 'cases': cases,
              'sourceSha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'scope': 'Actual shell function bodies with envtools, board discovery and reboot mocked',
              'hardwareTouched': False, 'realEnvironmentWritten': False}
    (OUT / 'recovery-test-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'cases': len(cases)}))


if __name__ == '__main__':
    main()
