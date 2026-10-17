"""Minimum ping RX queue headroom; preserve all other BusyBox changes."""
from pathlib import Path
import difflib,hashlib,json
repo=Path('/home/xrdev/projects/xr1710g/openwrt')
out=Path('/mnt/d/ChatGPT/XR1710G/development/ap27/ping-rxbuf');out.mkdir(exist_ok=True)
source=repo/'build_dir/target-aarch64_cortex-a53_musl/busybox-default/busybox-1.38.0/networking/ping.c'
original=source.read_text()
old='\tsockopt = (datalen * 2) + 7 * 1024; /* giving it a bit of extra room */\n'
assert original.count(old)==2
new=old+'''\t/* RX skb memory accounting can exceed the payload size by a page.
\t * Concurrent raw ICMP sockets also receive each other's replies.
\t * Keep headroom for short bursts instead of shrinking to ~7 KiB.
\t */
\tif (sockopt < 64 * 1024)
\t\tsockopt = 64 * 1024;
'''
changed=original.replace(old,new)
patch=repo/'package/utils/busybox/patches/901-ping-receive-queue-headroom.patch';assert not patch.exists()
content=''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='a/networking/ping.c',tofile='b/networking/ping.c'))
patch.write_text(content);(out/'patch.diff').write_text(content);(out/'original-ping.c').write_text(original);(out/'patched-ping.c').write_text(changed)
mk=repo/'package/utils/busybox/Makefile';text=mk.read_text();assert 'PKG_RELEASE:=4\n' in text;mk.write_text(text.replace('PKG_RELEASE:=4\n','PKG_RELEASE:=5\n',1))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'sourceBeforeSHA256':hashlib.sha256(original.encode()).hexdigest(),'patchSHA256':sha(patch),'requestedMinimum':65536,'IPv4AndIPv6':True,'otherPingSemanticsChanged':False,'configurationSHA256':sha(repo/'.config'),'status':'source-candidate-not-compiled-or-deployed'}
(out/'prepared.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
