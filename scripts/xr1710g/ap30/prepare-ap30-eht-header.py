from pathlib import Path
import difflib,hashlib,json
r=Path('/home/xrdev/projects/xr1710g/openwrt');w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap30';out.mkdir(exist_ok=True)
b=r/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~be5ce791'
original=(b/'mt76.h').read_text();anchor='\tmstat = *((struct mt76_rx_status *)skb->cb);\n'
assert original.count(anchor)==1
changed=original.replace(anchor,anchor+'''
\t/* TLV RX metadata precedes the 802.11 header. The producer saves
\t * mac_header before pushing it, as required by the mac80211 API.
\t * In particular, EHT U-SIG type33 is not a frame-control field.
\t */
\tif (mstat.flag & RX_FLAG_RADIOTAP_TLV_AT_END)
\t\treturn skb_mac_header(skb);
''',1)
p=r/'package/kernel/mt76/patches/9999u-XR-use-saved-MAC-header-for-EHT-RX.patch';assert not p.exists()
p.write_text(''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='a/mt76.h',tofile='b/mt76.h')))
mk=r/'package/kernel/mt76/Makefile';s=mk.read_text();assert 'PKG_RELEASE=15\n' in s;mk.write_text(s.replace('PKG_RELEASE=15\n','PKG_RELEASE=16\n',1))
(out/'original-mt76.h').write_text(original);(out/'patched-mt76.h').write_text(changed)
(out/'pn-check-source.c').write_text((b/'mac80211.c').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(out/'prepared.json').write_text(json.dumps({'patchSHA256':sha(p),'oldHeaderSHA256':sha(out/'original-mt76.h'),'newHeaderSHA256':sha(out/'patched-mt76.h'),'change':'Honor RX_FLAG_RADIOTAP_TLV_AT_END MAC header pointer before PN/frame-type decisions','securityChecksRemoved':False,'receiveStatusLayoutChanged':False},indent=2)+'\n')
print('AP30_EHT_HEADER_CANDIDATE_PREPARED')
