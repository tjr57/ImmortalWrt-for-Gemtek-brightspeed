#!/usr/bin/env python3
"""Run the configurator against isolated files and the built ARM UCI binary.

The runtime is copied before executing QEMU; neither the live host configuration
nor the OpenWrt build root is modified. Test passphrases are fixture data only.
"""
import argparse
import hashlib
import json
import os
import pathlib
import pty
import select
import shutil
import subprocess
import tempfile
import termios
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=pathlib.Path)
    parser.add_argument('--shell', choices=['sh', 'busybox-ash'], default='busybox-ash')
    args = parser.parse_args()
    package = pathlib.Path(__file__).resolve().parent.parent
    program = package / 'files/xr1710g-ap-configure'
    baseline = package / 'files/xr1710g_ap_configurator'
    assert '.key' not in baseline.read_text(), 'Shipped profile must not contain any wireless key'
    with tempfile.TemporaryDirectory(prefix='xr1710g-configurator-test-') as folder:
        root = pathlib.Path(folder)
        runtime = root / 'runtime'
        shutil.copytree(args.runtime_root, runtime, symlinks=True)
        conf = root / 'config'
        conf.mkdir()
        (root / 'tmp').mkdir()
        (root / 'lock').mkdir()
        (root / 'delta').mkdir()
        foreign_delta = root / 'foreign-delta'; foreign_delta.mkdir()
        wrapper = root / 'uci'
        wrapper.write_text('#!/bin/sh\nexec /usr/bin/qemu-aarch64 -L "' + str(runtime) +
                           '" "' + str(runtime / 'sbin/uci') +
                           '" -p "' + str(foreign_delta) + '" "$@"\n')
        wrapper.chmod(0o755)
        env = dict(os.environ, XR1710G_CONFIG_DIR=str(conf), XR1710G_UCI=str(wrapper),
                   XR1710G_TMP_DIR=str(root / 'tmp'), XR1710G_LOCK_DIR=str(root / 'lock'))
        shell = ['/bin/busybox', 'ash'] if args.shell == 'busybox-ash' else ['/bin/sh']
        count = 0
        secret = 'fixture-only-\'"\\;$value'
        iot_secret = 'fixture-iot-only-2026'
        mesh_secret = 'fixture-mesh-only-2026'

        def snapshot():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in conf.iterdir() if p.is_file() and not p.name.startswith('.')}

        def u(*argv, input=None, okay=True):
            out = subprocess.run([str(wrapper), '-c', str(conf), '-t', str(root / 'delta'),
                                  *argv], input=input,
                                 text=True, capture_output=True)
            if okay:
                assert out.returncode == 0, out.stderr
            return out.stdout.rstrip('\n')

        def put(path, value):
            value = value.replace('\\', '\\\\').replace('"', '\\"')
            u('batch', input=f'set {path}="{value}"\n')
            u('commit', path.split('.')[0])

        def run(action, *argv, data=None, success=True, extra_env=None, shell_override=None):
            nonlocal count
            current_env = env if extra_env is None else dict(env, **extra_env)
            out = subprocess.run([*(shell_override or shell), str(program), action, *argv], input=data,
                                 text=True, capture_output=True, env=current_env)
            assert (out.returncode == 0) == success, (action, out.stdout, out.stderr)
            assert secret not in out.stdout + out.stderr
            assert iot_secret not in out.stdout + out.stderr
            assert mesh_secret not in out.stdout + out.stderr
            assert not list((root / 'lock').iterdir()), 'Lock was not released'
            count += 1
            return out

        def rejected(change, value):
            before_value = u('get', change)
            put(change, value)
            before = snapshot()
            run('apply', success=False)
            assert snapshot() == before, 'Rejected input changed live UCI files'
            put(change, before_value)

        shutil.copy2(baseline, conf / 'xr1710g_ap_configurator')
        # The shipped credential-free preset is inactive/unassigned. These
        # fixtures exercise the explicit owner-provisioned AP1 profile.
        put('xr1710g_ap_configurator.profile.management_ip','192.168.10.3')
        put('xr1710g_ap_configurator.profile.role','ap1')
        put('xr1710g_ap_configurator.profile.uplink_port','wan')
        put('xr1710g_ap_configurator.users.enabled','1')
        put('xr1710g_ap_configurator.iot.enabled','1')
        (conf / 'network').write_text('''config device 'bridge0'
 option name 'br-lan'
 option type 'bridge'
 list ports 'lan2'
config interface 'lan'
 option device 'br-lan'
 option proto 'dhcp'
 option ip6assign '60'
config interface 'wan'
 option device 'wan'
 option proto 'dhcp'
config interface 'wan6'
 option device 'wan'
 option proto 'dhcpv6'
config bridge-vlan
 option device 'br-lan'
 option vlan '300'
 list ports 'wan:t'
config bridge-vlan
 option device 'br-lan'
 option vlan '301'
 list ports 'lan2:t'
config bridge-vlan 'unrelated'
 option device 'br-guest'
 option vlan '100'
''')
        (conf / 'wireless').write_text('''config wifi-device 'radio7'
 option band '6g'
 option disabled '0'
config wifi-device 'radio3'
 option band '5g'
 option disabled '0'
config wifi-device 'radio0'
 option band '2g'
 option disabled '0'
config wifi-iface 'factory'
 option device 'radio3'
 option network 'lan'
 option ssid 'Old-test-SSID'
 option disabled '0'
''')
        (conf / 'dhcp').write_text('''config dnsmasq
 option port '53'
config dnsmasq 'second'
 option port '5353'
config dhcp 'lan'
 option interface 'lan'
 option ignore '0'
 option ra 'server'
 option dhcpv6 'server'
config dhcp 'extra'
 option interface 'guest'
 option ignore '0'
config odhcpd 'odhcpd'
 option maindhcp '1'
''')

        before = snapshot()
        plan = run('plan', success=False)
        assert 'enabled=0, VLAN=unassigned' in plan.stdout
        assert snapshot() == before
        run('key', 'users', data=secret + '\n')
        assert 'option key' in (conf / 'xr1710g_ap_configurator').read_text()
        assert u('get', 'xr1710g_ap_configurator.users.key') == secret
        assert (conf / 'xr1710g_ap_configurator').stat().st_mode & 0o777 == 0o600
        if args.shell == 'busybox-ash':
            master, slave = pty.openpty()
            interactive = subprocess.Popen([*shell, str(program), 'key', 'users'],
                                           stdin=slave, stdout=slave, stderr=slave, env=env)
            captured = b''
            deadline = time.monotonic() + 10
            while termios.tcgetattr(slave)[3] & termios.ECHO:
                assert time.monotonic() < deadline, 'Interactive key prompt did not hide echo'
                time.sleep(0.01)
            os.write(master, (secret + '\n').encode())
            interactive.wait(timeout=10)
            assert interactive.returncode == 0
            while select.select([master], [], [], 0.1)[0]:
                captured += os.read(master, 4096)
            assert secret.encode() not in captured, 'Interactive password was echoed'
            assert termios.tcgetattr(slave)[3] & termios.ECHO, 'Terminal echo was not restored'
            os.close(master); os.close(slave)
            count += 1
            assert u('get', 'xr1710g_ap_configurator.users.key') == secret
        before = snapshot()
        # Simulate the inherited default delta search path without touching
        # the host's /tmp/.uci. Only private fixture files are modified.
        (foreign_delta / 'network').write_text("network.lan.proto='pppoe'\n")
        assert u('get', 'network.lan.proto') == 'pppoe'
        run('validate')
        run('plan')
        assert snapshot() == before, 'Dry run modified live files'
        (foreign_delta / 'network').unlink()
        run('apply')
        assert u('get', 'network.lan.ipaddr') == '192.168.10.3'
        assert u('get', 'network.lan.device') == 'br-lan'
        assert u('get', 'network.lan.proto') == 'static'
        assert u('get', 'network.bridge0.ports') == 'lan2 lan3 lan4 wan'
        assert u('get', 'network.bridge0.vlan_filtering') == '0'
        assert u('get', 'network.unrelated.vlan') == '100'
        assert u('-q', 'get', 'network.wan', okay=False) == ''
        assert u('-q', 'get', 'network.wan6', okay=False) == ''
        assert '300' not in u('show', 'network') and '301' not in u('show', 'network')
        assert u('get', 'wireless.xr_users.device') == 'radio3'
        assert u('get', 'wireless.xr_users.network') == 'xr_users_gate'
        assert u('get', 'wireless.xr_users.xr1710g_owner') == 'users'
        assert u('get', 'network.xr_users_gate.proto') == 'none'
        assert u('get', 'network.xr_users_gate.auto') == '0'
        assert u('get', 'network.xr_users_gate.device') == 'br-lan'
        assert u('-q', 'get', 'network.xr_users_gate.ipaddr', okay=False) == ''
        assert u('-q', 'get', 'network.xr_users_gate.gateway', okay=False) == ''

        assert u('get', 'wireless.xr_users.key') == secret
        assert u('get', 'wireless.xr_iot.device') == 'radio0'
        assert u('get', 'wireless.xr_iot.disabled') == '1'
        assert u('get', 'wireless.radio0.disabled') == '1'
        assert u('get', 'wireless.radio3.disabled') == '0'
        assert u('get', 'wireless.radio7.disabled') == '1'
        assert u('get', 'wireless.factory.disabled') == '1'
        for radio in ['radio0', 'radio3', 'radio7']:
            assert u('get', f'wireless.{radio}.country') == 'AU'
        for dns in ['@dnsmasq[0]', 'second']:
            assert u('get', f'dhcp.{dns}.port') == '0'
        for section in ['lan', 'extra']:
            assert u('get', f'dhcp.{section}.ignore') == '1'
            for option in ['ra', 'dhcpv6', 'ndp']:
                assert u('get', f'dhcp.{section}.{option}') == 'disabled'

        # Explicit primary survives the VLAN profile transition that formerly
        # changed the live AP to ACS/136 and hid it from the owner's phone.
        put('xr1710g_ap_configurator.users.channel', '44')
        run('apply')
        assert u('get', 'wireless.radio3.channel') == '44'
        assert u('get', 'wireless.radio3.htmode') == 'EHT160'
        rejected('xr1710g_ap_configurator.users.channel', '136')
        rejected('xr1710g_ap_configurator.users.channel', 'auto')

        # VLAN 42 is artificial fixture data, not an assigned production VID.
        put('xr1710g_ap_configurator.iot.vid', '42')
        put('xr1710g_ap_configurator.profile.uplink_port', 'lan3')
        before = snapshot()
        run('apply', success=False)
        assert snapshot() == before
        run('key', 'iot', data=iot_secret + '\n')
        run('apply')
        assert u('get', 'network.bridge0.vlan_filtering') == '1'
        assert u('get', 'network.lan.device') == 'br-lan.1'
        assert u('get', 'network.xr_users_gate.device') == 'br-lan.1'
        assert u('get', 'network.xr_iot.device') == 'br-lan.42'
        assert u('get', 'wireless.radio3.channel') == '44', 'VLAN change restored ACS'
        assert u('get', 'wireless.radio3.htmode') == 'EHT160', 'VLAN change lost requested160MHz'
        assert u('get', 'network.xr_users_vlan.ports') == 'lan2:u* lan3:u* lan4:u* wan:u*'
        assert u('get', 'network.xr_iot_vlan.ports') == 'lan3:t'
        assert u('get', 'wireless.xr_iot.network') == 'xr_iot'
        assert u('get', 'wireless.xr_iot.disabled') == '0'
        assert u('get', 'wireless.radio0.disabled') == '0'

        put('xr1710g_ap_configurator.users.vid', '10')
        put('xr1710g_ap_configurator.profile.uplink_port', 'wan lan3')
        run('apply')
        assert u('get', 'network.lan.device') == 'br-lan.10'
        assert u('get', 'network.xr_users_vlan.ports') == 'lan2:u* lan3:t lan4:u* wan:t'
        assert u('get', 'network.xr_iot_vlan.ports') == 'wan:t lan3:t'
        for value in ['0', '001', '4095', '10', '42;reboot', '-2']:
            rejected('xr1710g_ap_configurator.iot.vid', value)
        rejected('xr1710g_ap_configurator.profile.country', 'US')
        rejected('xr1710g_ap_configurator.profile.uplink_port', 'wan lan3 lan3')
        rejected('xr1710g_ap_configurator.profile.uplink_port', 'wlan0')
        rejected('xr1710g_ap_configurator.users.ssid', 'line1\nline2')
        rejected('xr1710g_ap_configurator.users.enabled', '2')
        rejected('xr1710g_ap_configurator.users.encryption', 'none')
        rejected('xr1710g_ap_configurator.profile.management_ip', '192.168.10.1')
        rejected('xr1710g_ap_configurator.profile.management_ip', '192.168.10.5')
        put('xr1710g_ap_configurator.profile.management_ip', '192.168.10.4')
        run('apply')
        assert u('get', 'network.lan.ipaddr') == '192.168.10.4'
        put('xr1710g_ap_configurator.profile.management_ip', '192.168.10.3')
        run('apply')
        assert u('get', 'network.lan.ipaddr') == '192.168.10.3'

        put('xr1710g_ap_configurator.users.vid', '')
        rejected('xr1710g_ap_configurator.iot.vid', '1')
        put('wireless.extra', 'wifi-device')
        put('wireless.extra.band', '5g')
        before = snapshot()
        run('apply', success=False)
        assert snapshot() == before
        u('delete', 'wireless.extra'); u('commit', 'wireless')
        put('network.legacy', 'interface')
        put('network.legacy.device', 'br-lan.99')
        before = snapshot()
        run('apply', success=False)
        assert snapshot() == before
        u('delete', 'network.legacy'); u('commit', 'network')

        # Force a failure after replacing network, before replacing wireless.
        # The previous configurations must be restored byte-for-byte.
        fault_bin = root / 'fault-bin'; fault_bin.mkdir()
        marker = root / 'fail-once'; marker.touch()
        mv = fault_bin / 'mv'
        mv.write_text('''#!/bin/sh
case "$1" in *.xr-ap-new-*-wireless)
 if [ -f "''' + str(marker) + '''" ]; then
  rm -f "''' + str(marker) + '''"
  exit 1
 fi;; esac
exec /bin/mv "$@"
''')
        mv.chmod(0o755)
        before = snapshot()
        # Debian's static BusyBox ash prefers built-in applets over PATH, so use
        # the host POSIX shell for this external mv failure injection.
        run('apply', success=False, extra_env={'PATH': str(fault_bin) + ':' + os.environ['PATH']},
            shell_override=['/bin/sh'])
        assert snapshot() == before, 'Failed multi-file replacement was not rolled back'
        before = snapshot()
        run('key', 'users', data='short\n', success=False)
        assert snapshot() == before
        run('plan')
        assert snapshot() == before
        # First-AP mesh provisioning only; no live radio/netifd execution.
        put('xr1710g_ap_configurator.mesh.enabled', '1')
        before = snapshot()
        run('apply', success=False)
        assert snapshot() == before, 'Missing mesh key changed live configuration'
        run('key', 'mesh', data=mesh_secret + '\n')
        before = snapshot()
        run('plan')
        assert snapshot() == before
        run('apply')
        assert u('get', 'wireless.xr_mesh6g.mode') == 'mesh'
        assert u('get', 'wireless.xr_mesh6g.ifname') == 'mesh6g'
        assert u('get', 'wireless.xr_mesh6g.network') == 'xr_mesh_backhaul'
        assert u('get', 'wireless.xr_mesh6g.encryption') == 'sae'
        assert u('get', 'wireless.xr_mesh6g.ieee80211w') == '2'
        assert u('get', 'wireless.xr_mesh6g.key') == mesh_secret
        assert u('get', 'wireless.xr_mesh6g.disabled') == '0'
        assert u('get', 'wireless.radio7.channel') == '37'
        assert u('get', 'wireless.radio7.htmode') == 'HE160'
        assert u('get', 'network.xr_mesh_backhaul.device') == 'br-lan'
        assert u('get', 'network.xr_mesh_backhaul.proto') == 'none'
        assert u('-q', 'get', 'network.xr_mesh_backhaul.ipaddr', okay=False) == ''
        assert u('get', 'network.bridge0.stp') == '1'
        assert u('get', 'network.xr_users_vlan.ports').endswith('mesh6g:u*')
        assert u('get', 'network.xr_iot_vlan.ports').endswith('mesh6g:t')
        # AP2 has mesh as its only trunk; the PC debug ports stay native only.
        put('xr1710g_ap_configurator.profile.uplink_port', '')
        run('apply')
        assert u('get', 'network.xr_iot_vlan.ports') == 'mesh6g:t'
        assert u('get', 'network.xr_users_vlan.ports') == 'lan2:u* lan3:u* lan4:u* wan:u* mesh6g:u*'
        rejected('xr1710g_ap_configurator.mesh.enabled', '0')
        put('xr1710g_ap_configurator.profile.uplink_port', 'wan lan3')
        put('xr1710g_ap_configurator.users.vid', '10')
        run('apply')
        assert u('get', 'network.xr_users_vlan.ports').endswith('mesh6g:t')
        assert u('get', 'network.xr_iot_vlan.ports').endswith('mesh6g:t')
        assert u('get', 'network.lan.device') == 'br-lan.10'
        for setting, value in [('enabled', '2'), ('encryption', 'none'),
                               ('channel', '1'), ('htmode', 'EHT320'),
                               ('mesh_id', 'bad\nidentifier')]:
            rejected('xr1710g_ap_configurator.mesh.' + setting, value)
        rejected('network.xr_mesh_backhaul.xr1710g_owner', 'foreign')
        put('wireless.foreign_mesh', 'wifi-iface')
        put('wireless.foreign_mesh.ifname', 'mesh6g')
        before = snapshot()
        run('apply', success=False)
        assert snapshot() == before
        u('delete', 'wireless.foreign_mesh'); u('commit', 'wireless')
        put('xr1710g_ap_configurator.mesh.enabled', '0')
        run('apply')
        assert u('get', 'wireless.xr_mesh6g.disabled') == '1'
        assert 'mesh6g' not in u('get', 'network.xr_users_vlan.ports')
        assert 'mesh6g' not in u('get', 'network.xr_iot_vlan.ports')
        assert u('get', 'network.xr_mesh_backhaul.auto') == '0'
        u('delete', 'xr1710g_ap_configurator.mesh'); u('commit', 'xr1710g_ap_configurator')
        run('apply')
        assert u('get', 'wireless.radio7.disabled') == '1'
        assert u('get', 'wireless.xr_mesh6g.disabled') == '1'
        # AP13: real ARM-UCI feature transactions and secrets, no live radios.
        put('xr1710g_ap_configurator.users.vid', '')
        put('xr1710g_ap_configurator.roaming.enabled', '1')
        run('apply')
        assert u('get', 'wireless.xr_users.ieee80211k') == '1'
        assert u('get', 'wireless.xr_users.bss_transition') == '1'
        assert u('get', 'wireless.xr_users.ieee80211r') == '1'
        assert u('get', 'wireless.xr_users.mobility_domain') == '1710'
        assert u('get', 'wireless.xr_users.ft_iface') == 'br-lan.1'
        assert u('get', 'wireless.xr_users.ft_over_ds') == '0'
        assert u('get', 'wireless.xr_users.ft_psk_generate_local') == '0'
        ap1_r0=u('get', 'wireless.xr_users.r0kh')
        assert ap1_r0.startswith('00:58:28:d7:49:f4,XR1710G-AP2-users,')
        ft_key=ap1_r0.rsplit(',',1)[1]
        assert len(ft_key)==32 and all(c in '0123456789abcdef' for c in ft_key)
        put('xr1710g_ap_configurator.profile.management_ip','192.168.10.4')
        run('apply')
        assert u('get','wireless.xr_users.nas_identifier')=='XR1710G-AP2-users'
        assert u('get','wireless.xr_users.r0kh')=='00:58:28:d7:85:0b,XR1710G-AP1-users,'+ft_key
        plan=run('plan'); assert ft_key not in plan.stdout+plan.stderr
        rejected('xr1710g_ap_configurator.roaming.mobility_domain','17100')
        rejected('xr1710g_ap_configurator.roaming.mobility_domain','zzzz')
        rejected('xr1710g_ap_configurator.roaming.ieee80211r','2')
        rejected('xr1710g_ap_configurator.users.enabled','0')
        # AP14 automatic PP and canonical FT domain (isolated files only).
        put('xr1710g_ap_configurator.roaming.mobility_domain','abcd')
        run('apply'); canonical_ft=u('get','wireless.xr_users.r0kh')
        put('xr1710g_ap_configurator.roaming.mobility_domain','ABCD')
        run('apply')
        assert u('get','wireless.xr_users.r0kh')==canonical_ft
        assert u('get','wireless.xr_users.mobility_domain')=='abcd'
        put('xr1710g_ap_configurator.roaming.mobility_domain','1710')
        put('xr1710g_ap_configurator.roaming.enabled','0')
        run('apply')
        for key in ('ieee80211r','r0kh','r1kh','nas_identifier','bss_transition'):
            assert u('-q','get','wireless.xr_users.'+key,okay=False)==''

        put('xr1710g_ap_configurator.mlo.enabled','1')
        run('apply')
        assert u('get','wireless.xr_users.device')=='radio3 radio0'
        assert u('get','wireless.xr_users.mlo')=='1'
        assert u('get','wireless.radio0.htmode')=='EHT20'
        assert u('get','wireless.xr_iot.xr1710g_owner')=='iot'
        assert u('get','wireless.xr_iot.network')=='xr_iot'
        assert u('get','wireless.xr_iot.key')==iot_secret
        rejected('xr1710g_ap_configurator.mlo.bands','5g 6g')
        rejected('xr1710g_ap_configurator.mlo.bands','2g 5g')
        rejected('xr1710g_ap_configurator.users.enabled','0')
        rejected('xr1710g_ap_configurator.roaming.enabled','1')
        put('xr1710g_ap_configurator.roaming.ieee80211r','0')
        put('xr1710g_ap_configurator.roaming.enabled','1')
        put('xr1710g_ap_configurator.mesh','wifi')
        put('xr1710g_ap_configurator.mesh.enabled','1')
        put('xr1710g_ap_configurator.mesh.encryption','sae')
        put('xr1710g_ap_configurator.mesh.channel','37')
        put('xr1710g_ap_configurator.mesh.htmode','HE160')
        put('xr1710g_ap_configurator.mesh.mesh_id','fixture-6g-backhaul')
        put('xr1710g_ap_configurator.mesh.key',mesh_secret)
        run('apply')
        assert u('get','wireless.xr_users.ieee80211r')=='0'
        assert u('get','wireless.xr_users.ieee80211k')=='1'
        assert u('get','wireless.xr_mesh6g.device')=='radio7'
        assert u('get','wireless.xr_mesh6g.mode')=='mesh'
        assert u('get','wireless.radio7.htmode')=='HE160'
        assert u('get','network.xr_iot_vlan.ports').endswith('mesh6g:t')
        put('xr1710g_ap_configurator.mlo.enabled','0')
        run('apply')
        assert u('get','wireless.xr_users.device')=='radio3'
        assert u('-q','get','wireless.xr_users.mlo',okay=False)==''

        put('xr1710g_ap_configurator.puncturing.enabled','1')
        put('xr1710g_ap_configurator.puncturing.bitmap','1')
        run('apply')
        assert u('get','wireless.radio3.punct_bitmap')=='1'
        for value in ('4','12','5','255','256','01','-1','1;reboot'):
            rejected('xr1710g_ap_configurator.puncturing.bitmap',value)
        rejected('xr1710g_ap_configurator.puncturing.enabled','0')
        put('xr1710g_ap_configurator.puncturing.enabled','0')
        put('xr1710g_ap_configurator.puncturing.bitmap','0')
        run('apply')
        assert u('-q','get','wireless.radio3.punct_bitmap',okay=False)==''
        put('xr1710g_ap_configurator.puncturing.mode','auto')
        put('xr1710g_ap_configurator.puncturing.enabled','1')
        run('apply')
        assert u('get','wireless.radio3.xr_pp_mode')=='1'
        assert u('-q','get','wireless.radio3.punct_bitmap',okay=False)==''
        rejected('xr1710g_ap_configurator.puncturing.bitmap','1')
        rejected('xr1710g_ap_configurator.puncturing.mode','auto;reboot')
        # AP18 automatic PP policy belongs only to the 5GHz MLD link.
        mesh_before = u('export','network')
        iot_before = u('get','wireless.xr_iot.device')
        put('xr1710g_ap_configurator.mlo.enabled','1')
        run('apply')
        devices = u('get','wireless.xr_users.device').split()
        assert len(devices)==2 and devices[0]=='radio3'
        assert u('get','wireless.radio3.xr_pp_mode')=='1'
        assert u('-q','get','wireless.'+devices[1]+'.xr_pp_mode',okay=False)==''
        assert u('get','wireless.xr_iot.device')==iot_before
        assert u('get','wireless.xr_mesh6g.device')=='radio7'
        assert u('export','network')==mesh_before
        put('xr1710g_ap_configurator.mlo.enabled','0')
        run('apply')

        put('xr1710g_ap_configurator.puncturing.mode','manual')
        put('xr1710g_ap_configurator.puncturing.bitmap','1')
        run('apply')
        assert u('get','wireless.radio3.punct_bitmap')=='1'
        assert u('-q','get','wireless.radio3.xr_pp_mode',okay=False)==''
        put('xr1710g_ap_configurator.puncturing.enabled','0')
        put('xr1710g_ap_configurator.puncturing.bitmap','0')
        run('apply')
        assert u('-q','get','wireless.radio3.xr_pp_mode',okay=False)==''
        for section in ('roaming','mlo','puncturing'):
            u('delete','xr1710g_ap_configurator.'+section)
        u('commit','xr1710g_ap_configurator'); run('apply')
        assert u('get','wireless.xr_users.device')=='radio3'
        assert u('-q','get','wireless.xr_users.ieee80211r',okay=False)==''
        assert u('get','wireless.xr_mesh6g.mode')=='mesh'
        print(json.dumps({'passed': True, 'invocations': count, 'shell': args.shell,
                          'checks': ['real ARM UCI', 'runtime secret escaping and redaction',
                                     'interactive key input without stty', 'foreign delta isolation',
                                     'dry-run immutability', 'radio band reordering',
                                     'native and explicit VLAN membership',
                                     'IoT disabled without VID', 'DHCP/DNS/RA disabled',
                                     'invalid input rejection', 'multi-file rollback',
                                     'mesh SAE and PMF with runtime key',
                                     'mesh parent-bridge attachment and native/tagged VLAN membership',
                                     'mesh disable removes VLAN port memberships',
                                     'mesh ownership and interface-name collision rejection',
                                     'AP8 profile without mesh keeps 6 GHz disabled',
                                     'explicit primary/EHT160 survives VLAN changes; auto and136 rejected',
                                     'AP13 explicit peer FT holders and secret redaction; disabling clears FT',
                                     'AP13 dual-device MLO retains independent IoT and6GHz mesh; MLO+FT rejected',
                                     'AP13 valid static bitmap and primary/pattern rejection; disabling clears bitmap',
                                     'AP12 profiles without new sections retain legacy behavior',
                                     'AP14 canonical FT domain; auto PP transition and reject bitmap/MLO/invalid mode'],
                          'hardware_tested': False}, indent=2))


if __name__ == '__main__':
    main()
