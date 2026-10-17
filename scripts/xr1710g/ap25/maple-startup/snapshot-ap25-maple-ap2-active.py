"""Read-only supplement to the submitted AP2 epoch; never activates or reboots."""
import json
from xr_two_ap import WORKSPACE as w,connect,command
out=w/'development/ap25/maple-ap2-epoch1';expected=json.loads((out/'activation-observed.json').read_text())['bootID']
c=connect(2,via='lan')
try:
 before=command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip();assert before==expected
 data=command(c,'dmesg')[0];snapshot=command(c,'cat /sys/kernel/debug/xr_maple_observer')[0].decode().strip()
 after=command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip();assert after==before
 (out/'activation-kernel.txt').write_bytes(data)
 (out/'observer-live.json').write_text(json.dumps({'bootID':before,'snapshot':snapshot,'passiveReadyLogged':b'XR_MAPLE_OBSERVER ready exact_site=d4 passive=1' in data},indent=2)+'\n')
 print(json.dumps({'bootID':before,'observerSnapshot':snapshot}))
finally:c.close()
