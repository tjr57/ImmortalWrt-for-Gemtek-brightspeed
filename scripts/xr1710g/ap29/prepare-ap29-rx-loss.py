from pathlib import Path
import difflib,hashlib,json
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap29'
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791'
original=(b/'mac80211.c').read_text();header=(out/'rx-loss-audit.h').read_text()
changed=original.replace('#include "mt76.h"','#include "mt76.h"\n#include "xr-rx-loss-audit.h"',1)
changed=changed.replace('mt76_check_ccmp_pn(struct sk_buff *skb)','mt76_check_ccmp_pn(struct sk_buff *skb, bool napi)',1)
changed=changed.replace('if (ret <= 0) {\n\t\tstatus->flag |= RX_FLAG_ONLY_MONITOR;', 'if (ret <= 0) {\n\t\txr_rx_loss_record(skb, 2, security_idx, napi);\n\t\tstatus->flag |= RX_FLAG_ONLY_MONITOR;',1)
changed=changed.replace('\tmemcpy(wcid->rx_key_pn[security_idx], status->iv, sizeof(status->iv));', '\txr_rx_loss_record(skb, 0, security_idx, napi);\n\tmemcpy(wcid->rx_key_pn[security_idx], status->iv, sizeof(status->iv));',1)
changed=changed.replace('\t\tmt76_check_ccmp_pn(skb);','''\t\tstruct mt76_rx_status *status = (struct mt76_rx_status *)skb->cb;

\t\tif (status->flag & RX_FLAG_ONLY_MONITOR)
\t\t\txr_rx_loss_record(skb, 1,
\t\t\t\tstatus->qos_ctl & IEEE80211_QOS_CTL_TID_MASK, !!napi);
\t\tmt76_check_ccmp_pn(skb, !!napi);''',1)
assert changed.count('xr_rx_loss_record(')==3
patch=''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='a/mac80211.c',tofile='b/mac80211.c'))
patch+=''.join(difflib.unified_diff([],header.splitlines(True),fromfile='/dev/null',tofile='b/xr-rx-loss-audit.h'))
p=r/'package/kernel/mt76/patches/9999t-XR-opt-in-6GHz-RX-rejection-origin.patch';assert not p.exists();p.write_text(patch)
mk=r/'package/kernel/mt76/Makefile';s=mk.read_text();assert 'PKG_RELEASE=14\n' in s;mk.write_text(s.replace('PKG_RELEASE=14\n','PKG_RELEASE=15\n',1))
(out/'patched-mac80211.c').write_text(changed);(out/'original-mac80211.c').write_text(original)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(out/'prepared.json').write_text(json.dumps({'patchSHA256':sha(p),'headerSHA256':sha(out/'rx-loss-audit.h'),'receiveVerdictsUnchanged':True,'defaultOff':True,'records':16,'scope':'6GHz driver ONLY_MONITOR versus software PN rejection; scalar metadata only'},indent=2)+'\n')
print('AP29_RX_ORIGIN_PREPARED')
