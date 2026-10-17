from xr_two_ap import connect,command
import json
c=connect(2,via='lan')
try:
 out,err,code=command(c,'for d in lan2 lan3 lan4 wan; do printf "%s=" "$d"; cat /sys/class/net/$d/carrier || exit 1; done',check=False)
 print(json.dumps({'unit':2,'carrierReadCode':code,'carriers':out.decode(),'stderr':err.decode()}))
 assert code==0 and set(out.splitlines())=={x+b'=0' for x in (b'lan2',b'lan3',b'lan4',b'wan')}
 for cmd in ('iperf3 --version','command -v timeout'):
  out,err,code=command(c,cmd,check=False);assert code==0;print(out.decode().splitlines()[0])
finally:c.close()
