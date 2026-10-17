from pathlib import Path
import hashlib,json,subprocess,shutil,os
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap26'
app=r/'feeds/app_airoha/luci-app-airoha-npu'
qa=json.loads((out/'rpc-qa.json').read_text());assert qa['passed'];results=qa['results'];checks=qa['checks']
source=(w/'environment/test-ap26-ppe-control.py').read_text()
exec(compile(source[source.index('js=Path(os.environ.get('):], 'ap26-ui-qa', 'exec'))
