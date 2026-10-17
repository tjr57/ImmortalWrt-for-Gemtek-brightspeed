"""Exercise the current controller AND changed configurator together, offline."""
from pathlib import Path
import hashlib,json
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt')
out=w/'development/ap24/current-source-audit';out.mkdir(exist_ok=True)
t=(w/'environment/test-ap17-control.py').read_text()
t=t.replace("exec(compile(t,'ap17-control-fixture','exec'),{})", "")
ns={};exec(compile(t,'current-control-fixture-loader','exec'),ns)
t=ns['t'].replace('development/ap17','development/ap24/current-source-audit')
old="bad=dict(request,puncturing=True,mode='auto',mlo=True);run('configure',bad,False);assert before==snap()"
assert t.count(old)==1
t=t.replace(old,"allowed=dict(request,puncturing=True,mode='auto',mlo=True);run('configure',allowed);assert before==snap()")
t=t.replace('actualhelper rejects MLO+FT/autoPP+MLO/primarypuncturing without writes','current helper rejects MLO+FT/primarypuncturing and accepts autoPP+MLO preview without writes')
old="events.unlink();d=run('configure',dict(request,apply=True,puncturing=True,mode='auto'));assert d['reboot_required'] and not events.exists()"
assert t.count(old)==1
t=t.replace(old,"events.unlink();d=run('configure',dict(request,apply=True,puncturing=True,mode='auto',mlo=True));assert d['reboot_required'] and not events.exists()\n assert subprocess.run([str(uci),'-q','-c',str(conf),'get','wireless.xr_users.device'],capture_output=True,text=True,check=True).stdout.strip()=='radio1 radio0'")
t=t.replace('autoPP configuration waits for boot opt-in and does not reload live radios','autoPP+MLO publishes both device links and PP mode, waits for boot opt-in, restores exactly')
exec(compile(t,'ap24-current-controller-and-configurator','exec'),{})
report=json.loads((out/'control-qa.json').read_text())
report['configuratorSHA256']=hashlib.sha256((r/'package/network/config/xr1710g-ap-configurator/files/xr1710g-ap-configure').read_bytes()).hexdigest()
report['priorDescriptionSuperseded']='AP18-24 inherited control report tested unchanged controller but its autoPP+MLO rejection description predates changed configurator'
(out/'control-qa.json').write_text(json.dumps(report,indent=2)+'\n')
