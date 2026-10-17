"""Bounded software connectivity after both AP33 deployments, no capture."""
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import json, re, subprocess
from xr_two_ap import WORKSPACE as w, connect, command

out=w/'development/ap33'
results={u:json.loads((out/f'deployment/ap{u}/result.json').read_text()) for u in (1,2)}
assert all(x['passed'] and x['version']=='20261011-ap33-d331711d' for x in results.values())
def ap(unit):
    c=connect(unit,via='lan')
    try:
        before=command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip()
        assert before==results[unit]['bootID']
        o,e,rc=command(c,'ping -I br-lan.1 -c 30 -i 1 -s 1400 -W 2 '+('192.168.10.4' if unit==1 else '192.168.10.3'),timeout=45,check=False)
        text=o.decode(errors='replace')
        match=re.search(r'(\d+) packets transmitted, (\d+) packets received, (\d+)% packet loss',text)
        passed=rc==0 and match is not None and tuple(map(int,match.groups()))==(30,30,0)
        assert command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip()==before
        return {'unit':unit,'passed':passed,'returnCode':rc,'summary':match[0] if match else None,
                'stdout':text,'stderr':e.decode(errors='replace'),'bootID':before}
    finally:c.close()
def pc():
    p=subprocess.run(['ping.exe','-n','10','-l','1400','-w','1500','192.168.10.4'],capture_output=True,timeout=25)
    raw=p.stdout.decode('gb18030',errors='replace')
    passed=p.returncode==0 and re.search(r'\(\s*0%',raw) is not None
    return {'source':'wired Windows PC','destination':'AP2 through AP1/Mesh','passed':passed,'returnCode':p.returncode,'stdout':raw}
with ThreadPoolExecutor(max_workers=3) as pool:
    pending=[pool.submit(ap,1),pool.submit(ap,2),pool.submit(pc)]
    checks=[f.result() for f in pending]
now=datetime.now(timezone(timedelta(hours=8)))
report={'at':now.isoformat(),'passed':all(x['passed'] for x in checks),'checks':checks,
        'payloadSize':1400,'APProbeCountEach':30,'PCProbeCount':10,'NpuPpeEnabled':False,
        'configurationChanged':False,'rawPacketCapture':False,'throughputOrLongTermAcceptance':False}
(out/'postflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
(out/('postflight-'+now.strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'APResults':[{k:x[k] for k in ('unit','passed','summary')}for x in checks[:2]],'PCPassed':checks[2]['passed']}))
raise SystemExit(0 if report['passed'] else 1)
