 'use strict';
'require view';
'require rpc';
'require ui';
'require poll';
var status = rpc.declare({object:'luci.xr1710g_ap_features',method:'status',expect:{}});
var settings = rpc.declare({object:'luci.xr1710g_ap_features',method:'settings',expect:{}});
var configure = rpc.declare({object:'luci.xr1710g_ap_features',method:'configure',
 params:['apply','roaming','ieee80211k','ieee80211v','ieee80211r','mlo','puncturing','mobility_domain','mode','bitmap'],expect:{}});
var confirm = rpc.declare({object:'luci.xr1710g_ap_features',method:'confirm',params:['confirmation_id'],expect:{}});
var restore = rpc.declare({object:'luci.xr1710g_ap_features',method:'restore',expect:{}});
return view.extend({
 load:function(){return Promise.all([status(),settings()]);},
 render:function(data){
  var self=this,s=data[0],v=data[1],inputs={},canRestore=!!v.can_restore,pending=!!v.confirmation_pending,confirmId=v.confirmation_id||'',preview=E('pre',{'style':'white-space:pre-wrap'}),message=E('p',{});
  var control=function(name,label,type,value){
   var element;
   if(type=='flag') element=E('input',{type:'checkbox',checked:!!value});
   else if(type=='select') element=E('select',{},[E('option',{value:'manual',selected:value!='auto'},'手动位图'),E('option',{value:'auto',selected:value=='auto'},'固件自动（实验）')]);
   else element=E('input',{type:type,value:String(value),min:type=='number'?0:null,max:type=='number'?255:null,maxlength:name=='mobility_domain'?4:null});
   inputs[name]=element;
   return E('div',{'class':'cbi-value'},[E('label',{'class':'cbi-value-title'},label),E('div',{'class':'cbi-value-field'},element)]);
  };
  var buttons=[],active=false,operation=0;
  var busy=function(value){active=value;buttons.forEach(function(b,i){b.disabled=value||(i==1&&pending)||(i==2&&!canRestore)||(i==3&&!pending);});};
  var update=function(result){
   if(result.can_restore!==undefined)canRestore=!!result.can_restore;
   if(result.confirmation_pending!==undefined)pending=!!result.confirmation_pending;
   confirmId=result.confirmation_id||'';
  };
  var readSettings=function(){return settings().then(function(state){
   update(state);
   ['roaming','ieee80211k','ieee80211v','ieee80211r','mlo','puncturing'].forEach(function(name){inputs[name].checked=!!state[name];});
   inputs.mobility_domain.value=state.mobility_domain||'1710';
   inputs.mode.value=state.mode||'manual';inputs.bitmap.value=String(state.bitmap||0);
   return state;
  });};
  var call=function(apply){
   var domain=inputs.mobility_domain.value,bitmap=inputs.bitmap.value;
   if(!/^[0-9a-f]{4}$/i.test(domain)||! /^(0|[1-9][0-9]{0,2})$/.test(bitmap)||Number(bitmap)>255){
    message.textContent='请填写四位十六进制漫游域和0到255的十进制位图。';return;
   }
   operation++;busy(true);message.textContent=apply?'正在生成并应用配置……':'正在检查配置……';
   return configure(apply,inputs.roaming.checked,inputs.ieee80211k.checked,inputs.ieee80211v.checked,
    inputs.ieee80211r.checked,inputs.mlo.checked,inputs.puncturing.checked,domain,inputs.mode.value,Number(bitmap))
    .then(function(result){
     message.textContent=result.message || '配置操作未返回结果。';preview.textContent=result.preview || '';
     update(result);
    }).catch(function(error){message.textContent='配置请求失败：'+error.message;})
    .finally(function(){busy(false);});
  };
  var check=E('button',{'class':'cbi-button cbi-button-action',click:function(){return call(false);}},'检查与预览');
  var apply=E('button',{'class':'cbi-button cbi-button-apply',click:function(){return call(true);}},'保存并应用');
  var undo=E('button',{'class':'cbi-button cbi-button-reset',disabled:!v.can_restore,click:function(){
   operation++;busy(true);return restore().then(function(result){message.textContent=result.message||'恢复失败。';preview.textContent='';update(result);return readSettings();})
    .catch(function(error){message.textContent='恢复请求失败：'+error.message;}).finally(function(){busy(false);});
  }},'恢复上一次设置');
  var accept=E('button',{'class':'cbi-button cbi-button-positive',disabled:!pending,click:function(){
   operation++;busy(true);return confirm(confirmId).then(function(result){message.textContent=result.message||'确认失败。';update(result);})
    .catch(function(error){message.textContent='确认请求失败：'+error.message;}).finally(function(){busy(false);});
  }},'确认此设置');buttons=[check,apply,undo,accept];
  if(pending)message.textContent='有待确认的设置；剩余'+String(v.confirmation_seconds||0)+'秒。请检查连接后确认，否则本次运行中会自动恢复。';
  if(v.automatic_restore_conflict)message.textContent='配置已由其他操作修改，自动恢复已停止以保留这些修改。';
  busy(false);
  poll.add(function(){
   if(!pending||active)return Promise.resolve();
   var observed=operation;
   return settings().then(function(state){
    if(active||operation!==observed)return;
    update(state);
    if(!pending){
     message.textContent=state.automatic_restore_conflict?'配置已由其他操作修改，自动恢复已停止以保留这些修改。':'待确认操作已结束，请核对当前设置。';
     return readSettings().then(function(){busy(false);});
    }
    message.textContent='请检查连接后确认；剩余'+String(state.confirmation_seconds||0)+'秒。';busy(false);
   }).catch(function(){});
  },5);

  var rows=[['版本',s.release||'AP15'],['无线回程','6GHz 专用于 Mesh'],
   ['手动/自动打孔驱动',s.puncturing_driver||'未知']];
  return E('div',{},[E('h2',{},'XR1710G 无线功能'),
   E('p',{},'新增功能尚待手机与实机验收。应用后需在180秒内确认，否则本次运行中自动恢复。首次启用打孔需要重启，页面不会自动重启设备。'),
   E('table',{'class':'table'},rows.map(function(row){return E('tr',{'class':'tr'},[E('td',{'class':'td'},row[0]),E('td',{'class':'td'},row[1])]);})),
   control('roaming','用户网络漫游','flag',v.roaming),
   control('ieee80211k','11k 邻居报告','flag',v.ieee80211k),
   control('ieee80211v','11v 切换建议','flag',v.ieee80211v),
   control('ieee80211r','11r 快速漫游','flag',v.ieee80211r),
   control('mobility_domain','两台相同的漫游域','text',v.mobility_domain||'1710'),
   control('mlo','用户网络 MLO（2.4GHz＋5GHz）','flag',v.mlo),
   control('puncturing','5GHz 160MHz 打孔','flag',v.puncturing),
   control('mode','打孔模式','select',v.mode||'manual'),
   control('bitmap','手动位图（自动模式填0）','number',v.bitmap||0),
   E('p',{},'MLO 暂不与11r或自动打孔组合启用。IoT、回程、SSID、密码、国家地区及 VLAN 保留。请先确认再重启；恢复缓存只保留本次运行，无法跨断电恢复。NPU/PPE 已从生产镜像移除；本页不提供相关开关。'),
   E('div',{},buttons),message,preview]);
 },handleSaveApply:null,handleSave:null,handleReset:null
});
