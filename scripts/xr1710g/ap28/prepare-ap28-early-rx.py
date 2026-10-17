"""Extend opt-in Mesh metadata to driver-flagged early RX rejection."""
from pathlib import Path
import difflib,hashlib,json,shutil
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap28';out.mkdir(exist_ok=True)
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mac80211-regular/backports-7.2/net/mac80211'
original=(b/'rx.c').read_text();oldheader=(b/'xr-mesh-rx-audit.h').read_text()
assert oldheader==(w/'development/ap27/mesh-rx-audit.h').read_text()
helper='''
/* pubsta is supplied by the driver and protected by the RX caller's RCU
 * section. Record only known Mesh peers; unknown stations are not attributed.
 * 0x20000000 is an observer-only namespace, never a kernel drop verdict.
 */
static void xr_mesh_rx_early_drop(struct ieee80211_sta *pubsta,
\t\t\t\t  struct sk_buff *skb, u32 flags)
{
\tstruct ieee80211_rx_data rx = {};
\tstruct sta_info *sta;

\tif (!READ_ONCE(xr_mesh_rx_drop_audit) || !pubsta)
\t\treturn;
\tsta = container_of(pubsta, struct sta_info, sta);
\trx.sdata = sta->sdata;
\trx.skb = skb;
\txr_mesh_rx_drop_record(&rx, 0x20000000 | flags, false);
}
'''
newheader=oldheader.replace('\nstatic int xr_mesh_rx_drop_get(',helper+'\nstatic int xr_mesh_rx_drop_get(',1)
old='''\tstatus->rx_flags = 0;

\tkcov_remote_start_common(skb_get_kcov_handle(skb));'''
new='''\tstatus->rx_flags = 0;

\t/* These frames are consumed before the normal RX handlers. */
\tif (status->flag & (RX_FLAG_ONLY_MONITOR | RX_FLAG_FAILED_FCS_CRC |
\t\t\t    RX_FLAG_FAILED_PLCP_CRC))
\t\txr_mesh_rx_early_drop(pubsta, skb,
\t\t\tstatus->flag & (RX_FLAG_ONLY_MONITOR | RX_FLAG_FAILED_FCS_CRC |
\t\t\t\t\tRX_FLAG_FAILED_PLCP_CRC));

\tkcov_remote_start_common(skb_get_kcov_handle(skb));'''
assert original.count(old)==1;changed=original.replace(old,new,1)
content=''
for path,a,z in [('rx.c',original,changed),('xr-mesh-rx-audit.h',oldheader,newheader)]:
    content+=''.join(difflib.unified_diff(a.splitlines(True),z.splitlines(True),fromfile='a/net/mac80211/'+path,tofile='b/net/mac80211/'+path))
patch=r/'package/kernel/mac80211/patches/subsys/9999e-XR-Mesh-early-RX-drop-metadata.patch';assert not patch.exists();patch.write_text(content)
(out/'mesh-rx-audit.h').write_text(newheader);(out/'patch.diff').write_text(content)
mk=r/'package/kernel/mac80211/Makefile';s=mk.read_text();assert 'PKG_RELEASE:=10\n' in s;mk.write_text(s.replace('PKG_RELEASE:=10\n','PKG_RELEASE:=11\n',1))
qa=(w/'environment/test-ap27-mesh-audit.py').read_text().replace('development/ap27','development/ap28')
qa=qa.replace('struct ieee80211_rx_data {struct sdata *sdata;struct skb *skb;};','''struct ieee80211_rx_data {struct sdata *sdata;struct skb *skb;};
struct ieee80211_sta {int placeholder;};
struct sta_info {struct ieee80211_sta sta;struct sdata *sdata;};
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-__builtin_offsetof(type,member)))''')
qa=qa.replace('assert(!xr_mesh_rx_drop_audit);','''struct sta_info peer={.sdata=&iface};
 assert(!xr_mesh_rx_drop_audit);
 xr_mesh_rx_early_drop(&peer.sta,&packet,4);assert(!xr_mesh_rx_drop_total);
 xr_mesh_rx_drop_audit=true;xr_mesh_rx_early_drop(NULL,&packet,4);assert(!xr_mesh_rx_drop_total);
 iface.vif.mesh=false;xr_mesh_rx_early_drop(&peer.sta,&packet,4);assert(!xr_mesh_rx_drop_total);iface.vif.mesh=true;
 xr_mesh_rx_early_drop(&peer.sta,&packet,4);assert(xr_mesh_rx_drop_total==1&&xr_mesh_rx_drops[0].reason==0x20000004);read_check();
 xr_mesh_rx_early_drop(&peer.sta,&packet,32|64);assert(xr_mesh_rx_drop_total==2&&xr_mesh_rx_drops[1].reason==0x20000060);read_check();
 /* fixture reset, not an exposed production operation */
 xr_mesh_rx_drop_total=0;memset(xr_mesh_rx_drops,0,sizeof(xr_mesh_rx_drops));xr_mesh_rx_drop_audit=false;
 assert(!xr_mesh_rx_drop_audit);''',1)
qa=qa.replace('struct skb','struct sk_buff')
qa_path=w/'environment/test-ap28-mesh-audit.py';assert not qa_path.exists();qa_path.write_text(qa)
dest=out/'mesh-rx-audit';dest.mkdir(exist_ok=True)
build=(w/'environment/build-ap27-mesh-audit.py').read_text().replace('development/ap27','development/ap28');(w/'environment/build-ap28-mesh-audit.py').write_text(build)
(dest/'patched-rx.c').write_text(changed)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'prepared':True,'patchSHA256':sha(patch),'headerSHA256':sha(out/'mesh-rx-audit.h'),'defaultOff':True,'receivePolicyUnchanged':True,'scope':'Known Mesh peer driver ONLY_MONITOR/FCS/PLCP flags before mac80211 RX monitor gate; unknown peer or pre-driver drops remain unobserved','payloadOrKeyBytesRecorded':False}
(out/'prepared.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
