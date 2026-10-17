from pathlib import Path
import hashlib, json
r=Path('/home/xrdev/projects/xr1710g/openwrt')
w=Path('/mnt/d/ChatGPT/XR1710G')
p=r/'package/network/config/xr1710g-ap-configurator'
out=w/'development/ap25';out.mkdir(exist_ok=True)
f=p/'files/xr1710g-ap-uplink-guard';old=f.read_text()
assert not (out/'guard-before.sh').exists()
(out/'guard-before.sh').write_text(old)
s=old
def replace(a,b):
 global s
 assert s.count(a)==1,a
 s=s.replace(a,b)
replace('\\"failure_streak\\":$failure_streak,', '\\"failure_streak\\":$failure_streak,\\"failure_threshold\\":$failure_required,\\"recovery_successes\\":$recovery_required,')
replace('interval=5; recovery_required=3;', 'interval=5; recovery_required=3; failure_required=3;')
replace('configured_recovery owner_ok=0', 'configured_recovery configured_failure owner_ok=0')
replace('case "$previous_failure" in 0|1)', 'case "$previous_failure" in 0|1|2|3|4|5|6)')
replace('configured_recovery=$(get "$PROFILE.uplink_guard.recovery_successes")', 'configured_recovery=$(get "$PROFILE.uplink_guard.recovery_successes")\n\tconfigured_failure=$(get "$PROFILE.uplink_guard.failure_threshold")')
replace('\tgate_json=$(ubus call', '\tif [ -n "$configured_failure" ]; then small_uint "$configured_failure" 1 6 && failure_required="$configured_failure" || policy_enabled=false; fi\n\t[ "$failure_streak" -le "$failure_required" ] || failure_streak="$failure_required"\n\tgate_json=$(ubus call')
replace('elif [ "$success_streak" -ge "$recovery_required" ]; then', '''# A gate that survived a transient miss must not be closed by
			# its first successful retry. Closed/new-context gates still
			# require the full recovery streak before opening.
			elif { [ "$actual" = open ] && [ "$context" = "$previous_context" ]; } ||
				[ "$success_streak" -ge "$recovery_required" ]; then''')
replace('\t\telse success_streak=0; failure_streak=1; fi', '''		else
			success_streak=0
			if [ "$reason" = gateway-unreachable ]; then
				[ "$failure_streak" -ge "$failure_required" ] || failure_streak=$((failure_streak + 1))
				# Only an isolated reachability failure may be tolerated.
				# Invalid management state, a changed profile, pending edits
				# and explicit holds must never inherit an open gate.
				if [ "$pending" = 1 ]; then reason=pending-uci-edits
				elif [ "$actual" = open ] && [ "$context" = "$previous_context" ] &&
					[ "$failure_streak" -lt "$failure_required" ]; then
					desired=open; reason=gateway-failure-hysteresis
				fi
			else failure_streak=0; fi
		fi''')
f.write_text(s)
f=p/'files/xr1710g_ap_configurator';s=f.read_text();assert "option failure_threshold" not in s
f.write_text(s.replace("\toption recovery_successes '3'", "\toption recovery_successes '3'\n\t# Consecutive ICMP misses before closing an already-open users BSS.\n\toption failure_threshold '3'"))
f=p/'Makefile';s=f.read_text();assert 'PKG_RELEASE:=9\n' in s;f.write_text(s.replace('PKG_RELEASE:=9\n','PKG_RELEASE:=10\n'))
print(json.dumps({'beforeSHA256':hashlib.sha256(old.encode()).hexdigest(),'guardChanged':True,'packageRelease':10}))
