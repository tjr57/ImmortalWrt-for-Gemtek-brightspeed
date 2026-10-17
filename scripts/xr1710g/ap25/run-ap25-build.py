from pathlib import Path
import subprocess,json
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap25';r=Path('/home/xrdev/projects/xr1710g/openwrt')
p=subprocess.run(['python3',str(w/'environment/test-ap25-guard.py'),'--program',str(out/'guard-before.sh'),'--report',str(out/'negative-unexpected.json')],capture_output=True,text=True)
(out/'old-guard-negative.log').write_text(p.stdout+p.stderr)
assert p.returncode!=0 and "'reason': 'gateway-unreachable'" in p.stderr and "'last_action': 'down'" in p.stderr and not (out/'negative-unexpected.json').exists(),p.stderr
(out/'negative-control.json').write_text(json.dumps({'passed':True,'oldGuardFailedIntendedRegression':True,'observation':'First miss closes users gate in old guard','log':'old-guard-negative.log'},indent=2)+'\n')
subprocess.run(['python3',str(w/'environment/prepare-ap25-build.py')],check=True)
subprocess.run(['python3',str(w/'environment/xr1710g-safe-build.py'),'ap25','--root',str(r),'--artifacts','/home/xrdev/artifacts/xr1710g'],check=True)
