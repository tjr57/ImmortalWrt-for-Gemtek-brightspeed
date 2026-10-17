#!/usr/bin/env python3
"""Check real packed wireless callback layout against actual kernel headers."""
from pathlib import Path
import argparse,hashlib,io,json,re,shlex,subprocess,tempfile
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

def compiler_args(command_file,source_suffix,root):
 line=command_file.read_text().splitlines()[0];assert line.startswith('savedcmd_')
 args=shlex.split(line.split(':=',1)[1].strip().split(';',1)[0])
 args=[a for a in args if not a.startswith(('-Wp,-MD,','-Wp,-MMD,'))]
 if args[0].endswith('ccache'):args=args[1:]
 assert Path(args[0]).name=='aarch64-openwrt-linux-musl-gcc' and '-c' in args and '-o' in args
 cc=list((root/'staging_dir').glob('toolchain-aarch64*/bin/aarch64-openwrt-linux-musl-gcc'));assert len(cc)==1
 args[0]=str(cc[0]);inputs=[i for i,a in enumerate(args) if a.endswith(source_suffix)];assert len(inputs)==1
 return args,inputs[0],args.index('-o')+1

def probe(command_file,source_suffix,cwd,root,out):
 args,input_index,output_index=compiler_args(command_file,source_suffix,root)
 p=out/'layout.c';obj=out/'layout.o'
 p.write_text('''#include <linux/netdevice.h>
const unsigned long xr_layout_values[] = {
 sizeof(struct net_device),offsetof(struct net_device,name),offsetof(struct net_device,napi_list),
 sizeof(struct net_device_ops),offsetof(struct net_device_ops,ndo_open),offsetof(struct net_device_ops,ndo_setup_tc),
 sizeof(struct napi_struct),offsetof(struct napi_struct,dev),offsetof(struct napi_struct,poll)
};
''')
 args[input_index]=str(p);args[output_index]=str(obj)
 result=subprocess.run(args,cwd=cwd,capture_output=True,text=True)
 if result.returncode:raise RuntimeError(result.stderr[-1800:])
 with obj.open('rb') as f:
  elf=ELFFile(f);symbols=elf.get_section_by_name('.symtab').get_symbol_by_name('xr_layout_values');assert len(symbols)==1
  s=symbols[0];raw=elf.get_section(s['st_shndx']).data()[s['st_value']:s['st_value']+s['st_size']];assert len(raw)==72
  values=[int.from_bytes(raw[i:i+8],'little') for i in range(0,len(raw),8)]
 return dict(zip(['netDeviceBytes','netDeviceName','netDeviceNapiList','netDeviceOpsBytes','ndoOpen','ndoSetupTc','napiBytes','napiDev','napiPoll'],values))

def active_kernel_tree(root):
 details=(root/'target/linux/generic/kernel-6.18').read_text()
 match=re.search(r'^LINUX_VERSION-6\.18\s*=\s*(\.\d+)\s*$',details,re.M)
 if not match:raise ValueError('Cannot resolve configured 6.18 kernel')
 kernel=root/('build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18'+match[1])
 if not (kernel/'.config').is_file():raise ValueError('Configured kernel tree missing: '+str(kernel))
 return kernel

def check(root):
 k=active_kernel_tree(root);ld=k.parent;backports=list(ld.glob('mac80211-regular/backports-*'));assert len(backports)==1;b=backports[0]
 with tempfile.TemporaryDirectory(prefix='xr-module-abi-') as temporary:
  out=Path(temporary);a=out/'kernel';a.mkdir();z=out/'wireless';z.mkdir()
  kernel=probe(k/'net/core/.dev.o.cmd','net/core/dev.c',k,root,a)
  wireless=probe(b/'net/wireless/.nl80211.o.cmd','net/wireless/nl80211.c',b,root,z)
  assert kernel==wireless,'Kernel and wireless-header layouts disagree'
  module=root/'build_dir/target-aarch64_cortex-a53_musl/root-airoha/lib/modules'/k.name.removeprefix('linux-')/'mac80211.ko'
  raw=module.read_bytes();elf=ELFFile(io.BytesIO(raw));rows=[]
  for section in elf.iter_sections():
   if not isinstance(section,RelocationSection) or elf.get_section(section['sh_info']).name!='.rodata':continue
   symtab=elf.get_section(section['sh_link'])
   for relocation in section.iter_relocations():
    name=symtab.get_symbol(relocation['r_info_sym']).name
    if name in ('ieee80211_open','ieee80211_netdev_setup_tc'):rows.append({'name':name,'offset':relocation['r_offset']})
  opens=[x['offset'] for x in rows if x['name']=='ieee80211_open'];setups=[x['offset'] for x in rows if x['name']=='ieee80211_netdev_setup_tc']
  assert len(opens)==3 and len(setups)==2,'Unexpected wireless callback tables; review before exporting'
  actual=[]
  for setup in setups:
   candidates=[opening for opening in opens if 0<=setup-opening<kernel['netDeviceOpsBytes']];assert candidates
   actual.append(setup-(max(candidates)-kernel['ndoOpen']))
  assert actual==[kernel['ndoSetupTc']]*2,('Packed wireless callbacks use another kernel layout',actual,kernel['ndoSetupTc'])
  return {'passed':True,'checks':['actual target compiler kernel and backports header layouts agree',
    'two independent packaged mac80211 callback tables match kernel offsets'],
   'kernelLayout':kernel,'wirelessHeaderLayout':wireless,'packedCallbackOffsets':actual,
   'packedMac80211SHA256':hashlib.sha256(raw).hexdigest(),'kernelConfigSHA256':hashlib.sha256((k/'.config').read_bytes()).hexdigest(),
   'physicalBootAccepted':False}

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
 try:report=check(args.root.resolve())
 except Exception as error:report={'passed':False,'errorType':type(error).__name__,'error':str(error)}
 args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
