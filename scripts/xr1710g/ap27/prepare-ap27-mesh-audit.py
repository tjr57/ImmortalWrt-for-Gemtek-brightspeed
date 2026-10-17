from pathlib import Path
import difflib,hashlib,json
r=Path('/home/xrdev/projects/xr1710g/openwrt');out=Path('/mnt/d/ChatGPT/XR1710G/development/ap27/mesh-rx-audit');out.mkdir(exist_ok=True)
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mac80211-regular/backports-7.2/net/mac80211'
original=(b/'rx.c').read_text();changed=original.replace('#include "rate.h"\n','#include "rate.h"\n#include "xr-mesh-rx-audit.h"\n',1)
old='\tif (res != RX_CONTINUE) {\n\t\tI802_DEBUG_INC(rx->sdata->local->rx_handlers_drop);'
assert changed.count(old)==1
changed=changed.replace(old,'\tif (res != RX_CONTINUE) {\n\t\txr_mesh_rx_drop_record(rx, (__force u32)res, false);\n\t\tI802_DEBUG_INC(rx->sdata->local->rx_handlers_drop);',1)
start=changed.index('static bool ieee80211_invoke_fast_rx(');end=changed.index('\n/*',start)
part=changed[start:end]
assert part.count('ieee80211_rx_result res;')==1
part=part.replace('ieee80211_rx_result res;','ieee80211_rx_result res;\n\tu32 xr_drop_reason = 0;',1)
old='\tres = ieee80211_rx_mesh_data(rx->sdata, rx->sta, rx->skb);\n'
assert part.count(old)==1
part=part.replace(old,old+'\txr_drop_reason = (__force u32)res;\n',1)
old=' drop:\n\tdev_kfree_skb(skb);'
assert part.count(old)==1
part=part.replace(old,' drop:\n\txr_mesh_rx_drop_record(rx, xr_drop_reason, true);\n\tdev_kfree_skb(skb);',1)
changed=changed[:start]+part+changed[end:]
header=out.parent/'mesh-rx-audit.h';patch=r/'package/kernel/mac80211/patches/subsys/9999d-XR-opt-in-Mesh-RX-drop-metadata.patch';assert not patch.exists()
content=''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='a/net/mac80211/rx.c',tofile='b/net/mac80211/rx.c'))
content+=''.join(difflib.unified_diff([],header.read_text().splitlines(True),fromfile='/dev/null',tofile='b/net/mac80211/xr-mesh-rx-audit.h'))
patch.write_text(content);(out/'patch.diff').write_text(content);(out/'original-rx.c').write_text(original);(out/'patched-rx.c').write_text(changed)
mk=r/'package/kernel/mac80211/Makefile';s=mk.read_text();assert 'PKG_RELEASE:=9\n' in s;mk.write_text(s.replace('PKG_RELEASE:=9\n','PKG_RELEASE:=10\n',1))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'prepared':True,'patchSHA256':sha(patch),'headerSHA256':sha(header),'enabledByDefault':False,'payloadOrKeyBytesRecorded':False,'ringEntries':32,'scope':'mac80211 Mesh slow/fast receive handler drops only; not hardware/DMA drops or every early rejection','publicHeadersChanged':False}
(out/'prepared.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
