"""Shipped ARM shell, actual rc.common and new helper; loader/actor boundaries mocked."""
from pathlib import Path
import hashlib,json,subprocess,shutil
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap30/npu-gates'
prepared=json.loads((out/'prepared.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for p,h in prepared['helperHashes'].items():assert sha(out/p)==h
reports=[]
for unit in [1]:
 source=(w/'environment/test-kmsg-shipped-shell.py').read_text()
 source=source[:source.index("(root/'usr/libexec/xr-kmsg-capture').write_text")]
 replacements={"base=w/'development/npu-first-fault'":f"base=w/'development/ap30/npu-gates/ap{unit}'",'20261010-ap22-d331711d-development':'20261010-ap30-d331711d-development','6df5cdb92072e4a51d8c0a81fc40e55804671181d43f1f2ebf519263306ba0bd':'904d5fb41e05424ce0185f26934318302e379761c68c30427d0ddd8a18def6c0','xr-kmsg-once':'xr-npu-guarded-once','xr1710g_kmsg_capture':'xr_guarded_npu',"'arm-shell-'":f"'maple-ap{unit}-'"}
 for old,new in replacements.items():assert old in source;source=source.replace(old,new)
 ns={};exec(compile(source,'actual-ARM-fixture-setup','exec'),ns);root=ns['root'];ship=ns['ship']
 for p in ['sys/kernel/debug','proc']:(root/p).mkdir(parents=True,exist_ok=True)
 def executable(path,data):
  p=root/path;p.write_text('#!/fixture/busybox sh\n'+data);p.chmod(0o755)
 executable('usr/libexec/xr-diag-activate','printf "actor\\n" >>/tmp/events\n')
 executable('bin/mount','[ ! -e /tmp/mount-fail ] || exit 1\nprintf "debugfs /sys/kernel/debug debugfs rw 0 0\\n" > /proc/mounts\nprintf "mount\\n" >>/tmp/events\n')
 executable('bin/insmod','''[ ! -e /tmp/insmod-fail ] || exit 1
case "$1" in
 /usr/libexec/xr_npu_addresses.ko) printf 'address\n' >>/tmp/events ;;
 /usr/libexec/xr_maple_observer.ko)
  printf 'maple\n' >>/tmp/events
  [ ! -e /tmp/endpoint-fail ] || exit 0
  if [ -e /tmp/captured ]; then printf 'schema=1 captured=1\n'; else printf 'schema=1 captured=0\n'; fi >/sys/kernel/debug/xr_maple_observer ;;
 *) exit 2 ;;
esac
''')
 old='22222222-2222-2222-2222-222222222222';current='11111111-1111-1111-1111-111111111111'
 (root/'proc/sys/kernel/random/boot_id').write_text(current+'\n')
 (root/'tmp/sysinfo/board_name').write_text('gemtek,xr1710g\n');(root/'tmp/role').write_text(json.dumps({'role':f'ap{unit}'})+'\n')
 address=root/'usr/libexec/xr_npu_addresses.ko';address.write_text('address fixture module\n')
 module=root/'usr/libexec/xr_maple_observer.ko';actual=w/'development/ap24/maple-observer/xr_maple_observer.ko';shutil.copy2(actual,module)
 request=root/'etc/xr-npu-guarded.once';events=root/'tmp/events';cases=[]
 def run():return subprocess.run(['chroot',str(root),'/bin/sh','/etc/rc.common','/etc/init.d/xr_guarded_npu','boot'],capture_output=True,text=True,timeout=15)
 def reset(boot=old):
  for name in ['events','mount-fail','insmod-fail','endpoint-fail','captured']:(root/'tmp'/name).unlink(missing_ok=True)
  (root/'sys/kernel/debug/xr_maple_observer').unlink(missing_ok=True)
  (root/'proc/mounts').write_text('');request.write_text('xr-npu-guarded-v1 '+boot+'\n');request.chmod(0o600)
 def test(name,success,consumed=False):
  p=run();assert (p.returncode==0)==success,(unit,name,p.returncode,p.stdout,p.stderr)
  if not success:assert not events.exists() or 'actor' not in events.read_text()
  if consumed:assert not request.exists()
  cases.append(name)
 reset();request.unlink();test('no marker no-op',True);assert not events.exists()
 reset(current);test('same boot never activates',True);assert request.exists() and not events.exists()
 reset();request.chmod(0o644);test('loose marker mode',False);assert request.exists()
 reset();(root/'tmp/role').write_text(json.dumps({'role':f'ap{3-unit}'})+'\n');test('wrong role',False);assert request.exists();(root/'tmp/role').write_text(json.dumps({'role':f'ap{unit}'})+'\n')
 reset();(root/'proc/mounts').write_text('tmpfs /sys/kernel/debug tmpfs rw 0 0\n');test('wrong debug filesystem',False,True)
 reset();(root/'tmp/mount-fail').touch();test('debug mount failure',False,True)
 reset();(root/'tmp/insmod-fail').touch();test('observer load failure',False,True)
 reset();module.unlink();test('missing Maple module',False,True);shutil.copy2(actual,module)
 reset();module.write_text('bad module\n');test('wrong module digest',False,True);shutil.copy2(actual,module)
 reset();(root/'tmp/endpoint-fail').touch();test('missing observer endpoint',False,True)
 reset();(root/'tmp/captured').touch();test('already captured observer rejected',False,True)
 reset();test('successful ordered original-firmware startup',True,True);assert events.read_text().splitlines()==['mount','address','maple','actor']
 events.unlink();test('consumed request no-op on repeated invocation',True);assert not events.exists()
 reset();(root/'proc/mounts').write_text('debugfs /sys/kernel/debug debugfs rw 0 0\n');test('already-mounted debugfs',True,True);assert events.read_text().splitlines()==['address','maple','actor']
 report={'passed':True,'unit':unit,'checks':cases,'helperSHA256':sha(out/f'ap{unit}/files/xr-npu-guarded-once'),'shippedBusyBoxSHA256':sha(ship/'bin/busybox'),'fixture':str(root),'scope':'Actual ARM BusyBox and rc.common; module/activation and debugfs mount boundaries mocked; real module already qualified in AP24 guest/live tests'}
 (out/f'ap{unit}/shell-qa.json').write_text(json.dumps(report,indent=2)+'\n');reports.append(report);print(json.dumps({'unit':unit,'passed':True,'cases':len(cases)}),flush=True)
(out/'shell-qa.json').write_text(json.dumps({'passed':True,'totalCases':sum(len(r['checks']) for r in reports),'roles':reports},indent=2)+'\n')
