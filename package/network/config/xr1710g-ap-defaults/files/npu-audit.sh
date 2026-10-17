#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Early boot helper. The request is consumed durably before module loading.
audit_prefix=${XR_NPU_AUDIT_ROOT:-/}
case "$audit_prefix" in /*) ;; *) return 1 ;; esac
audit_prefix=${audit_prefix%/}
audit_marker="$audit_prefix/etc/xr1710g-npu-audit.once"
audit_module="$audit_prefix/etc/modules.d/00-xr1710g-npu-audit"
audit_state="$audit_prefix/tmp/xr1710g-npu-audit.state"
audit_signature='# xr1710g single-boot NPU audit'
audit_expected="$audit_signature
mt76 npu_enable=1 npu_rx_audit=1"

audit_board_ok() {
    [ "$(cat "$audit_prefix/tmp/sysinfo/board_name" 2>/dev/null)" = gemtek,xr1710g ] || return 1
    [ -n "$audit_prefix" ] || [ "$(id -u)" = 0 ]
}

audit_record() {
    mkdir -p "$audit_prefix/tmp" || return 1
    printf '%s\n' "$1" > "$audit_state"
}

audit_module_owned() {
    [ -f "$audit_module" ] && [ ! -L "$audit_module" ] &&
        [ "$(cat "$audit_module")" = "$audit_expected" ]
}

audit_clear_module() {
    if [ -e "$audit_module" ] || [ -L "$audit_module" ]; then
        audit_module_owned || return 1
        rm -f "$audit_module" || return 1
    fi
}

audit_bool() {
    case "$(cat "$1" 2>/dev/null)" in
        1|Y|y) printf true ;;
        0|N|n) printf false ;;
        *) printf null ;;
    esac
}

audit_status() {
    local pending=false state=unavailable
    [ ! -f "$audit_marker" ] || pending=true
    [ ! -r "$audit_state" ] || state=$(cat "$audit_state")
    case "$state" in normal|armed-for-module-load|driver-already-loaded|ppe-not-disabled|invalid-request|module-config-conflict) ;;
        *) state=unavailable ;;
    esac
    printf '{"pending":%s,"state":"%s","wlan_npu_boot_parameter":%s,"descriptor_audit_parameter":%s,"ppe_bind_parameter":%s}\n' \
        "$pending" "$state" \
        "$(audit_bool "$audit_prefix/sys/module/mt76/parameters/npu_enable")" \
        "$(audit_bool "$audit_prefix/sys/module/mt76/parameters/npu_rx_audit")" \
        "$(audit_bool "$audit_prefix/sys/module/airoha_eth/parameters/ppe_bind_enable")"
}

audit_arm() {
    audit_board_ok || return 1
    [ ! -e "$audit_marker" ] && [ ! -L "$audit_marker" ] || return 1
    [ "$(audit_bool "$audit_prefix/sys/module/airoha_eth/parameters/ppe_bind_enable")" = false ] || return 1
    [ "$(audit_bool "$audit_prefix/sys/module/mt76/parameters/npu_enable")" = false ] || return 1
    [ "$(audit_bool "$audit_prefix/sys/module/mt76/parameters/npu_rx_audit")" = false ] || return 1
    if [ -e "$audit_module" ] || [ -L "$audit_module" ]; then
        audit_module_owned || return 1
    fi
    ( umask 077; printf 'xr1710g-npu-audit-v1\n' > "$audit_marker.tmp" ) || return 1
    mv "$audit_marker.tmp" "$audit_marker" || return 1
    sync
    printf 'Single-boot NPU audit armed. Runtime policy is unchanged until reboot.\n'
}

audit_disarm() {
    audit_board_ok || return 1
    audit_clear_module || return 1
    rm -f "$audit_marker"
    sync
    printf 'NPU audit request cleared. Current loaded module parameters are unchanged.\n'
}

audit_boot() {
    audit_board_ok || return 1
    if ! audit_clear_module; then
        audit_record module-config-conflict
        return 1
    fi
    if [ ! -e "$audit_marker" ] && [ ! -L "$audit_marker" ]; then
        audit_record normal
        return 0
    fi
    if [ ! -f "$audit_marker" ] || [ -L "$audit_marker" ] ||
       [ "$(cat "$audit_marker")" != xr1710g-npu-audit-v1 ]; then
        audit_record invalid-request
        return 1
    fi
    # If this boot fails later, no persistent request can arm the next boot.
    rm -f "$audit_marker" || return 1
    sync
    if [ -d "$audit_prefix/sys/module/mt76" ]; then
        audit_record driver-already-loaded
        return 1
    fi
    if [ "$(audit_bool "$audit_prefix/sys/module/airoha_eth/parameters/ppe_bind_enable")" != false ]; then
        audit_record ppe-not-disabled
        return 1
    fi
    mkdir -p "$audit_prefix/etc/modules.d" || return 1
    ( umask 077; printf '%s\n' "$audit_expected" > "$audit_module.tmp" ) || return 1
    mv "$audit_module.tmp" "$audit_module" || return 1
    audit_record armed-for-module-load
}
