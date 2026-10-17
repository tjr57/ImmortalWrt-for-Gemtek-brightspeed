from xr_two_ap import connect,command,WORKSPACE as w
import json
out=w/'development/ap24/npu-ap1-load1';data={}
for unit in (1,2):
 c=connect(unit,via='lan')
 try:
  raw,err,code=command(c,'ping -I br-lan.1 -i 0.2 -c 5 -W 1 192.168.10.'+('4' if unit==1 else '3'),timeout=10,check=False)
  data[str(unit)]={'code':code,'stdout':raw.decode(),'stderr':err.decode(),'bootID':command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip()}
 finally:c.close()
(out/'probe-parser-inspection.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data))
