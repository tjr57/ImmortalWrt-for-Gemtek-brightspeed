"""Execute actual RPC with isolated files/UCI and actual UI functions with a DOM double."""
from pathlib import Path
import ast, hashlib, json, subprocess, tempfile, shutil, os
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap26'
app=r/'feeds/app_airoha/luci-app-airoha-npu';rpc=app/'root/usr/libexec/rpcd/luci.airoha_npu'
old=w/'development/ap4-fusion-qa/rpc-ppe-policy/test_rpc_policy.py'
tree=ast.parse(old.read_text());tree.body=[x for x in tree.body if isinstance(x,(ast.Import,ast.ImportFrom,ast.FunctionDef))]
results=[]
with tempfile.TemporaryDirectory(prefix='ap26-rpc-') as temp:
 ns={'source':rpc.read_text(),'fixture_root':Path(temp),'results':results}
 exec(compile(tree,str(old),'exec'),ns)
 checks=[]
 cases=[
  ('legacy-ap',None,None,None,False,''),
  ('legacy-router',None,None,None,True,'active_wan'),
  ('global-off','N','Y','N',False,'ppe_boot_policy_disabled'),
  ('global-off-numeric','0','Y','N',False,'ppe_boot_policy_disabled'),
  ('bridge-off','Y','N','N',False,'ppe_bridge_boot_policy_disabled'),
  ('bridge-off-numeric','1','0','0',False,'ppe_bridge_boot_policy_disabled'),
  ('bridge-filtered','Y','Y','Y',False,'ppe_bridge_policy_latched'),
  ('bridge-filtered-numeric','1','1','1',False,'ppe_bridge_policy_latched'),
  ('explicit-rules','Y','Y','N',False,'ppe_explicit_rules_required'),
  ('missing-latch','Y','Y',None,False,'ppe_bridge_policy_unavailable'),
  ('bad-latch','Y','Y','invalid',False,'ppe_bridge_policy_unavailable'),
  ('bad-bridge','Y','invalid','N',False,'ppe_bridge_policy_unavailable'),
  ('router-priority','Y','N','Y',True,'active_wan'),
 ]
 for label,global_policy,bridge,latch,wan,reason in cases:
  item=ns['fixture'](global_policy,wan);root=item[0]
  for name,value in [('sys/module/airoha_eth/parameters/ppe_bridge_bind_enable',bridge),('sys/kernel/debug/ppe/xr_l2_policy_latched',latch)]:
   if value is not None:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value+'\n')
  mode=ns['call'](item,'getDeviceMode')
  assert mode['bridge_offload_blocked']==bool(reason) and mode['bridge_offload_block_reason']==reason,(label,mode)
  assert mode['hardware_flow_offload_blocked']==(global_policy in ('N','0'))
  assert mode['ppe_bridge_binding_enabled']==(True if bridge in ('Y','1') else False if bridge in ('N','0') else None)
  assert mode['ppe_bridge_policy_latched']==(True if latch in ('Y','1') else False if latch in ('N','0') else None)
  for getter,setter in [('getVlanOffload','setVlanOffload'),('getPppoeOffload','setPppoeOffload'),('getApModeOffload','setApModeOffload')]:
   value=ns['call'](item,getter)
   if reason:assert value=={'enabled':0,'policy_blocked':True,'reason':reason},(label,value)
   else:assert value['enabled']==1
   before=ns['proc_state'](root);log=item[3].read_text();persist=list((root/'etc/sysctl.d').iterdir())
   value=ns['call'](item,setter,1)
   if reason:
    assert value.get('reason')==reason and value.get('error')
    assert ns['proc_state'](root)==before and item[3].read_text()==log and list((root/'etc/sysctl.d').iterdir())==persist
   else:assert value['result']=='ok'
  flow=ns['call'](item,'getFlowOffload')
  assert flow['enabled']==int(global_policy not in ('N','0'))
  for setter in ['setVlanOffload','setPppoeOffload','setApModeOffload','setFlowOffload']:
   assert ns['call'](item,setter,0)['result']=='ok'
  checks.append(label)
 # Actual old RPC reproduces the gap: the new bridge gate is ignored and a
 # legacy enable persists sysctls, despite bridge binding being off.
 ns['source']=(out/'baseline/root/usr/libexec/rpcd/luci.airoha_npu').read_text()
 item=ns['fixture']('Y');(item[0]/'sys/module/airoha_eth/parameters/ppe_bridge_bind_enable').write_text('N\n')
 negative_mode=ns['call'](item,'getDeviceMode');negative=ns['call'](item,'setVlanOffload',1)
 assert not negative_mode['bridge_offload_blocked'] and negative['result']=='ok'
 assert (item[0]/'etc/sysctl.d/14-vlan-offload.conf').exists()
 checks.append('old-RPC-negative-control-reproduced')
report={'passed':True,'checks':checks,'rpcCalls':len(results),'programSHA256':hashlib.sha256(rpc.read_bytes()).hexdigest(),
 'runtime':'full actual RPC under host shell; absolute filesystem paths redirected, UCI/ubus/jsonfilter/modprobe are fixtures',
 'realDeviceOrNetworkChanged':False,'results':results}
(out/'rpc-qa.json').write_text(json.dumps(report,indent=2)+'\n')
js=Path(os.environ.get('XR_AP26_UI_SOURCE',str(app/'htdocs/luci-static/resources/view/airoha_npu/status.js')))
node=r'''const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(process.argv[1],'utf8');new Function(code);
function extract(name){let start=code.indexOf('function '+name+'('),open=code.indexOf('{',start),depth=0;assert(start>=0);for(let i=open;i<code.length;i++){depth+=(code[i]==='{')-(code[i]==='}');if(!depth)return code.slice(start,i+1);}throw Error(name);}
const c={_:x=>x,E:(tag,attrs,children)=>({tag,attrs,children}),aui:{switchRow:x=>x},ui:{addNotification:()=>{}},callSetFlowOffload:()=>{throw Error('unexpected RPC')},callSetVlanOffload:()=>{throw Error('unexpected RPC')},callSetApModeOffload:()=>{throw Error('unexpected RPC')}};
const names=['isEnabled','isBridgeOffloadBlocked','isPpeBootPolicyBlocked','isHardwareFlowOffloadBlocked','offloadBlockText','offloadBlockLabel','offloadState','renderOffloadSwitch','renderOffloadControls'];vm.runInNewContext(names.map(extract).join('\n'),c);
const modes=[['ppe_boot_policy_disabled','Disabled by boot policy',false],['ppe_bridge_boot_policy_disabled','Bridge disabled by boot policy',true],['ppe_bridge_policy_latched','Software forwarding required',true],['ppe_explicit_rules_required','Explicit forwarding rules required',true],['ppe_bridge_policy_unavailable','Forwarding policy unavailable',true],['active_wan','Router mode restricted',true],['','Router mode restricted',true]];
for(const [reason,label,ppe] of modes){const mode={ppe_binding_enabled:ppe,bridge_offload_blocked:!!reason,bridge_offload_block_reason:reason,hardware_flow_offload_blocked:!ppe};const rows=c.renderOffloadControls({compatible:'gemtek,xr1710g'},{enabled:0},{enabled:0},{enabled:0},mode).children;assert.equal(rows.length,3);assert.equal(c.offloadBlockLabel(mode),label);for(const row of rows){const isFlow=row.inputId==='flow-offload-select';assert.equal(row.blocked,isFlow?!ppe:!!reason);if(row.blocked)assert.equal(row.blockedLabel,label);}if(reason.startsWith('ppe_bridge')||reason==='ppe_explicit_rules_required'){assert(!c.offloadBlockText(mode).includes('router mode'));assert.equal(rows.find(r=>r.inputId==='flow-offload-select').blocked,false);}}
console.log(JSON.stringify({passed:true,modes:modes.length,actualFunctions:names,fullViewParsed:true,realBrowser:false}));'''
node_exe=shutil.which('node')
js_argument=str(js)
if node_exe is None:
 node_exe='/mnt/c/Program Files/nodejs/node.exe'
 (out/'ui-candidate.js').write_bytes(js.read_bytes())
 js_argument='D:/ChatGPT/XR1710G/development/ap26/ui-candidate.js'
p=subprocess.run([node_exe,'-e',node,js_argument],capture_output=True,text=True,check=True)
ui=json.loads(p.stdout);ui['sourceSHA256']=hashlib.sha256(js.read_bytes()).hexdigest();(out/os.environ.get('XR_AP26_UI_REPORT','ui-qa.json')).write_text(json.dumps(ui,indent=2)+'\n')
print(json.dumps({'passed':True,'rpcCalls':len(results),'RPCScenarios':len(checks),'UIModes':ui['modes']}))
