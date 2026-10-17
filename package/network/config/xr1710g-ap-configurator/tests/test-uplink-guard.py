#!/usr/bin/env python3
"""Execute the complete guard with real ARM UCI/jsonfilter and isolated I/O.

No host/device networking. Only ubus, ip, ping and logging are fixtures.
"""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

def main():
 a=argparse.ArgumentParser();a.add_argument('--program',type=Path);a.add_argument('--report',type=Path,required=True);a.add_argument('--runtime-root',type=Path);args=a.parse_args()
 repo=Path('/home/xrdev/projects/xr1710g/openwrt')
 program=args.program or repo/'package/network/config/xr1710g-ap-configurator/files/xr1710g-ap-uplink-guard'
 runtime=args.runtime_root or repo/'build_dir/target-aarch64_cortex-a53_musl/root-airoha'
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 cases=[];ticks=0
 with tempfile.TemporaryDirectory(prefix='xr-guard-qa-') as tmp:
  root=Path(tmp);rt=root/'runtime';shutil.copytree(runtime,rt,symlinks=True)
  conf=root/'config';conf.mkdir();state=root/'state';state.mkdir();lock=root/'lock';lock.mkdir();delta=root/'delta';delta.mkdir();bins=root/'bin';bins.mkdir()
  for name,path in [('uci','sbin/uci'),('jsonfilter','usr/bin/jsonfilter')]:
   wrapper=bins/name
   extra=f' -c "{conf}" -t "{delta}"' if name=='uci' else ''
   wrapper.write_text(f'#!/bin/sh\nexec /usr/bin/qemu-aarch64 -L "{rt}" "{rt/path}"{extra} "$@"\n');wrapper.chmod(0o755)
  stub=bins/'fixture'
  stub.write_text('''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
r=Path(os.environ['FIXTURE_ROOT']);p=r/'io.json';d=json.loads(p.read_text());name=Path(sys.argv[0]).name;a=sys.argv[1:]
with (r/'calls.jsonl').open('a') as f:f.write(json.dumps([name,a])+'\\n')
if name=='logger':sys.exit(0)
if name=='ping':
 assert a==['-4','-I',d['address'],'-c','1','-W','1','192.168.10.1'],a
 if d.get('race'):(r/'config/network').open('a').write('# raced\\n')
 sys.exit(1 if d.get('miss') else 0)
if name=='ip':
 if a==['-4','-o','address','show']:
  print('1: br-lan.1 inet '+('192.168.10.99' if d.get('wrong_address') else d['address'])+'/24')
  if d.get('alias'):print('2: lo inet 192.168.10.1/32')
 elif a==['-4','route','get','192.168.10.1','from',d['address']]:
  if d.get('route_fail'):sys.exit(1)
  print('192.168.10.1 '+('via 192.168.10.2 ' if d.get('via') else '')+'dev '+('wrong0' if d.get('wrong_device') else 'br-lan.1')+' src '+d['address'])
 else:raise AssertionError(a)
 sys.exit(0)
assert name=='ubus' and a[0]=='call',a
if a[1]=='network.interface.xr_users_gate':
 if a[2]=='status':print(json.dumps({'autostart':d['open']}))
 else:
  assert a[2] in ['up','down'] and a[3]=='{}'
  if d.get('action_fail'):sys.exit(1)
  d['open']=a[2]=='up';p.write_text(json.dumps(d))
elif a[1]=='network.interface.lan':print(json.dumps({'up':not d.get('lan_down'),'l3_device':'br-lan.1'}))
elif a[1]=='network.wireless':
 dev=json.loads(a[3])['device'];assert dev=='radio1'
 print(json.dumps({'radio1':{'pending':False,'interfaces':[{'section':'xr_users','ifname':'phy0-ap0'}]+([{'section':'foreign','ifname':'phy0-ap1'}] if d.get('foreign') else [])}}))
else:raise AssertionError(a)
''');stub.chmod(0o755)
  for name in ['ubus','ip','ping','logger']:(bins/name).symlink_to(stub)
  # Host BusyBox has standalone applets: PATH alone does not replace ip/ping.
  # Functions override only these I/O commands, then source the unmodified file.
  driver=root/'driver.sh'
  driver.write_text('\n'.join(f'{n}() {{ "$FIXTURE_ROOT/bin/{n}" "$@"; }}' for n in ['ubus','ip','ping','logger'])+f'\n. "{program}"\n')
  env=dict(os.environ,PATH=str(bins)+':'+os.environ['PATH'],FIXTURE_ROOT=str(root),XR_GUARD_CONFIG_DIR=str(conf),XR_GUARD_STATE_DIR=str(state),XR_GUARD_LOCK_DIR=str(lock),XR_GUARD_UCI=str(bins/'uci'))
  address='192.168.10.3'
  def init(addr='192.168.10.3',threshold=None):
   nonlocal address
   address=addr
   for p in state.iterdir():p.unlink()
   for p in delta.iterdir():p.unlink()
   (root/'calls.jsonl').write_text('')
   (root/'io.json').write_text(json.dumps({'address':addr,'open':False}))
   (conf/'network').write_text(f'''config interface 'lan'
 option proto 'static'
 option device 'br-lan.1'
 option ipaddr '{addr}'
 option gateway '192.168.10.1'
config interface 'xr_users_gate'
 option proto 'none'
 option device 'br-lan.1'
 option xr1710g_owner 'users'
 option auto '0'
 option delegate '0'
''')
   (conf/'wireless').write_text('''config wifi-device 'radio1'
 option band '5g'
 option disabled '0'
config wifi-iface 'xr_users'
 option device 'radio1'
 option xr1710g_owner 'users'
 option mode 'ap'
 option network 'xr_users_gate'
 option disabled '0'
 option ssid 'fixture-users'
 option key 'fixture-pass-only'
 option encryption 'sae'
''')
   (conf/'xr1710g_ap_configurator').write_text(f'''config ap 'profile'
 option management_ip '{addr}'
 option management_gateway '192.168.10.1'
config wifi 'users'
 option enabled '1'
 option ssid 'fixture-users'
 option key 'fixture-pass-only'
 option encryption 'sae'
config guard 'uplink_guard'
 option enabled '1'
 option deployed '1'
 option interval '5'
 option recovery_successes '3'
'''+('' if threshold is None else f" option failure_threshold '{threshold}'\n"))
  def control(**kw):
   p=root/'io.json';d=json.loads(p.read_text());d.update(kw);p.write_text(json.dumps(d))
  def step(action='once',**kw):
   nonlocal ticks
   control(**kw);before={p.name:sha(p) for p in conf.iterdir()}
   result=subprocess.run(['/bin/busybox','ash',str(driver),action],env=env,capture_output=True,text=True,timeout=30);ticks+=1
   assert result.returncode==0,(result.stdout,result.stderr)
   assert not list(lock.iterdir()) and not list(state.glob('check.*'))
   assert 'fixture-pass-only' not in result.stdout+result.stderr+(state/'status.json').read_text()+(root/'calls.jsonl').read_text()
   if not kw.get('race'):assert before=={p.name:sha(p) for p in conf.iterdir()},'guard changed UCI'
   return json.loads((state/'status.json').read_text())
  def expect(d,gate,reason,action='none'):
   assert (d['gate_autostart'],d['desired'],d['reason'],d['last_action'])==(gate,gate,reason,action),d
  def opened(addr='192.168.10.3',threshold=None):
   init(addr,threshold)
   for n in [1,2]:
    d=step();expect(d,'closed','gateway-recovery-hysteresis');assert d['success_streak']==n
   expect(step(),'open','gateway-reachable','up')
  def done(name):cases.append(name);print(name,flush=True)
  for addr in ['192.168.10.3','192.168.10.4']:
   opened(addr);d=step(miss=True)
   expect(d,'open','gateway-failure-hysteresis');assert d['failure_streak']==1 and d['failure_threshold']==3
   expect(step(miss=False),'open','gateway-reachable')
   for n in [1,2]:
    d=step(miss=True);expect(d,'open','gateway-failure-hysteresis');assert d['failure_streak']==n
   d=step();expect(d,'closed','gateway-unreachable','down');assert d['failure_streak']==3
   d=step();expect(d,'closed','gateway-unreachable');assert d['failure_streak']==3
   for n in [1,2]:
    d=step(miss=False);expect(d,'closed','gateway-recovery-hysteresis');assert d['success_streak']==n
   expect(step(),'open','gateway-reachable','up');done(addr+' legacy profile default: isolated loss, first recovery, consecutive loss and 3-success reopen')
  opened(threshold=1);expect(step(miss=True),'closed','gateway-unreachable','down');done('explicit threshold1 retains immediate failure close')
  opened(threshold=6)
  for n in range(1,6):d=step(miss=True);expect(d,'open','gateway-failure-hysteresis');assert d['failure_streak']==n
  expect(step(),'closed','gateway-unreachable','down');done('threshold6 saturates and closes on sixth consecutive miss')
  for value in ['0','7','03','bad']:
   init(threshold=value);control(open=True);expect(step(),'closed','policy-disabled','down')
  done('invalid threshold values close existing owned gate')
  for field,reason in [('lan_down','management-interface-down'),('alias','gateway-is-local-alias'),('wrong_address','management-address-not-on-device'),('route_fail','gateway-route-unavailable'),('via','gateway-route-not-direct'),('wrong_device','gateway-route-wrong-device')]:
   opened();d=step(**{field:True});expect(d,'closed',reason,'down');assert d['failure_streak']==0
  done('six structural management faults close without debounce')
  for action in ['hold','stop']:
   opened();expect(step(action),'closed','maintenance-hold','down')
  done('hold and stop close immediately')
  for miss in [False,True]:
   opened()
   subprocess.run([str(bins/'uci'),'set','network.lan.gateway=192.168.10.22'],check=True)
   expect(step(miss=miss),'closed','pending-uci-edits','down')
  done('pending UCI deltas close with either successful or failed ping')
  for miss in [False,True]:
   opened();(conf/'network').open('a').write('# changed context\n')
   expect(step(miss=miss),'closed','gateway-unreachable' if miss else 'gateway-recovery-hysteresis','down')
  done('context changes invalidate prior open privilege and streaks')
  opened();d=step(foreign=True,miss=True);assert d['reason']=='other-bss-present-maintenance-required' and d['last_action']=='none' and d['gate_autostart']=='open'
  done('foreign BSS ownership prevents all gate actions')
  opened();d=step(race=True,miss=True);assert d['reason']=='configuration-changed-during-check' and d['last_action']=='none' and d['gate_autostart']=='open'
  done('concurrent configuration mutation rejects action')
  opened();step(miss=True);step();d=step(action_fail=True);assert d['reason']=='down-failed' and d['gate_autostart']=='open'
  expect(step(action_fail=False),'closed','gateway-unreachable','down');done('failed close retries immediately despite action backoff')
  init();step();step();d=step(action_fail=True);assert d['reason']=='up-failed' and d['gate_autostart']=='closed'
  d=step(action_fail=False);assert d['reason']=='action-retry-backoff' and d['gate_autostart']=='closed'
  d=json.loads((state/'status.json').read_text());d['next_retry_uptime']=0;(state/'status.json').write_text(json.dumps(d))
  expect(step(),'open','gateway-reachable','up');done('failed open respects existing retry backoff')
  report={'passed':True,'programSHA256':sha(program),'tickCount':ticks,'cases':cases,'uciSHA256':sha(rt/'sbin/uci'),'jsonfilterSHA256':sha(rt/'usr/bin/jsonfilter'),'scope':'Actual complete shell guard, ARM UCI/jsonfilter, BusyBox ash; network and ubus fixtures only; no physical Wi-Fi or NPU emulation'}
  args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
