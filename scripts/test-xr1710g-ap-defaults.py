#!/usr/bin/env python3
"""Exercise shipped AP defaults with the firmware's real ARM UCI library."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import time

source = Path('/home/xrdev/projects/xr1710g/openwrt/build_dir/target-aarch64_cortex-a53_musl/root-airoha')
work = Path('/home/xrdev/artifacts/xr1710g/qa') / str(time.time_ns())
assert os.geteuid() == 0, 'Run inside Debian-XR1710G with sudo'
shutil.copytree(source, work, symlinks=True)
# Use a native static shell for child process dispatch, without changing
# global WSL binfmt registrations. UCI and ucode stay the actual ARM binaries.
shutil.copy2('/bin/busybox', work / 'bin/busybox')
shutil.copy2('/usr/bin/qemu-aarch64', work / 'qemu-aarch64')
for relative in ('sbin/uci', 'usr/bin/ucode'):
    executable = work / relative
    executable.rename(str(executable) + '.arm')
    executable.write_text(f'#!/bin/sh\nexec /qemu-aarch64 /{relative}.arm "$@"\n')
    executable.chmod(0o755)

def run(*args):
    result = subprocess.run(['chroot', str(work), *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{args}: {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result.stdout.strip()

def uci(*args):
    return run('/sbin/uci', *args)

def write(relative, text):
    path = work / relative.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)

write('/tmp/sysinfo/board_name', 'gemtek,xr1710g\n')
(work / 'tmp/lock').mkdir(parents=True, exist_ok=True)
(work / 'sys/class/ieee80211/phy0').mkdir(parents=True, exist_ok=True)
write('/etc/config/network', '''config device
 option name 'br-lan'
 option type 'bridge'
 list ports 'lan2'
 list ports 'lan3'
 list ports 'lan4'
config interface 'lan'
 option device 'br-lan'
 option proto 'static'
 option ipaddr '198.51.100.1'
 option netmask '255.255.255.0'
 option gateway '198.51.100.254'
 option ip6assign '60'
config interface 'wan'
 option device 'wan'
 option proto 'dhcp'
config interface 'wan6'
 option device 'wan'
 option proto 'dhcpv6'
''')
write('/etc/config/dhcp', '''config dnsmasq
 option port '53'
config dhcp 'lan'
 option interface 'lan'
 option ignore '0'
 option ra 'server'
 option dhcpv6 'server'
 option ndp 'proxy'
''')
write('/etc/config/system', "config system\n option hostname 'Fixture'\n")
# Reordered bands ensure the AP path uses the band's identity, not radio index.
write('/etc/config/wireless', '''config wifi-device 'radio0'
 option type 'mac80211'
 option band '6g'
 option disabled '0'
config wifi-device 'radio1'
 option type 'mac80211'
 option band '2g'
 option disabled '0'
config wifi-device 'radio2'
 option type 'mac80211'
 option band '5g'
 option disabled '0'
''')
# Factory volume fixtures use the real DTS nvmem offset; MAC overrides on
# running NICs must not affect first-boot role detection.
write('/sys/class/ubi/ubi0_3/name', 'factory\n')
nvmem=work/'sys/bus/nvmem/devices/ubi0_3/nvmem'
nvmem.parent.mkdir(parents=True,exist_ok=True)
nvmem.write_bytes(b'\0'*24576+bytes.fromhex('005828d78509'))
factory_configs={name:(work/'etc/config'/name).read_bytes() for name in
                 ['network','dhcp','wireless','system','firewall','xr1710g_ap','xr1710g_ap_configurator']}
factory_bytes_before=nvmem.read_bytes()
run('/bin/sh', '/etc/uci-defaults/03_wireless')
for radio, width in (('radio0', 'EHT160'), ('radio1', 'HE20'), ('radio2', 'EHT80')):
    assert uci('get', f'wireless.{radio}.disabled') == '1'
    assert uci('get', f'wireless.{radio}.htmode') == width
    assert uci('get', f'wireless.{radio}.country') == 'AU'

run('/bin/sh', '/etc/uci-defaults/95-xr1710g-ap')
assert uci('get', 'network.lan.proto') == 'static'
assert uci('get', 'network.lan.device') == 'br-lan'
assert uci('get', 'network.lan.ipaddr') == '192.168.10.3'
assert uci('get', 'network.lan.netmask') == '255.255.255.0'
assert uci('get', 'network.lan.gateway') == '192.168.10.1'
assert uci('get', 'network.lan.dns') == '192.168.10.1'
assert uci('get', 'dhcp.lan.ignore') == '1'
assert uci('get', 'dhcp.@dnsmasq[0].port') == '0'
assert uci('get', 'dhcp.lan.ra') == 'disabled'
assert uci('get', 'dhcp.lan.dhcpv6') == 'disabled'
assert uci('get', 'dhcp.lan.ndp') == 'disabled'
assert uci('get', 'firewall.@defaults[0].flow_offloading') == '0'
assert uci('get', 'firewall.@defaults[0].flow_offloading_hw') == '0'
assert uci('get', 'network.@device[0].ports') == 'lan2 lan3 lan4 wan'
assert uci('get', 'system.@system[0].hostname') == 'XR1710G-AP1'
for key in ('network.wan', 'network.wan6', 'network.lan.ip6assign'):
    assert subprocess.run(['chroot', str(work), '/sbin/uci', '-q', 'get', key], capture_output=True).returncode != 0
assert not list((work / 'etc/rc.d').glob('S*dnsmasq'))
assert not list((work / 'etc/rc.d').glob('S*odhcpd'))

# An upgrade reruns uci-defaults. Keep the operator's VLANs, static address,
# radio policy and offload choice once initialization has been saved.
uci('set', 'network.lan.proto=static')
uci('set', 'network.lan.ipaddr=198.51.100.20')
uci('set', 'network.iot=interface')
uci('set', 'network.iot.device=br-lan.30')
uci('set', 'network.iot.proto=none')
uci('set', 'wireless.radio1.disabled=0')
uci('set', 'wireless.radio1.country=NZ')
uci('set', 'firewall.@defaults[0].flow_offloading=1')
uci('commit')
before = {name: uci('export', name) for name in ('network', 'dhcp', 'wireless', 'firewall', 'system')}
for script in ('03_wireless', '11-xr1710g-cpufreq-defaults', '18-xr1710g-firewall-defaults', '95-xr1710g-ap'):
    run('/bin/sh', '/etc/uci-defaults/' + script)
after = {name: uci('export', name) for name in before}
assert before == after, 'Upgrade overwrote an operator configuration'

write('/tmp/sysinfo/board_name', 'gemtek,w1700k-ubi\n')
uci('-q', 'delete', 'xr1710g_ap.defaults.initialized')
uci('commit', 'xr1710g_ap')
run('/bin/sh', '/etc/uci-defaults/95-xr1710g-ap')
assert uci('export', 'network') == before['network'], 'AP script modified a different board'
run('/usr/bin/ucode', '-c', '-o', '/tmp/mac80211.ucb', '/lib/wifi/mac80211.uc')
recovery = '/usr/libexec/rpcd/luci.airoha_recovery'
assert set(json.loads(run('/bin/sh', recovery, 'list'))) == {'getStatus', 'rebootToUboot'}
status = json.loads(run('/bin/sh', recovery, 'call', 'getStatus'))
assert status['supported'] == 0 and status['reason'] == 'unsupported-board'
write('/tmp/sysinfo/board_name', 'gemtek,xr1710g\n')
status = json.loads(run('/bin/sh', recovery, 'call', 'getStatus'))
assert status['supported'] == 0 and status['reason'] == 'ubootenv-volume-not-found'
acl = json.loads((work / 'usr/share/rpcd/acl.d/luci-app-airoha-recovery.json').read_text())['luci-app-airoha-recovery']
assert acl['read']['ubus']['luci.airoha_recovery'] == ['getStatus']
assert acl['write']['ubus']['luci.airoha_recovery'] == ['rebootToUboot']
# The same image resets AP2 back to its hardware-selected .4, with no
# dependency on overlay data, U-Boot environment writes or operator NIC MACs.
def factory_reset(mac):
    for name,data in factory_configs.items():
        (work/'etc/config'/name).write_bytes(data)
    nvmem.write_bytes(b'\0'*24576+bytes.fromhex(mac))
    write('/tmp/sysinfo/board_name','gemtek,xr1710g\n')
    before_identity=nvmem.read_bytes()
    run('/bin/sh','/etc/uci-defaults/03_wireless')
    run('/bin/sh','/etc/uci-defaults/95-xr1710g-ap')
    assert nvmem.read_bytes()==before_identity, 'Factory identity was modified'

for _ in range(2):
    factory_reset('005828d749f2')
    assert uci('get','network.lan.ipaddr')=='192.168.10.4'
    assert uci('get','system.@system[0].hostname')=='XR1710G-AP2'
    assert uci('get','xr1710g_ap_configurator.profile.management_ip')=='192.168.10.4'
    assert uci('get','xr1710g_ap_configurator.profile.role')=='ap2'
    assert subprocess.run(['chroot',str(work),'/sbin/uci','-q','get','xr1710g_ap_configurator.profile.uplink_port'],capture_output=True).returncode!=0
    assert uci('get','dhcp.lan.ignore')=='1'
    for radio in ('radio0','radio1','radio2'): assert uci('get',f'wireless.{radio}.disabled')=='1'
    assert not list((work/'etc/rc.d').glob('S*dnsmasq'))
    assert not list((work/'etc/rc.d').glob('S*odhcpd'))
write('/sys/class/net/lan2/address','00:58:28:d7:85:09\n')
role=json.loads(run('/bin/sh','/usr/sbin/xr1710g-ap-role'))
assert role['role']=='ap2' and role['management_address']=='192.168.10.4'
# An ordinary AP2 upgrade preserves private runtime keys and operator choices.
uci('set','xr1710g_ap_configurator.mesh.key=fixture-private-mesh-key')
uci('set','network.lan.ipaddr=192.168.10.4')
uci('set','wireless.radio2.disabled=0')
uci('commit')
before={name:uci('export',name) for name in factory_configs}
run('/bin/sh','/etc/uci-defaults/95-xr1710g-ap')
assert before=={name:uci('export',name) for name in before}

factory_reset('005828d78509')
assert uci('get','xr1710g_ap_configurator.profile.role')=='ap1'
assert uci('get','xr1710g_ap_configurator.profile.uplink_port')=='lan2'
assert nvmem.read_bytes()==factory_bytes_before
factory_reset('020000000099')
assert uci('get','network.lan.proto')=='dhcp'
assert uci('get','xr1710g_ap_configurator.profile.role')=='unassigned'
assert uci('get','system.@system[0].hostname')=='XR1710G-Unassigned'
assert subprocess.run(['chroot',str(work),'/sbin/uci','-q','get','network.lan.ipaddr'],capture_output=True).returncode!=0
for radio in ('radio0','radio1','radio2'): assert uci('get',f'wireless.{radio}.disabled')=='1'
# Missing, ambiguous and truncated factory data never assigns either fixed IP.
(work/'sys/class/ubi/ubi0_3/name').unlink()
assert json.loads(run('/bin/sh','/usr/sbin/xr1710g-ap-role'))['identity_state']=='factory-unavailable'
write('/sys/class/ubi/ubi0_3/name','factory\n')
write('/sys/class/ubi/ubi0_4/name','factory\n')
assert json.loads(run('/bin/sh','/usr/sbin/xr1710g-ap-role'))['identity_state']=='ambiguous-factory'
(work/'sys/class/ubi/ubi0_4/name').unlink()
nvmem.write_bytes(b'\0'*24576+b'\x00\x58')
assert json.loads(run('/bin/sh','/usr/sbin/xr1710g-ap-role'))['identity_state']=='invalid-factory-mac'
factory_reset('005828d78509')

# Exercise actual shipped factory/upgrade hooks. The owner's plaintext input
# stays outside the checkout and never enters assertion output or QA reports.
import ctypes
settings = json.loads(Path('/mnt/d/ChatGPT/XR1710G/environment/private/ap11-user-settings.json').read_text())
crypt_lib = ctypes.CDLL('libcrypt.so.1')
crypt_lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
crypt_lib.crypt.restype = ctypes.c_char_p
admin_hook = '/etc/uci-defaults/97-xr1710g-admin-defaults'

def reset_admin_marker():
    subprocess.run(['chroot', str(work), '/sbin/uci', '-q', 'delete', 'xr1710g_ap.defaults.admin_initialized'], capture_output=True)
    uci('commit', 'xr1710g_ap')

original_shadow = 'root:::0:99999:7:::\ndaemon:*:0:0:99999:7:::\n'
write('/etc/shadow', original_shadow)
reset_admin_marker()
uci('set', 'luci.main.lang=auto')
uci('commit', 'luci')
run('/bin/sh', admin_hook)
shadow = (work / 'etc/shadow').read_text()
factory_hash = shadow.splitlines()[0].split(':')[1]
assert factory_hash.startswith('$6$'), 'Factory password is not a SHA-512 crypt hash'
assert crypt_lib.crypt(settings['rootPassword'].encode(), factory_hash.encode()).decode() == factory_hash, 'Factory password verification failed'
assert settings['rootPassword'] not in (work / admin_hook.lstrip('/')).read_text(), 'Plain password leaked into factory hook'
assert shadow.splitlines()[1:] == original_shadow.splitlines()[1:], 'Non-root shadow records changed'
assert (work / 'etc/shadow').stat().st_mode & 0o777 == 0o600
assert uci('get', 'luci.main.lang') == 'zh_cn'
assert uci('get', 'xr1710g_ap.defaults.admin_initialized') == '1'

# Later upgrades preserve both an operator-selected password and language.
owner_hash = crypt_lib.crypt(b'fixture-upgrade-password', b'$6$upgradefixture$').decode()
write('/etc/shadow', original_shadow.replace('root::', 'root:' + owner_hash + ':', 1))
uci('set', 'luci.main.lang=en')
uci('commit', 'luci')
run('/bin/sh', admin_hook)
assert (work / 'etc/shadow').read_text().split(':')[1] == owner_hash, 'Upgrade changed root password'
assert uci('get', 'luci.main.lang') == 'en', 'Repeated upgrade changed selected language'

# AP10 -> AP11 adds the Chinese default without changing an existing login.
reset_admin_marker()
run('/bin/sh', admin_hook)
assert (work / 'etc/shadow').read_text().split(':')[1] == owner_hash
assert uci('get', 'luci.main.lang') == 'zh_cn'

reset_admin_marker()
write('/etc/shadow', original_shadow.replace('root::', 'root:!:', 1))
run('/bin/sh', admin_hook)
assert (work / 'etc/shadow').read_text().split(':')[1] == '!', 'Factory migration unlocked an operator-locked account'

reset_admin_marker()
write('/etc/shadow', original_shadow)
uci('set', 'luci.main.lang=auto')
uci('commit', 'luci')
write('/tmp/sysinfo/board_name', 'gemtek,w1700k-ubi\n')
run('/bin/sh', admin_hook)
assert (work / 'etc/shadow').read_text() == original_shadow
assert uci('get', 'luci.main.lang') == 'auto'
write('/tmp/sysinfo/board_name', 'gemtek,xr1710g\n')

# Fail closed if the login database is incomplete; do not mark initialized.
write('/etc/shadow', 'daemon:*:0:0:99999:7:::\n')
failure = subprocess.run(['chroot', str(work), '/bin/sh', admin_hook], capture_output=True)
assert failure.returncode != 0
assert uci('get', 'luci.main.lang') == 'auto'
assert subprocess.run(['chroot', str(work), '/sbin/uci', '-q', 'get', 'xr1710g_ap.defaults.admin_initialized'], capture_output=True).returncode != 0

catalogs = list((work / 'usr/lib/lua/luci/i18n').glob('*.zh-cn.lmo'))
assert len(catalogs) >= 5 and all(p.stat().st_size > 0 for p in catalogs), 'Chinese catalog is missing or empty'

result = {'passed': True, 'fixture': str(work), 'runtime': 'shipped ARM UCI/ucode under QEMU, native static shell',
          'checks': ['first boot bridge/static 192.168.10.3/main gateway and DNS/no DHCP or DNS server', 'reordered radio bands/AU country',
                     'upgrade preserves VLAN/address/wireless/offload', 'other board untouched',
                     'recovery RPC and ACL present; unavailable boot environment blocks recovery',
                     'wireless generator compiles with shipped modules', 'factory root hash verifies against private owner input', 'Simplified Chinese default and five nonempty catalogs', 'credential/language upgrade preservation and locked-account protection', 'admin defaults leave other board untouched and reject missing root record', 'same image AP2 factory/reset restores192.168.10.4 and independent hostname', 'factory identity is read-only and NIC MAC override ignored', 'AP2 upgrade preserves private mesh keys and configuration', 'unknown missing ambiguous truncated factory identity selects addressless DHCP client with radios off'], 'hardwareWirelessTest': False}
(work.parent / 'latest-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
