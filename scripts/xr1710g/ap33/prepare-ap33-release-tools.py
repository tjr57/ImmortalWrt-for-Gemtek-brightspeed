"""Derive AP33 tools; does not build or touch devices. One-shot file generation."""
from pathlib import Path
p=Path(__file__).parent
def write(n,s):
 q=p/n;assert not q.exists(),n;q.write_text(s,encoding='utf-8',newline='\n')
def sub(s,a,b):
 assert a in s,a;return s.replace(a,b)
s=(p/'check-ap32-build.py').read_text().replace('ap32','ap33').replace('AP32','AP33')
s=sub(s,"oldversion = '20261011-ap31-d331711d'","oldversion = '20261011-ap32-d331711d'")
s=s.replace("candidate = out / 'packet-fence'","candidate = out / 'bridge-policy'").replace('bridge-transaction/vm-result.json','bridge-policy/vm-result.json')
s=s.replace('82d648081434651041cfbc01a607e229223ae65dd4afaa6bd498b1042dcc8932','a0e137d15c07b5b288f19529e6361a3dbc77ac8889496b619f3512b9d78dcbfd')
s=s.replace('development/ap31/packed-files-qa.json','development/ap32/packed-files-qa.json').replace('DT identical to AP31','DT identical to AP32')
s=s.replace('Actual FDB/STP change ordering, balanced guards and active-writer registration in isolated Linux VM; exact PPE epoch functions native/ARM;', 'Actual VLAN/port policy ordering, per-VLAN forwarding and switchdev failure rollback in isolated Linux VM; exact PPE context/packet functions native/ARM;')
write('check-ap33-build.py',s)
s=(p/'ap32-deploy.py').read_text().replace('ap32','ap33').replace('AP32','AP33')
s=s.replace("BASELINE='20261011-ap31-d331711d'","BASELINE='20261011-ap32-d331711d'")
s=s.replace('packet-fence/qa.json','bridge-policy/qa.json').replace('bridge-transaction/vm-result.json','bridge-policy/vm-result.json')
write('ap33-deploy.py',s)
s=(p/'ap32-postflight.py').read_text().replace('ap32','ap33').replace('AP32','AP33')
write('ap33-postflight.py',s)
s=(p/'ap32-preflight.py').read_text().replace('before AP32','before AP33').replace('current AP31','current AP32').replace('20261011-ap31-d331711d','20261011-ap32-d331711d').replace('development/ap32','development/ap33')
write('ap33-preflight.py',s)
print('AP33 release tools generated; no device or build action')
