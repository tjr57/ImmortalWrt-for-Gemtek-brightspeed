from pathlib import Path
import re
w=Path('D:/ChatGPT/XR1710G')
def advance(s):return re.sub(r'ap2[89]|AP2[89]',lambda m:{'ap28':'ap29','ap29':'ap30','AP28':'AP29','AP29':'AP30'}[m[0]],s)
s=advance((w/'environment/build-ap29.py').read_text()).replace('rx-loss-audit/','eht-header/')
s=s.replace("out/'rx-loss-audit.h'", "out/'patched-mt76.h'").replace("dest/'rx-loss-audit.h'","dest/'patched-mt76.h'")
s=s.replace("['prepare-ap30-rx-loss.py','test-ap30-rx-loss.py','build-ap30-rx-loss.py','build-ap30.py','prepare-ap30-build.py']", "['prepare-ap30-eht-header.py','test-ap30-eht-header.py','build-ap30-driver.py','build-ap30.py','prepare-ap30-build.py']")
s=s.replace('Distinguish driver ONLY_MONITOR and software PN rejection using default-off scalar metadata','Fix EHT TLV header selection and prevent cross-TID false replay rejection').replace("'packetAcceptancePolicyUnchanged':True", "'correctPNCounterSelection':True,'replayChecksPreserved':True")
(w/'environment/build-ap30.py').write_text(s)
s=advance((w/'environment/check-ap29-build.py').read_text()).replace('rx-loss-audit/','eht-header/')
s=s.replace('093e47b02be6841d380c1c954784e5383c5280bea177f5742824f472548ddef4','5cfb7ac8f7b30359bc9be84bfc115f5ab7336ae9568c5d0afe45be1ee918871f')
s=s.replace("'lib/modules/6.18.54/mt76.ko',", "'lib/modules/6.18.54/mt76.ko','lib/modules/6.18.54/mt76-connac-lib.ko','lib/modules/6.18.54/mt7996e.ko',",1)
a=s.index("    raw=out/'eht-header/mt76.ko'");z=s.index('    scripts=[]',a)
s=s[:a]+'''    modules=json.loads((out/'eht-header/build.json').read_text())['moduleHashes'];verified={}
    for name,h in modules.items():
        raw=out/'eht-header'/name;assert sha(raw)==h
        stripped=Path(tmp)/('verified-'+name);shutil.copy2(raw,stripped)
        cross=str(r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl/bin/aarch64-openwrt-linux-musl-')
        subprocess.run(['sh',str(r/'scripts/strip-kmod.sh'),str(stripped)],env=dict(os.environ,CROSS=cross,NO_RENAME='1'),check=True)
        assert stripped.read_bytes()==(rf/'lib/modules/6.18.54'/name).read_bytes();verified[name]=sha(stripped)
    (out/'eht-header/packed-module-qa.json').write_text(json.dumps({'passed':True,'sourceModuleHashes':modules,'packedModuleHashes':verified},indent=2)+'\\n')
'''+s[z:]
s=s.replace('(14|15)','(15|16)').replace("if p!='lib/modules/6.18.54/mt76.ko':", "if p not in {'lib/modules/6.18.54/'+n for n in modules}:")
s=s.replace('Full rootfs delta limited to mt76','Full rootfs delta limited to affected mt76 modules').replace('firmware blob, mac80211/mt7996','firmware blob and mac80211').replace('packed mt76 equals qualified module','packed driver modules equal qualified modules').replace('Default-off internal mt76 RX rejection recorder; BusyBox and mac80211 unchanged','EHT saved MAC header fix;496 exact-source negative/positive regression cases;BusyBox and mac80211 unchanged')
(w/'environment/check-ap30-build.py').write_text(s)
s=advance((w/'environment/ap29-deploy.py').read_text()).replace("root/'rx-loss-audit/qa/result.json'", "root/'eht-header/qa/result.json'")
(w/'environment/ap30-deploy.py').write_text(s)
print('AP30 build, packed checks and one-shot deployment prepared')
