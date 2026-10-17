#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Runtime-only production users BSS gate. Never commits or reloads UCI.
export LC_ALL=C
umask 077

PROFILE='xr1710g_ap_configurator'
OWNED='xr_users'
GATE='xr_users_gate'
EXPECTED_GATEWAY='192.168.10.1'
EXPECTED_ADDRESS='192.168.10.3'
CONFIG_DIR=${XR_GUARD_CONFIG_DIR:-/etc/config}
STATE_DIR=${XR_GUARD_STATE_DIR:-/var/run/xr1710g-uplink-guard}
LOCK_DIR=${XR_GUARD_LOCK_DIR:-/var/lock}
UCI=${XR_GUARD_UCI:-/sbin/uci}
STATUS="$STATE_DIR/status.json"
HOLD="$STATE_DIR/hold"
STOP="$STATE_DIR/stop"
CHECK_LOCK="$LOCK_DIR/xr1710g-uplink-guard.lock"
CONFIG_LOCK="$LOCK_DIR/xr1710g-ap-configurator.lock"
work=''; have_check_lock=0; have_config_lock=0

cleanup_tick() {
	if [ -n "$work" ]; then
		# work is produced by mktemp under this service's private directory.
		rm -rf "$work"
		work=''
	fi
	[ "$have_config_lock" = 0 ] || rmdir "$CONFIG_LOCK" 2>/dev/null
	[ "$have_check_lock" = 0 ] || rmdir "$CHECK_LOCK" 2>/dev/null
	have_check_lock=0; have_config_lock=0
}

valid_name() { case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1 ;; esac; }
valid_key() {
	case "$1" in *'
'*) return 1 ;; esac
	[ "${#1}" -ge 8 ] && [ "${#1}" -le 63 ] && ! printf '%s' "$1" | grep -q '[^ -~]'
}
small_uint() { case "$1" in ''|*[!0-9]*|0*) return 1 ;; esac; [ "${#1}" -le 2 ] && [ "$1" -ge "$2" ] && [ "$1" -le "$3" ]; }
get() { "$UCI" -q -c "$work/config" -C "$work/override" -t "$work/delta" get "${namespace}_$1" 2>/dev/null || true; }
jget() { jsonfilter -s "$1" -e "$2" 2>/dev/null || true; }
oldget() { [ -r "$STATUS" ] && jsonfilter -i "$STATUS" -e "$1" 2>/dev/null || true; }
uptime_seconds() { cut -d. -f1 /proc/uptime; }

emit_status() {
	local old_reason old_actual now json
	old_reason=$(oldget '@.reason'); old_actual=$(oldget '@.gate_autostart')
	now=$(uptime_seconds)
	json="{\"schema\":1,\"owner\":\"$OWNED\",\"gate\":\"$GATE\",\"deployed\":$deployed,\"policy_enabled\":$policy_enabled,\"eligible\":$eligible,\"gateway\":\"$EXPECTED_GATEWAY\",\"management_address\":\"$EXPECTED_ADDRESS\",\"probe_device\":\"$probe_device\",\"reachable\":$reachable,\"success_streak\":$success_streak,\"failure_streak\":$failure_streak,\"desired\":\"$desired\",\"gate_autostart\":\"$actual\",\"bss_state\":\"$bss_state\",\"reason\":\"$reason\",\"last_action\":\"$last_action\",\"transition_count\":$transition_count,\"context\":\"$context\",\"checked_uptime\":$now,\"next_retry_uptime\":$next_retry}"
	printf '%s\n' "$json" > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
	if [ "$reason" != "$old_reason" ] || [ "$actual" != "$old_actual" ] || [ "$last_action" = up ] || [ "$last_action" = down ]; then
		logger -t xr1710g-uplink-guard "gate=$actual desired=$desired reason=$reason action=$last_action"
	fi
}

tick_reset() {
	deployed=false; policy_enabled=true; eligible=false; reachable=false; probe_device=''; context=''
	success_streak=0; failure_streak=0; desired=closed; actual=unknown; bss_state=unknown
	reason=not-configured; last_action=none; interval=5; recovery_required=3; transition_count=0; next_retry=0
	previous_context=$(oldget '@.context')
	previous_success=$(oldget '@.success_streak')
	previous_failure=$(oldget '@.failure_streak')
	previous_transitions=$(oldget '@.transition_count')
	previous_retry=$(oldget '@.next_retry_uptime')
	case "$previous_transitions" in ''|*[!0-9]*) ;; *) transition_count="$previous_transitions" ;; esac
	case "$previous_retry" in ''|*[!0-9]*) ;; *) next_retry="$previous_retry" ;; esac
}

stage_snapshot() {
	local package
	work=$(mktemp -d "$STATE_DIR/check.XXXXXX") || return 1
	namespace="xrg$(basename "$work" | tr -cd 'A-Za-z0-9')"
	mkdir "$work/config" "$work/override" "$work/delta" || return 1
	for package in network wireless "$PROFILE"; do
		[ -f "$CONFIG_DIR/$package" ] && [ ! -L "$CONFIG_DIR/$package" ] || return 1
		cp "$CONFIG_DIR/$package" "$work/config/${namespace}_$package" || return 1
	done
	# Hash contents independent of randomized staging filenames.
	context=$(for package in network wireless "$PROFILE"; do sha256sum "$work/config/${namespace}_$package" | cut -d' ' -f1; done | sha256sum | cut -d' ' -f1)
}

snapshot_unchanged() {
	local package
	for package in network wireless "$PROFILE"; do
		cmp -s "$CONFIG_DIR/$package" "$work/config/${namespace}_$package" || return 1
	done
}

check_pending() {
	local package pending
	for package in network wireless "$PROFILE"; do
		pending=$("$UCI" -q changes "$package" 2>/dev/null || true)
		[ -z "$pending" ] || return 1
	done
}

check_owner() {
	local field
	[ "$(get wireless.$OWNED)" = wifi-iface ] && [ "$(get wireless.$OWNED.xr1710g_owner)" = users ] &&
		[ "$(get wireless.$OWNED.mode)" = ap ] && [ "$(get wireless.$OWNED.network)" = "$GATE" ] || return 1
	local candidate band device_list count=0 seen=' '
	radio=''; secondary_radio=''
	device_list=$(get "wireless.$OWNED.device")
	for candidate in $device_list; do
		valid_name "$candidate" && [ "$(get "wireless.$candidate")" = wifi-device ] || return 1
		case "$seen" in *" $candidate "*) return 1 ;; esac
		seen="$seen$candidate "; count=$((count + 1))
		band=$(get "wireless.$candidate.band")
		case "$band" in
			5g) [ -z "$radio" ] || return 1; radio=$candidate ;;
			2g) [ -z "$secondary_radio" ] || return 1; secondary_radio=$candidate ;;
			*) return 1 ;;
		esac
	done
	[ -n "$radio" ] || return 1
	if [ "$(get wireless.$OWNED.mlo)" = 1 ]; then
		[ "$(get "$PROFILE.mlo.enabled")" = 1 ] && [ "$count" = 2 ] && [ -n "$secondary_radio" ] || return 1
		[ "$(get "wireless.$secondary_radio.disabled")" = 0 ] || return 1
	else
		[ "$count" = 1 ] && [ -z "$secondary_radio" ] || return 1
	fi
	[ "$(get network.$GATE)" = interface ] && [ "$(get network.$GATE.xr1710g_owner)" = users ] &&
		[ "$(get network.$GATE.proto)" = none ] && [ "$(get network.$GATE.auto)" = 0 ] || return 1
	lan_device=$(get network.lan.device)
	valid_name "$lan_device" && [ "$(get network.$GATE.device)" = "$lan_device" ] || return 1
	for field in ipaddr netmask gateway dns ip6addr ip6gw ip6assign; do
		[ -z "$(get "network.$GATE.$field")" ] || return 1
	done
	[ "$(get network.$GATE.delegate)" = 0 ] || return 1
}

check_other_bss() {
	local section type iface_device iface_disabled sections
	sections=$("$UCI" -q -X -c "$work/config" -C "$work/override" -t "$work/delta" show "${namespace}_wireless" 2>/dev/null |
		sed -n "s/^${namespace}_wireless\.\([A-Za-z0-9_][A-Za-z0-9_]*\)=wifi-iface$/\1/p")
	for section in $sections; do
		[ "$section" = "$OWNED" ] && continue
		iface_device=$(get "wireless.$section.device")
		case " $iface_device " in *" $radio "*)
			[ "$(get "wireless.$section.disabled")" = 1 ] || return 1 ;;
		esac
	done
	# Runtime may still contain the old test BSS after configurator apply (which
	# deliberately does not reload). Treat every other runtime VIF as a peer.
	wireless_json=$(ubus call network.wireless status "{\"device\":\"$radio\"}" 2>/dev/null) || return 2
	[ -n "$wireless_json" ] || return 2
	sections=$(jget "$wireless_json" '@.*.interfaces[*].section')
	for section in $sections; do [ "$section" = "$OWNED" ] || return 1; done
	if [ -n "$(jget "$wireless_json" "@.*.interfaces[@.section='$OWNED'].ifname")" ]; then bss_state=present; else bss_state=absent; fi
	[ "$(jget "$wireless_json" '@.*.pending')" != true ] || bss_state=pending
	[ -z "$secondary_radio" ] || check_mlo_secondary
}

# MLO shares2.4GHz with the explicitly generated IoT BSS. Permit that owned
# interface only, with a separate addressless network and matching private
# profile. Any third-party BSS blocks operations as in the original guard.
check_mlo_secondary() {
	local section device sections json profile_key iface_key iot_ok=0
	if [ "$(get "$PROFILE.iot.enabled")" = 1 ] && [ "$(get wireless.xr_iot.disabled)" = 0 ]; then
		[ "$(get wireless.xr_iot.xr1710g_owner)" = iot ] && [ "$(get wireless.xr_iot.mode)" = ap ] &&
			[ "$(get wireless.xr_iot.device)" = "$secondary_radio" ] && [ "$(get wireless.xr_iot.network)" = xr_iot ] &&
			[ "$(get wireless.xr_iot.encryption)" = psk2 ] && [ "$(get network.xr_iot.proto)" = none ] || return 1
		local vid field
		vid=$(get "$PROFILE.iot.vid")
		case "$vid" in ''|*[!0-9]*|0[0-9]*) return 1 ;; esac
		[ "${#vid}" -le 4 ] && [ "$vid" -ge 2 ] && [ "$vid" -le 4094 ] || return 1
		[ "$(get network.xr_iot.device)" = "br-lan.$vid" ] &&
			[ "$(get network.xr_iot.device)" != "$lan_device" ] &&
			[ "$(get network.xr_iot.delegate)" = 0 ] || return 1
		for field in ipaddr gateway dns ip6addr ip6gw ip6assign; do
			[ -z "$(get "network.xr_iot.$field")" ] || return 1
		done
		[ "$(get wireless.xr_iot.ssid)" = "$(get "$PROFILE.iot.ssid")" ] || return 1
		profile_key=$(get "$PROFILE.iot.key"); iface_key=$(get wireless.xr_iot.key)
		valid_key "$profile_key" && [ "$profile_key" = "$iface_key" ] || return 1
		iot_ok=1
	fi
	sections=$("$UCI" -q -X -c "$work/config" -C "$work/override" -t "$work/delta" show "${namespace}_wireless" 2>/dev/null |
		sed -n "s/^${namespace}_wireless\.\([A-Za-z0-9_][A-Za-z0-9_]*\)=wifi-iface$/\1/p")
	for section in $sections; do
		[ "$section" = "$OWNED" ] && continue
		device=$(get "wireless.$section.device")
		case " $device " in *" $secondary_radio "*)
			[ "$(get "wireless.$section.disabled")" = 1 ] && continue
			[ "$section" = xr_iot ] && [ "$iot_ok" = 1 ] || return 1 ;;
		esac
	done
	json=$(ubus call network.wireless status "{\"device\":\"$secondary_radio\"}" 2>/dev/null) || return 2
	for section in $(jget "$json" '@.*.interfaces[*].section'); do
		[ "$section" = "$OWNED" ] && continue
		[ "$section" = xr_iot ] && [ "$iot_ok" = 1 ] || return 1
	done
	[ "$(jget "$json" '@.*.pending')" != true ] || bss_state=pending
}

profile_eligible() {
	local profile_key iface_key
	[ "$(get "$PROFILE.users.enabled")" = 1 ] && [ "$(get wireless.$OWNED.disabled)" = 0 ] && [ "$(get "wireless.$radio.disabled")" = 0 ] || return 1
	[ "$(get "$PROFILE.users.encryption")" = sae ] && [ "$(get wireless.$OWNED.encryption)" = sae ] || return 1
	[ "$(get "$PROFILE.users.ssid")" = "$(get wireless.$OWNED.ssid)" ] && [ -n "$(get wireless.$OWNED.ssid)" ] || return 1
	profile_key=$(get "$PROFILE.users.key"); iface_key=$(get "wireless.$OWNED.key")
	valid_key "$profile_key" && [ "$profile_key" = "$iface_key" ]
}

probe_gateway() {
	local lan_json route local_addresses configured_address
	configured_address=$(get "$PROFILE.profile.management_ip")
	case "$configured_address" in
		192.168.10.3|192.168.10.4) EXPECTED_ADDRESS="$configured_address" ;;
		*) reason=management-configuration-mismatch; return 1 ;;
	esac
	[ "$(get "$PROFILE.profile.management_gateway")" = "$EXPECTED_GATEWAY" ] &&
		[ "$(get network.lan.gateway)" = "$EXPECTED_GATEWAY" ] && [ "$(get network.lan.ipaddr)" = "$EXPECTED_ADDRESS" ] &&
		[ "$(get network.lan.proto)" = static ] || { reason=management-configuration-mismatch; return 1; }
	lan_json=$(ubus call network.interface.lan status 2>/dev/null) || { reason=management-interface-unavailable; return 1; }
	[ "$(jget "$lan_json" '@.up')" = true ] || { reason=management-interface-down; return 1; }
	probe_device=$(jget "$lan_json" '@.l3_device')
	valid_name "$probe_device" && [ "$probe_device" = "$lan_device" ] || { probe_device=''; reason=management-device-mismatch; return 1; }
	local_addresses=$(ip -4 -o address show 2>/dev/null) || { reason=address-query-failed; return 1; }
	# An alias of the gateway on this AP would make ping reply locally.
	if printf '%s\n' "$local_addresses" | grep -q " inet $EXPECTED_GATEWAY/"; then reason=gateway-is-local-alias; return 1; fi
	if ! printf '%s\n' "$local_addresses" | awk -v device="$probe_device" -v address="$EXPECTED_ADDRESS" '
		$3 == "inet" {
			split($2, name, "@"); split($4, ipaddr, "/")
			if (name[1] == device && ipaddr[1] == address) found=1
		}
		END { if (!found) exit 1 }
	'; then reason=management-address-not-on-device; return 1; fi
	route=$(ip -4 route get "$EXPECTED_GATEWAY" from "$EXPECTED_ADDRESS" 2>/dev/null) || { reason=gateway-route-unavailable; return 1; }
	case " $route " in *' local '*|*' via '*) reason=gateway-route-not-direct; return 1 ;; esac
	case " $route " in *" dev $probe_device "*) ;; *) reason=gateway-route-wrong-device; return 1 ;; esac
	# Bind to the known management address; never use the debug255 or Wi-Fi77 aliases.
	if ping -4 -I "$EXPECTED_ADDRESS" -c 1 -W 1 "$EXPECTED_GATEWAY" >/dev/null 2>&1; then return 0; fi
	reason=gateway-unreachable
	return 1
}

set_gate() {
	local action="$1" response now
	[ "$action" = up ] || [ "$action" = down ] || return 1
	now=$(uptime_seconds)
	# An earlier failed opening must never delay a safety close.
	[ "$action" = down ] || [ "$now" -ge "$next_retry" ] || { reason=action-retry-backoff; return 1; }
	if ! ubus call "network.interface.$GATE" "$action" '{}' >/dev/null 2>&1; then
		next_retry=$((now + 30)); reason="$action-failed"; last_action=failed; return 1
	fi
	response=$(ubus call "network.interface.$GATE" status 2>/dev/null) || { reason=gate-status-unavailable; return 1; }
	case "$(jget "$response" '@.autostart')" in true) actual=open ;; false) actual=closed ;; *) actual=unknown ;; esac
	if { [ "$action" = up ] && [ "$actual" = open ]; } || { [ "$action" = down ] && [ "$actual" = closed ]; }; then
		last_action="$action"; transition_count=$((transition_count + 1)); next_retry=0; return 0
	fi
	next_retry=$((now + 30)); reason="$action-not-confirmed"; last_action=failed; return 1
}

tick() {
	local gate_json options_enabled configured_interval configured_recovery owner_ok=0 pending=0 peer_result
	tick_reset
	mkdir "$CHECK_LOCK" 2>/dev/null || return 75
	have_check_lock=1
	mkdir "$CONFIG_LOCK" 2>/dev/null || { reason=configurator-busy; emit_status; cleanup_tick; return 0; }
	have_config_lock=1
	if ! stage_snapshot; then reason=configuration-unavailable; emit_status; cleanup_tick; return 0; fi
	if [ "$context" = "$previous_context" ]; then
		case "$previous_success" in 0|1|2|3|4|5|6) success_streak="$previous_success" ;; esac
		case "$previous_failure" in 0|1) failure_streak="$previous_failure" ;; esac
	fi
	options_enabled=$(get "$PROFILE.uplink_guard.enabled")
	[ "$(get "$PROFILE.uplink_guard.deployed")" != 1 ] || deployed=true
	case "$options_enabled" in ''|1) ;; 0) policy_enabled=false ;; *) policy_enabled=false; reason=invalid-policy ;; esac
	configured_interval=$(get "$PROFILE.uplink_guard.interval")
	configured_recovery=$(get "$PROFILE.uplink_guard.recovery_successes")
	if [ -n "$configured_interval" ]; then small_uint "$configured_interval" 2 60 && interval="$configured_interval" || policy_enabled=false; fi
	if [ -n "$configured_recovery" ]; then small_uint "$configured_recovery" 1 6 && recovery_required="$configured_recovery" || policy_enabled=false; fi
	gate_json=$(ubus call "network.interface.$GATE" status 2>/dev/null) || { reason=gate-not-installed; emit_status; cleanup_tick; return 0; }
	case "$(jget "$gate_json" '@.autostart')" in true) actual=open ;; false) actual=closed ;; *) reason=gate-status-invalid; emit_status; cleanup_tick; return 0 ;; esac
	if ! check_owner; then reason=owned-mapping-invalid; emit_status; cleanup_tick; return 0; fi
	check_other_bss; peer_result=$?
	if [ "$peer_result" != 0 ]; then
		if [ "$peer_result" = 1 ]; then reason=other-bss-present-maintenance-required; else reason=wireless-status-unavailable; fi
		# A radio setup fallback could interrupt another BSS; never call up/down.
		emit_status; cleanup_tick; return 0
	fi
	check_pending || pending=1
	if [ -f "$HOLD" ] || [ -f "$STOP" ]; then
		reason=maintenance-hold
	elif [ "$deployed" != true ]; then
		reason=guard-not-deployed
	elif [ "$policy_enabled" != true ]; then
		reason=policy-disabled
	elif ! profile_eligible; then
		reason=users-disabled-or-key-not-provisioned
	else
		eligible=true
		if probe_gateway; then
			reachable=true; failure_streak=0
			[ "$success_streak" -ge "$recovery_required" ] || success_streak=$((success_streak + 1))
			if [ "$pending" = 1 ]; then
				success_streak=0; reason=pending-uci-edits
			elif [ "$success_streak" -ge "$recovery_required" ]; then
				desired=open; reason=gateway-reachable
			else reason=gateway-recovery-hysteresis; fi
		else success_streak=0; failure_streak=1; fi
	fi
	if [ "$eligible" != true ]; then success_streak=0; failure_streak=0; fi
	if ! snapshot_unchanged; then reason=configuration-changed-during-check; emit_status; cleanup_tick; return 0; fi
	if [ "$desired" = open ] && [ "$actual" != open ]; then set_gate up || true; fi
	if [ "$desired" = closed ] && [ "$actual" = open ]; then set_gate down || true; fi
	# netifd and hostapd application is asynchronous. autostart confirms the
	# requested gate only; bss_state is from the most recent wireless status.
	emit_status
	cleanup_tick
}

mkdir -p "$STATE_DIR" "$LOCK_DIR" || exit 1
chmod 0700 "$STATE_DIR"
trap 'cleanup_tick' EXIT
case "${1:-status}" in
	status) [ -r "$STATUS" ] && cat "$STATUS" || printf '{"schema":1,"reason":"not-started"}\n' ;;
	once) tick ;;
	hold|close) : > "$HOLD"; tick ;;
	release) rm -f "$HOLD"; tick ;;
	stop) : > "$STOP"; tick ;;
	run)
		rm -f "$STOP"
		trap ': > "$STOP"; cleanup_tick; tick; exit 0' HUP INT TERM
		while [ ! -f "$STOP" ]; do tick; sleep "$interval"; done
		;;
	*) printf 'Usage: xr1710g-ap-uplink-guard run|once|status|hold|release|stop\n' >&2; exit 2 ;;
esac
