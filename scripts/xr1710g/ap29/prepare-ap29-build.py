from pathlib import Path
import re
w=Path('D:/ChatGPT/XR1710G')
def advance(s):return re.sub(r'ap2[78]|AP2[78]',lambda m:{'ap27':'ap28','ap28':'ap29','AP27':'AP28','AP28':'AP29'}[m[0]],s)
s=advance((w/'environment/build-ap28.py').read_text()).replace('mesh-rx-audit','rx-loss-audit')
s=s.replace("['prepare-ap29-early-rx.py','test-ap29-mesh-audit.py','build-ap29-mesh-audit.py','build-ap29.py']","['prepare-ap29-rx-loss.py','test-ap29-rx-loss.py','build-ap29-rx-loss.py','build-ap29.py','prepare-ap29-build.py']")
s=s.replace("out/'rx-loss-audit.h'","out/'rx-loss-audit.h'")
s=s.replace('Extend default-off Mesh RX metadata to known peer ONLY_MONITOR/FCS/PLCP flags before monitor gate','Distinguish driver ONLY_MONITOR and software PN rejection using default-off scalar metadata')
(w/'environment/build-ap29.py').write_text(s)
s=advance((w/'environment/check-ap28-build.py').read_text())
s=s.replace('eb960f6f290db9092608be716ee3de69d126ab0ae4a7e093cc197d33b3aa159f','093e47b02be6841d380c1c954784e5383c5280bea177f5742824f472548ddef4')
s=s.replace('mesh-rx-audit','rx-loss-audit').replace('mac80211.ko','mt76.ko')
s=s.replace("w/'development/ap28/ping-rxbuf", "w/'development/ap27/ping-rxbuf").replace("w/'development/ap28/busybox-arm-smoke", "w/'development/ap27/busybox-arm-smoke")
start=s.index("            # Package revisions can change names")
end=s.index("            assert pkg+'.'+kind not in norm",start)
s=s[:start]+'''            # mt76 package revision only; lifecycle script bodies must match.
            if pkg.startswith(('kmod-mt76-', 'kmod-mt7996-')):
                import re
                pkg=re.sub(r'-r?(14|15)$','',pkg)
'''+s[end:]
s=s.replace('Full rootfs delta limited to mac80211','Full rootfs delta limited to mt76')
s=s.replace('firmware blob, mt76/mt7996','firmware blob, mac80211/mt7996')
s=s.replace('packed mac80211 equals qualified module','packed mt76 equals qualified module')
s=s.replace('BusyBox ping headroom and default-off internal mac80211 metadata recorder','Default-off internal mt76 RX rejection recorder; BusyBox and mac80211 unchanged')
(w/'environment/check-ap29-build.py').write_text(s)
s=advance((w/'environment/ap28-deploy.py').read_text()).replace("root.parent/'ap28/ping-rxbuf","root.parent/'ap27/ping-rxbuf").replace("root/'mesh-rx-audit","root/'rx-loss-audit")
anchor=" assert all(absent(c,p) for p in markers)"
s=s.replace(anchor," assert read(c,'cat /sys/module/mt76/parameters/rx_loss_audit')=='N'\n assert read(c,'cat /sys/module/mt76/parameters/rx_loss_events').startswith('schema=1 enabled=0 total=0 retained=0')\n"+anchor,1)
(w/'environment/ap29-deploy.py').write_text(s)
print('AP29 build, packed QA and one-shot deployment helpers generated')
