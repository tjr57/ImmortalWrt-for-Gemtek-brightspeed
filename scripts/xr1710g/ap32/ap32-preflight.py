"""Read-only current AP31 identity/health before AP32 release qualification."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import importlib.util, json, re
from xr_two_ap import WORKSPACE as w, connect as pinned, command

spec=importlib.util.spec_from_file_location('health',Path(__file__).with_name('ap18-r2-formal-common.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
h.VERSION='20261011-ap31-d331711d'
h.connect=lambda unit,**kw:pinned(unit,via='lan')
def inspect(unit):
    result=h.health(unit,h.VERSION)
    c=pinned(unit,via='lan')
    try:
        result['bootID']=command(c,'cat /proc/sys/kernel/random/boot_id')[0].decode().strip()
        data=command(c,'dmesg')[0].decode(errors='replace')
        result['faultLines']=re.findall(r'^.*(?:WARNING:|BUG:|Oops:|Call [Tt]race:|KASAN:|Kernel panic|TXFREE truncated).*$',data,re.M)
        result['diagnosticMarkersAbsent']=command(c,'test ! -e /etc/xr-npu-guarded.once -a ! -e /etc/xr-recovery.once -a ! -e /etc/xr-kmsg-capture.once',check=False)[2]==0
    finally:c.close()
    return result
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(inspect,[1,2]))
at=datetime.now(timezone(timedelta(hours=8)))
report={'at':at.isoformat(),'readOnly':True,'devices':results,'passed':all(x['healthy'] and not x['faultLines'] and x['diagnosticMarkersAbsent'] for x in results)}
p=w/'development/ap32'/('live-preflight-'+at.strftime('%Y%m%d-%H%M%S')+'.json')
p.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'evidence':str(p.relative_to(w)),'devices':[{'unit':x['unit'],'healthy':x['healthy'],'checks':len(x['checks']),'bootID':x['bootID'],'faultCount':len(x['faultLines'])}for x in results]}))
