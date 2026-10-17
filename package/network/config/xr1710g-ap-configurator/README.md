# XR1710G two-AP configurator

This optional package applies either authorized AP plan: management
`192.168.10.3/24` (AP1) or `192.168.10.4/24` (AP2), gateway/DNS `192.168.10.1`, country `AU`, all four
`lan2 lan3 lan4 wan` ports in the AP bridge, no local DHCP/DNS/RA service.
The default 5 GHz SSID is `Tizer` with SAE, and 2.4 GHz is `Poro` with WPA2.

The 5 GHz users radio uses EHT160 in AU. Set `users.channel` to a primary
in the lower36-64 block (default36); profile application preserves the selected
channel instead of returning to ACS. The bonded160 block includes DFS
subchannels52-64 and therefore requires radar checks. The current production
survey selected primary44; no fixed channel promises future zero interference.

6 GHz remains disabled by default. An explicit runtime mesh profile can
enable a 6 GHz SAE/802.11s backhaul. Both units have passed authenticated
160MHz peering and real VLAN1/VLAN50 forwarding on the AP11 runtime hotfix.

Runtime passphrases are absent from the source profile and installed image.
Read them via stdin, which keeps them out of process arguments and plan output:

```sh
xr1710g-ap-configure key users
xr1710g-ap-configure key iot
xr1710g-ap-configure plan
xr1710g-ap-configure validate
xr1710g-ap-configure apply
```

`key` hides terminal echo. A script can supply one passphrase line on stdin.
The runtime profile is mode `0600` and survives sysupgrade as a conffile. Normal
OpenWrt configuration backups therefore contain private keys and need to be
handled as private data. The package never contacts or alters the main router.

Set `users.vid`, `iot.vid` and `profile.uplink_port` in
`/etc/config/xr1710g_ap_configurator`, then commit that package before `apply`.
Leave `users.vid` empty for native/untagged users and management. No IoT VID
is assigned by this package. With an empty IoT VID, the IoT interface and
2.4 GHz radio remain disabled, and its key is not required. This prevents
silently putting IoT devices on the user LAN before a trunk is agreed.

Without VLANs, the management device is `br-lan`. With any explicit VLAN,
`br-lan` enables VLAN filtering. Each users access port is untagged with its
PVID; explicit users VLANs are tagged on the configured uplink ports. Native
users remain untagged on those uplinks, using internal bridge PVID 1.
Consequently, VID 1 cannot be assigned to IoT in native users mode. This is
an internal Linux bridge detail, not an assigned trunk VLAN on the main router.
IoT is tagged only on the explicitly configured uplink ports, has no IP address
on this AP, and never joins the users network. Its VID must differ from users.

The interfaces refer to `br-lan.VID`; Wi-Fi interfaces refer to the corresponding
logical networks. The shipped netifd `vlan.c::__vlan_hotplug_op()` passes a
`VID:u` membership when attaching a dynamic Wi-Fi port to that VLAN device,
and `bridge.c` installs the membership on its parent bridge. No transient
`wlan*` names are stored in bridge-vlan ports. The radio is identified by
its `band` property, so reordered `radio0`/`radio1`/`radio2` names are safe.
Exactly one 2g, 5g and 6g device is required; ambiguous/missing bands fail.

All normal validation and generation uses a private UCI directory under `/tmp`
and randomly named temporary UCI packages, so the CLI's inherited global delta
search path cannot merge an unrelated pending edit into the staged plan.
`plan` and `validate` do not change live UCI files. `apply` validates the complete
set, rejects existing pending UCI edits and concurrent file changes, then uses
same-filesystem renames to replace `network`, `wireless` and `dhcp`. Synchronous
errors/signals restore the previous files and retain the private recovery copy.
Three UCI files cannot be replaced atomically across sudden power loss or
SIGKILL; keep stable power during `apply`. No reload/restart is performed, so
the running network and radios do not change until the operator activates them.
Existing Wi-Fi interfaces on the three managed radios are disabled before the
owned interfaces are defined. Unmanaged interfaces on `br-lan` cause rejection
to avoid silently replacing another VLAN plan. No firewall offload policy is
modified.

Validation uses actual built ARM UCI through QEMU with a copied runtime and
independent fixtures. It tests VLAN membership, band reordering, secret quoting,
disabled IoT without a VID, server shutdown, invalid input and rollback after
an injected replacement failure. It does not claim radio or forwarding hardware
validation:

```sh
python3 package/network/config/xr1710g-ap-configurator/tests/test-configurator.py \
  --runtime-root staging_dir/target-aarch64_cortex-a53_musl/root-airoha
```

The `XR1710G_CONFIG_DIR`, `XR1710G_UCI`, `XR1710G_TMP_DIR` and
`XR1710G_LOCK_DIR` overrides support independent fixtures. Production apply/key
requires root and `/tmp/sysinfo/board_name=gemtek,xr1710g`.

## Two-AP 6 GHz mesh deployment

`mesh.enabled=1` enables generation of an SAE/PMF-required mesh interface on
AU PSC channel 37, with `HE80` or `HE160`. Supply its 8–63 byte passphrase at
runtime with `xr1710g-ap-configure key mesh`; no default key is shipped or printed.
Run `plan`/`validate` before `apply`. Old profiles without a mesh section keep
6 GHz disabled. Installation, upgrade and `apply` never reload the radio.

The stable interface name `mesh6g` joins the **parent** `br-lan` through the
addressless `xr_mesh_backhaul` network. When VLAN filtering is configured,
native users use `mesh6g:u*`, explicit user VLANs use `mesh6g:t`, and the IoT
VLAN also uses `mesh6g:t`. This prepares both VLANs for carriage over the same
backhaul instead of attaching the mesh only to the users' VLAN device. Bridge
STP is enabled when preparing mesh. The main router's physical trunk must carry
the same VLANs on the chosen `profile.uplink_port`; no trunk IDs are invented.

AP2 uses `profile.management_ip=192.168.10.4`. Its `profile.uplink_port`
is empty: all physical ports remain native users/management ports, and only
`mesh6g` carries tagged IoT VLAN50. Empty physical uplinks require explicitly
enabled mesh; VLAN mode without either uplink is rejected. The users uplink
guard reads the validated .3/.4 profile address and binds its gateway probe to
that unit's management address.

Actual AP11 runtime validation: SAE/PMF mesh37/160, bidirectional management,
AP2 gateway access, temporary AP2 VLAN50 client DHCP/DNS through the mesh,
backhaul-loss direct wired SSH survival and users-gate closure, then AP2 reboot
and automatic rejoin. The shared image still defaults to AP1 .3 after factory
reset; .4 and runtime private keys are persistent operator configuration.
This is not phone-roaming, sustained throughput, full loop or offload acceptance.
WLAN NPU/PPE policies remain off. Evidence:
`D:/ChatGPT/XR1710G/development/ap2-bringup/ap11-mesh/final-result.json`.
The current source is release5; the deployed AP11 package database/image remain
unchanged, with helper/guard overlay hotfixes. Any new full image must be AP12.

## AP12 factory role defaults and current release

AP12 is installed on both current units. The defaults package reads the
factory UBI nvmem LAN MAC at0x6000; current AP1/AP2 use .3/.4 and corresponding
hostnames even after normal factory reinitialization. Runtime MAC overrides
are ignored. Unknown or unavailable identity uses a DHCP management client
with radios off. Read-only `xr1710g-ap-role` explains the detected hardware
default; it does not change the running operator configuration.

Factory/reset starts without private wireless keys, users/IoT/mesh inactive.
Normal keep-config sysupgrade preserves .3/.4, private PSKs, VLANs and other
operator settings; initialized markers prevent default reapplication. The
reset behavior was tested with shippedARM UCI in fixtures and real read-only
identity, not by resetting live APs. Early failsafe preinit is still10.3.

AP12 actual normal upgrades, bothSSID/mesh restoration, VLAN50 DHCP/DNS and
four AX211 Tizer/Poro BSSID-authorized client/DNS/internet/limited-isolation
cases passed. Core runtime hashes match the image; packageDB defaults6 and
configurator5 replace earlier overlay hotfix status. Phone roaming, full
VLAN policy matrix, long stress and acceleration remain independent tests.
Future deployment order is AP2, accept its return, then AP1. New builds need
AP13 rather than overwriting the frozen AP12 archive.

## AP14 candidate

Puncturing adds `mode=manual|auto`. Auto requires bitmap0 and rejects MLO;
manual keeps primary-subchannel/pattern checks. Driver boot opt-in remains off.
The Chinese feature page has typed preview/apply/volatile rollback. It publishes
only feature-related wireless/profile fields: underlying network/DHCP bytes and
non-feature wireless fields are retained. FT rejects a runtime/profile key
mismatch; puncturing requires actual EHT160 with the profile primary channel.
MLO changes users device-list and the necessary2GHz EHT mode only, retaining
IoT identity and dedicated6GHz mesh. Neither preview nor the page reboots or
enables NPU/PPE. Rollback refuses an externally modified configuration.
AP14 compiled/isolated tests do not qualify RF effects or acceleration.
