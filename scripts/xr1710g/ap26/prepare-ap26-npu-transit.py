"""Reuse qualified activation/recovery with a new PC-to-AP2 transit workload."""
from pathlib import Path
import ast,hashlib,json
w=Path('D:/ChatGPT/XR1710G');dest=w/'environment/run-ap26-npu-transit-ap1.py';assert not dest.exists()
old=(w/'environment/run-ap25-maple-ap1-load1.py').read_text()
s=old.replace('"""AP25 AP1 passive Maple observer with two 20-second unpaced four-stream TCP transfers."""',
              '"""AP26 real wired-to-Mesh transit through AP1 NPU; qualified one-boot recovery unchanged."""')
s=s.replace("VERSION='20261010-ap25-d331711d'", "VERSION='20261010-ap26-d331711d'")
s=s.replace("out=WORKSPACE/'development/ap25/maple-ap1-load1'", "out=WORKSPACE/'development/ap26/npu-wired-mesh-ap1'")
s=s.replace('import json,hashlib,importlib.util,re,time,threading,shlex,sys','import json,hashlib,importlib.util,re,time,threading,shlex,sys,subprocess')
assert "assert json.loads((WORKSPACE/'development/ap25/deployment/final-result.json').read_text())['passed']" in s
s=s.replace("assert json.loads((WORKSPACE/'development/ap25/deployment/final-result.json').read_text())['passed']", "assert json.loads((WORKSPACE/'development/ap26/deployment/final-result.json').read_text())['passed']")
s=s.replace("'plannedTraffic':'Two20secondTCPdirections,4streams,unpaced,AP2clientAP1server'", "'plannedTraffic':'PC.101 to AP2.4 through AP1 lan2+mesh6g; two20secondTCPdirections,4streams,unpaced'")
s=s.replace("row={'version':board['release']['version']", "row={'interfaceCounters':read(c,'cat /proc/net/dev'),'version':board['release']['version']")
s=s.replace("server='/tmp/xr-ap25-maple-load-'", "server='/tmp/xr-ap26-transit-'")
start=s.index('    c1=connect(1)\n',s.index("server='/tmp/xr-ap26-transit-'"))
end=s.index('    after=snapshot(diag);',start)
s=s[:start]+'''    c1=connect(2)
    try:
     sockets=read(c1,'cat /proc/net/tcp /proc/net/tcp6').upper()
     assert not re.search(r':14C7\\s+\\S+\\s+0A\\s',sockets),'Test port is already listening'
     assert absent(c1,server) and absent(c1,exitfile)
     owned_server_paths.extend([server,exitfile]);save('server-files.json',owned_server_paths)
     command(c1,"sh -c 'timeout 30 iperf3 -s -1 -B 192.168.10.4 -p 5319 -J >"+server+" 2>&1; printf \\"%s\\\\n\\" \\"$?\\" >"+exitfile+"' </dev/null >/dev/null 2>&1 &")
    finally:c1.close()
    time.sleep(.5)
    cli=subprocess.run([str(pc_iperf),'-c','192.168.10.4','-B','192.168.10.101','-p','5319','-t','20','-P','4','-J','--connect-timeout','4000']+(['-R'] if reverse else []),capture_output=True,timeout=30)
    data,error,client_code=cli.stdout,cli.stderr,cli.returncode
    (out/('client-'+str(index)+'.json')).write_bytes(data);(out/('client-'+str(index)+'.stderr')).write_bytes(error)
    client_document=json.loads(data)
    assert all(row['local_host']=='192.168.10.101' and row['remote_host']=='192.168.10.4' for row in client_document['start']['connected'])
    c1=connect(2)
    try:
     for attempt in range(10):
      if not absent(c1,exitfile):break
      time.sleep(.2)
     server_data=command(c1,'cat '+server)[0];server_code=int(read(c1,'cat '+exitfile));(out/('server-'+str(index)+'.json')).write_bytes(server_data)
     command(c1,'rm '+server+' '+exitfile)
    finally:c1.close()
''' + s[end:]
anchor="assert len(sys.argv)==2 and sys.argv[1]=='run' and not operation.exists(),'Inspect one-shot journal; do not restart this epoch'"
assert anchor in s
s=s.replace(anchor,anchor+'''
pc_iperf=WORKSPACE/'development/tools/msys2-iperf3/bin/iperf3.exe'
provenance=json.loads((pc_iperf.parent.parent/'provenance.json').read_text())
assert provenance['package_signatures_verified']
for item in provenance['extracted_files']:assert sha(pc_iperf.parent/item['name'])==item['sha256']
assert json.loads((WORKSPACE/'development/ap25/ppe-transit/software-baseline1/path-analysis.json').read_text())['passed']
route=subprocess.run(['powershell','-NoProfile','-Command','Find-NetRoute -RemoteIPAddress 192.168.10.4 | Select-Object InterfaceIndex,IPAddress,NextHop | ConvertTo-Json -Compress'],capture_output=True,text=True,check=True)
routes=json.loads(route.stdout)
assert all(row['InterfaceIndex']==22 for row in routes) and any(row['IPAddress']=='192.168.10.101' for row in routes)
save('pc-route.json',routes)
''')
s=s.replace('active_samples=[];last_sample=0','active_samples=[];last_sample=0\nowned_server_paths=[]')
anchor="try:assert boot(c)==ap2_before['bootID'] and a.preservation(c)==ap2_before['preservation'] and all(v=='N' for v in params(c).values())"
assert anchor in s
s=s.replace(anchor,"""try:
 assert boot(c)==ap2_before['bootID'] and a.preservation(c)==ap2_before['preservation'] and all(v=='N' for v in params(c).values())
 for path in owned_server_paths:
  assert re.fullmatch('/tmp/xr-ap26-transit-[0-9a-f]{8}-[01]\\\\.json(?:\\\\.exit)?',path)
  if not absent(c,path):command(c,'rm -- '+shlex.quote(path))
 assert all(absent(c,path) for path in owned_server_paths)""")
ast.parse(s);dest.write_text(s)
print(json.dumps({'created':str(dest),'activationRecoveryModulesUnchanged':True,'targetNpu':'AP1 forwarding path','PCNetworkChanged':False,'oneShotOutput':'development/ap26/npu-wired-mesh-ap1'}))
