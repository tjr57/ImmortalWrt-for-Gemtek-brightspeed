from pathlib import Path
import importlib.util,json
from xr_two_ap import connect,command,WORKSPACE as w
s=importlib.util.spec_from_file_location('a',Path(__file__).with_name('ap22-upgrade-common.py'));a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
version='20261010-ap24-d331711d';a.base.VERSION=version;a.base.connect=lambda u,**kw:connect(u,via='lan')
out=w/'development/ap25';result={}
for unit in (2,1):
 c=connect(unit,via='lan')
 try:
  data=command(c,'cat /proc/sys/kernel/random/boot_id; /usr/sbin/xr1710g-ap-uplink-guard status')[0].decode().splitlines()
  guard=json.loads(data[1]);health=a.health(unit,version)
  result[str(unit)]={'bootID':data[0],'guard':guard,'health':health}
  print(json.dumps({'unit':unit,'healthy':health['healthy'],'guardReason':guard['reason'],'transitions':guard['transition_count']}),flush=True)
 finally:c.close()
(out/'live-before.json').write_text(json.dumps(result,indent=2)+'\n')
