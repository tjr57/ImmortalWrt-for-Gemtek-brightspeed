#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read original factory identity only. No writes to NAND, calibration or MACs.
xr1710g_detect_ap_role() {
 local name_file volume count mac
 ap_role=unassigned
 ap_address=''
 ap_hostname=XR1710G-Unassigned
 ap_uplink=''
 ap_identity_state=factory-unavailable
 ap_factory_mac=''
 volume=''; count=0
 for name_file in /sys/class/ubi/ubi[0-9]*_[0-9]*/name; do
  [ -r "$name_file" ] || continue
  [ "$(cat "$name_file")" = factory ] || continue
  volume=${name_file%/name}; volume=${volume##*/}
  count=$((count + 1))
 done
 [ "$count" = 1 ] || {
  [ "$count" = 0 ] || ap_identity_state=ambiguous-factory
  return 0
 }
 # DTS nvmem cell lan_mac: factory offset0x6000,length6. Never read br-lan
 # or the operator's current NIC MAC, which can change after bridge reload.
 if [ -r "/sys/bus/nvmem/devices/$volume/nvmem" ]; then
  mac=$(dd if="/sys/bus/nvmem/devices/$volume/nvmem" bs=1 skip=24576 count=6 2>/dev/null | hexdump -v -e '6/1 "%02x"')
 elif [ -c "/dev/$volume" ]; then
  mac=$(dd if="/dev/$volume" bs=1 skip=24576 count=6 2>/dev/null | hexdump -v -e '6/1 "%02x"')
 else
  return 0
 fi
 [ "${#mac}" = 12 ] || { ap_identity_state=invalid-factory-mac; return 0; }
 case "$mac" in *[!0-9a-f]*) ap_identity_state=invalid-factory-mac; return 0 ;; esac
 ap_factory_mac=$mac
 case "$mac" in
  005828d78509)
   ap_role=ap1; ap_address=192.168.10.3; ap_hostname=XR1710G-AP1; ap_uplink=lan2 ;;
  005828d749f2)
   ap_role=ap2; ap_address=192.168.10.4; ap_hostname=XR1710G-AP2 ;;
  *) ap_identity_state=unknown-factory-mac; return 0 ;;
 esac
 ap_identity_state=recognized
}
