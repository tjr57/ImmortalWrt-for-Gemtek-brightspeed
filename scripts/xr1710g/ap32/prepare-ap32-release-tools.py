"""Derive reviewed AP32 checks from the finalized AP31 release workflow."""
from pathlib import Path
p=Path(__file__).parent
def write(name,text):
 q=p/name;assert not q.exists(),name;q.write_text(text,encoding='utf-8',newline='\n')
def sub(s,a,b):
 assert a in s,a;return s.replace(a,b)
s=(p/'check-ap31-build.py').read_text()
s=s.replace('ap31','ap32').replace('AP31','AP32')
s=sub(s,"oldversion = '20261010-ap30-d331711d'","oldversion = '20261011-ap31-d331711d'")
s=sub(s,"candidate = out / 'ppe-context'","candidate = out / 'packet-fence'")
s=sub(s,"for p in ['drivers/net/ethernet/airoha/airoha_ppe.c', 'drivers/net/ethernet/airoha/airoha_eth.h', 'net/bridge/br_fdb.c', 'include/linux/if_bridge.h']:","for p in json.loads((candidate / 'prepared.json').read_text())['sources']:")
s=s.replace('publisher/vm-result.json','bridge-transaction/vm-result.json')
s=sub(s,'904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0','82d648081434651041cfbc01a607e229223ae65dd4afaa6bd498b1042dcc8932')
s=sub(s,"additions = {'tc-tiny', 'kmod-sched-core', 'kmod-sched-flower', 'kmod-sched-act-vlan'}","additions = set()")
s=sub(s,"w / 'development/ap30/packed-files-qa.json'","w / 'development/ap31/packed-files-qa.json'")
s=s.replace('DT identical to AP30','DT identical to AP31')
s=s.replace('Full rootfs delta limited to kernel modules, TC tools/autoload and metadata','Full rootfs delta limited to kernel modules and version/package metadata')
s=s.replace('Actual bridge API/port predicate and TC/VLAN actions in isolated Linux VM; AP ARM objects and linked image/ABI; hardware boot still requires AP2 first.',
 'Actual FDB/STP change ordering, balanced guards and active-writer registration in isolated Linux VM; exact PPE epoch functions native/ARM; AP ARM objects and linked image/ABI; hardware boot still requires AP2 first.')
s=sub(s,'metadata | tools or p.startswith','metadata or p.startswith')
write('check-ap32-build.py',s)
s=(p/'ap31-deploy.py').read_text().replace('ap31','ap32').replace('AP31','AP32')
s=sub(s,"BASELINE='20261010-ap30-d331711d'","BASELINE='20261011-ap31-d331711d'")
s=s.replace('ppe-context/qa.json','packet-fence/qa.json').replace('publisher/vm-result.json','bridge-transaction/vm-result.json')
s=sub(s," assert read(c,'test -d /sys/module/cls_flower -a -d /sys/module/act_vlan && echo ready')=='ready'", """ assert read(c,'test -d /sys/module/cls_flower -a -d /sys/module/act_vlan && echo ready')=='ready'
 writer_reads=[]
 for _ in range(10):
  value=int(read(c,'cat /sys/kernel/debug/ppe/xr_l2_bridge_writers'));writer_reads.append(value)
  if value==0:break
  time.sleep(0.1)
 assert writer_reads[-1]==0,writer_reads
 assert int(read(c,'cat /sys/kernel/debug/ppe/xr_l2_generation'))>0""")
write('ap32-deploy.py',s)
s=(p/'ap31-postflight.py').read_text().replace('ap31','ap32').replace('AP31','AP32')
write('ap32-postflight.py',s)
s=(p/'ap31-preflight.py').read_text().replace('before AP31','before AP32').replace('current AP30','current AP31').replace('20261010-ap30-d331711d','20261011-ap31-d331711d').replace('development/ap31','development/ap32')
write('ap32-preflight.py',s)
print('AP32 check/deploy/preflight/postflight tools generated; no build/device action')
