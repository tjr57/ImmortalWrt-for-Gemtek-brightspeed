"""Integrate the kernel's explicit bridge policy into the existing NPU RPC/UI."""
from pathlib import Path
import difflib, hashlib, json, shutil, subprocess, tempfile
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G')
out=w/'development/ap26';out.mkdir(exist_ok=True)
feed=r/'feeds/app_airoha';app=feed/'luci-app-airoha-npu'
patch=r/'patches/feeds/app_airoha/luci-app-airoha-npu/108-npu-report-and-enforce-boot-PPE-policy.patch'
assert not (out/'source-change.json').exists()
names=['Makefile','root/usr/libexec/rpcd/luci.airoha_npu','htdocs/luci-static/resources/view/airoha_npu/status.js','po/zh_Hans/luci-app-airoha-npu.po']
before={n:(app/n).read_text() for n in names}
for n,s in before.items():
 p=out/'baseline'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)

with tempfile.TemporaryDirectory(prefix='ap26-feed-base-') as temp:
 base=Path(temp);shutil.copytree(app,base/app.name)
 subprocess.run(['git','apply','--reverse'],cwd=base,input=patch.read_bytes(),check=True)
 originals={n:(base/app.name/n).read_text() for n in names}

rpc=before[names[1]]
start=rpc.index('_bridge_offload_blocked() {');end=rpc.index('\n# Discover the active cpufreq',start)
rpc=rpc[:start]+'''# The explicit bridge-rule ABI is independent of global PPE permission.
# Legacy sysctl switches do not publish the exact TC templates this ABI needs.
_ppe_bool_file() {
	local value
	value=$(cat "$1" 2>/dev/null)
	case "$value" in
	N|n|0) printf 'false' ;;
	Y|y|1) printf 'true' ;;
	*) printf 'null' ;;
	esac
}

_bridge_offload_reason() {
	if _ppe_binding_disabled; then
		printf 'ppe_boot_policy_disabled'
	elif _has_active_wan; then
		printf 'active_wan'
	elif [ -e /sys/module/airoha_eth/parameters/ppe_bridge_bind_enable ]; then
		case "$(_ppe_bool_file /sys/module/airoha_eth/parameters/ppe_bridge_bind_enable)" in
		false) printf 'ppe_bridge_boot_policy_disabled'; return ;;
		true) ;;
		*) printf 'ppe_bridge_policy_unavailable'; return ;;
		esac
		case "$(_ppe_bool_file /sys/kernel/debug/ppe/xr_l2_policy_latched)" in
		true) printf 'ppe_bridge_policy_latched' ;;
		false) printf 'ppe_explicit_rules_required' ;;
		*) printf 'ppe_bridge_policy_unavailable' ;;
		esac
	fi
}

_bridge_offload_blocked() {
	[ -n "$(_bridge_offload_reason)" ]
}

_bridge_offload_block_error() {
	local reason message
	reason=$(_bridge_offload_reason)
	case "$reason" in
	ppe_boot_policy_disabled) message='PPE forwarding is disabled for this boot; wireless DMA has a separate policy.' ;;
	active_wan) message='Use hardware flow offload in router mode.' ;;
	ppe_bridge_boot_policy_disabled) message='PPE bridge forwarding is disabled for this boot.' ;;
	ppe_bridge_policy_latched) message='Bridge filtering requires software forwarding for this boot.' ;;
	ppe_explicit_rules_required) message='This kernel requires explicit forwarding rules; these switches cannot enable hardware bridge offload.' ;;
	*) message='Bridge forwarding policy is unavailable.' ;;
	esac
	printf '{"error":"%s","reason":"%s"}' "$message" "$reason"
}

_ppe_disabled_status() {
	printf '{"enabled":0,"policy_blocked":true,"reason":"ppe_boot_policy_disabled"}'
}

_bridge_disabled_status() {
	printf '{"enabled":0,"policy_blocked":true,"reason":"%s"}' "$(_bridge_offload_reason)"
}

get_device_mode() {
	local mode='ap' reason='no_active_wan' blocked='false'
	local binding hardware_blocked='false' block_reason='' bridge_binding latch

	if _has_active_wan; then
		mode='router'
		reason='active_wan'
	elif [ "$(uci get dhcp.lan.ignore 2>/dev/null)" = '1' ]; then
		reason='dhcp_disabled'
	fi

	binding=$(_ppe_bind_policy)
	[ "$binding" = 'false' ] && hardware_blocked='true'
	bridge_binding=$(_ppe_bool_file /sys/module/airoha_eth/parameters/ppe_bridge_bind_enable)
	latch=$(_ppe_bool_file /sys/kernel/debug/ppe/xr_l2_policy_latched)
	block_reason=$(_bridge_offload_reason)
	[ -n "$block_reason" ] && blocked='true'
	printf '{"mode":"%s","reason":"%s","bridge_offload_blocked":%s,"bridge_offload_block_reason":"%s","ppe_binding_enabled":%s,"hardware_flow_offload_blocked":%s,"ppe_bridge_binding_enabled":%s,"ppe_bridge_policy_latched":%s}' \\
		"$mode" "$reason" "$blocked" "$block_reason" "$binding" "$hardware_blocked" "$bridge_binding" "$latch"
}
''' + rpc[end:]
for name in ['get_vlan_offload','get_pppoe_offload','get_apmode_offload']:
 start=rpc.index(name+'() {');end=rpc.index('\n}',start)+2
 func=rpc[start:end];assert 'if _ppe_binding_disabled; then\n\t\t_ppe_disabled_status' in func
 func=func.replace('if _ppe_binding_disabled; then\n\t\t_ppe_disabled_status','if _bridge_offload_blocked; then\n\t\t_bridge_disabled_status')
 rpc=rpc[:start]+func+rpc[end:]
(app/names[1]).write_text(rpc)
js=before[names[2]]
start=js.index('function offloadBlockText(');end=js.index('\n/* Token-pool',start)
js=js[:start]+'''function offloadBlockText(mode) {
	if (isPpeBootPolicyBlocked(mode))
		return _('PPE forwarding is disabled for this boot; WLAN DMA policy is shown separately.');
	switch ((mode || {}).bridge_offload_block_reason) {
	case 'ppe_bridge_boot_policy_disabled':
		return _('PPE bridge forwarding is disabled for this boot.');
	case 'ppe_bridge_policy_latched':
		return _('Bridge filtering requires software forwarding for this boot.');
	case 'ppe_explicit_rules_required':
		return _('This kernel requires explicit forwarding rules; these switches cannot enable hardware bridge offload.');
	case 'ppe_bridge_policy_unavailable':
		return _('Bridge forwarding policy is unavailable.');
	default:
		return _('Use hardware flow offload in router mode');
	}
}

function offloadBlockLabel(mode) {
	if (isPpeBootPolicyBlocked(mode)) return _('Disabled by boot policy');
	switch ((mode || {}).bridge_offload_block_reason) {
	case 'ppe_bridge_boot_policy_disabled': return _('Bridge disabled by boot policy');
	case 'ppe_bridge_policy_latched': return _('Software forwarding required');
	case 'ppe_explicit_rules_required': return _('Explicit forwarding rules required');
	case 'ppe_bridge_policy_unavailable': return _('Forwarding policy unavailable');
	default: return _('Router mode restricted');
	}
}
''' + js[end:]
(app/names[2]).write_text(js)
translations={
 'PPE forwarding is disabled for this boot; WLAN DMA policy is shown separately.':'本次启动已关闭 PPE 硬件转发；无线 DMA 策略单独显示。',
 'PPE bridge forwarding is disabled for this boot.':'本次启动已关闭 PPE 桥接转发。',
 'Bridge filtering requires software forwarding for this boot.':'当前桥接过滤策略要求本次启动使用软件转发。',
 'This kernel requires explicit forwarding rules; these switches cannot enable hardware bridge offload.':'当前内核需要明确的转发规则；这些开关无法启用桥接硬件卸载。',
 'Bridge forwarding policy is unavailable.':'无法读取桥接转发策略。',
 'Bridge disabled by boot policy':'启动策略已关闭桥接加速',
 'Software forwarding required':'当前需要软件转发',
 'Explicit forwarding rules required':'需要明确的转发规则',
 'Forwarding policy unavailable':'转发策略不可用',
}
po=before[names[3]]
for english,chinese in translations.items():
 if 'msgid "'+english+'"' not in po:
  po+='\nmsgid '+json.dumps(english)+'\nmsgstr '+json.dumps(chinese,ensure_ascii=False)+'\n'
(app/names[3]).write_text(po)
assert 'PKG_RELEASE:=6' in before['Makefile']
(app/'Makefile').write_text(before['Makefile'].replace('PKG_RELEASE:=6','PKG_RELEASE:=7'))
header='''Subject: [PATCH] luci-app-airoha-npu: enforce independent PPE bridge and WLAN policies
SPDX-License-Identifier: Apache-2.0

Keep the cumulative policy/UI patch idempotent across feed preparation.
Expose bridge opt-in and the kernel policy latch. The explicit-rule bridge
ABI cannot be enabled by legacy sysctl-only switches; retain software policy.
Global route permission and wireless NPU attachment remain independent.

'''
delta=header
for n in names:
 delta+=''.join(difflib.unified_diff(originals[n].splitlines(True),(app/n).read_text().splitlines(True),fromfile='a/luci-app-airoha-npu/'+n,tofile='b/luci-app-airoha-npu/'+n))
patch.write_text(delta)
subprocess.run(['git','apply','--reverse','--check'],cwd=feed,input=patch.read_bytes(),check=True)
with tempfile.TemporaryDirectory(prefix='ap26-feed-regenerate-') as temp:
 base=Path(temp)
 for n,s in originals.items():
  p=base/app.name/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
 subprocess.run(['git','apply'],cwd=base,input=patch.read_bytes(),check=True)
 assert all((base/app.name/n).read_bytes()==(app/n).read_bytes() for n in names)
report={'passed':True,'scope':'PPE bridge-policy RPC enforcement and simplified Chinese UI reasons',
 'kernelDriverOrBootServiceChanged':False,'defaultsChanged':False,'freshPatchRegenerationPassed':True,
 'files':{n:hashlib.sha256((app/n).read_bytes()).hexdigest() for n in names}}
(out/'source-change.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
