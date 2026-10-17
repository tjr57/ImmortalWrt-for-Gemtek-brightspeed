from xr_two_ap import WORKSPACE,connect,command
import json
c=connect(1,via='lan')
try:
 commands={'bridgeSysctls':'for p in /proc/sys/net/bridge/bridge-nf-*; do printf "%s=" "$p"; cat "$p"; done',
           'bridgeTable':'nft list table bridge fw4','ppePolicy':'cat /sys/kernel/debug/ppe/xr_l2_policy_latched',
           'portState':'bridge link show','cmdline':'cat /proc/cmdline'}
 result={}
 for key,cmd in commands.items():
  data,error,code=command(c,cmd,check=False);result[key]={'stdout':data.decode(),'stderr':error.decode(),'exit':code}
 (WORKSPACE/'development/ap26/bridge-live-context.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({key:result[key] for key in ['bridgeSysctls','bridgeTable','ppePolicy']}))
finally:c.close()
