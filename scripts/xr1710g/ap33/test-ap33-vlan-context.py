"""Exact new PPE context/key functions; underlying bridge APIs modeled here."""
from pathlib import Path
import fcntl,hashlib,json,os,subprocess
w=Path('/mnt/d/ChatGPT/XR1710G');r=Path('/home/xrdev/projects/xr1710g/openwrt');out=w/'development/ap33/bridge-policy'
tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl';root=r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'
new=(out/'airoha_ppe.c').read_text();old=(out/'before-airoha_ppe.c').read_text()
def fn(s,sig):
 a=s.index(sig);return s[a:s.index('\n}\n',a)+3]
s=(w/'development/ap31/ppe-context/context-contract.c').read_text()
s=s.replace('unsigned int state;','unsigned int state,vlan_state;')
s=s.replace('.state=BR_STATE_FORWARDING}', '.state=BR_STATE_FORWARDING,.vlan_state=BR_STATE_FORWARDING}')
marker='static bool airoha_ppe_l2_context('
orig=fn(s,marker);assert orig==fn(old,marker)
oldcontext=orig.replace('airoha_ppe_l2_context','pre_vlan_context')
api='''static bool br_vlan_forwarding_rcu(const struct net_device*d,u16 vid){return d->member&&vid==50&&d->vlan_state==BR_STATE_FORWARDING;}\n'''
s=s.replace(orig,api+oldcontext+fn(new,marker),1)
test='''
 /* New negative control: port forwards, but ingress/egress VLAN is blocked. */
 for(int side=0;side<2;side++)for(int state=0;state<256;state++){
  reset();struct net_device*d=side?&outdev:&in;d->vlan_state=state;
  CHECK(pre_vlan_context(&rule,&outdev,&data,&key));
  CHECK(airoha_ppe_l2_context(&rule,&outdev,&data,&key)==(state==BR_STATE_FORWARDING));
 }
'''
s=s.replace('int main(void){','int main(void){'+test,1)
(out/'context-contract.c').write_text(s)
# Keep previous packet/action fixtures, replacing only the packet function and
# add a blocked-VLAN negative control. Their historical action fixtures do not
# stand in for current bridge-context acceptance (tested separately above).
s=(w/'development/ap31/ppe-vlan/packet-contract.c').read_text()
marker='static bool airoha_ppe_skb_l2_key('
orig=fn(s,marker);assert orig==fn(old,marker)
api='''static bool vlan_forwarding=true;
static bool br_vlan_forwarding_rcu(const struct net_device*d,u16 vid){return d->member&&vid==50&&vlan_forwarding;}
'''
s=s.replace(orig,api+orig.replace('airoha_ppe_skb_l2_key','pre_vlan_packet_key')+fn(new,marker),1)
needle='CHECK(old_packet_key(&skb,&old_plain));CHECK(airoha_ppe_skb_l2_key(&skb,&new_plain));'
assert s.count(needle)==1
s=s.replace(needle,needle+'''
 vlan_forwarding=false;CHECK(pre_vlan_packet_key(&skb,&new_plain));CHECK(!airoha_ppe_skb_l2_key(&skb,&new_plain));
 vlan_forwarding=true;CHECK(airoha_ppe_skb_l2_key(&skb,&new_plain));
''')
(out/'packet-contract.c').write_text(s)
logs={}
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for fixture in ['context','packet']:
  for name,compiler,args in [('native','gcc',['-g','-fsanitize=address,undefined']),('ARM',str(tc/'bin/aarch64-openwrt-linux-musl-gcc'),['-Os'])]:
   binary=out/(fixture+'-'+name)
   p=subprocess.run([compiler,'-Wall','-Wextra','-Werror',*args,str(out/(fixture+'-contract.c')),'-o',str(binary)],capture_output=True,text=True,env=dict(os.environ,STAGING_DIR=str(tc)))
   assert p.returncode==0,p.stderr
   cmd=[str(binary)] if name=='native' else ['qemu-aarch64-static','-L',str(root),str(binary)]
   p=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
   (out/(fixture+'-'+name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(name,p.stdout,p.stderr)
   logs[fixture+'-'+name]=p.stdout.strip()
unchanged={}
for sig in ['static bool airoha_ppe_l2_actions(','static bool airoha_ppe_l2_ready_locked(',
 'static bool airoha_ppe_l2_snapshot(','static void airoha_ppe_l2_revoke_locked(',
 'static int airoha_ppe_l2_bridge_event(','static int\nairoha_ppe_foe_l2_flow_commit_entry(']:
 value=fn(new,sig);assert value==fn(old,sig);unchanged[sig]=hashlib.sha256(value.encode()).hexdigest()
deinit=fn(new,'void airoha_ppe_deinit(')
assert deinit.index('airoha_ppe_l2_policy_event(')<deinit.index('br_fwd_policy_unregister(')<deinit.index('rhashtable_destroy(')
report={'passed':True,'candidateSHA256':hashlib.sha256(new.encode()).hexdigest(),'logs':logs,
 'nativeASanUBSanAndARM':True,'kernelAPIsModeled':True,'AP32BlockedVLANAcceptedNegativeControl':True,
 'generationFunctionsUnchanged':unchanged,'generationEvidence':'development/ap32/packet-fence/qa.json',
 'preUnregisterL2LatchOrderingChecked':True,'fullPolicyOrHardwareQualified':False}
(out/'qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='generationFunctionsUnchanged'}))
