"""Check actual before/after packet key derivation, including wire/metadata VLAN."""
from pathlib import Path
import subprocess,json,hashlib,os,fcntl
w=Path('/mnt/d/ChatGPT/XR1710G');out=w/'development/ap31/ppe-vlan'
r=Path('/home/xrdev/projects/xr1710g/openwrt');tc=r/'staging_dir/toolchain-aarch64_cortex-a53_gcc-14.4.0_musl'
def extract(path):
 s=path.read_text();a=s.index('static bool airoha_ppe_skb_l2_key(');return s[a:s.index('\n}\n',a)+3]
before=extract(out/'before-airoha_ppe.c').replace('airoha_ppe_skb_l2_key','old_packet_key')
after=extract(out/'airoha_ppe.c')
s=(out/'contract.c').read_text()
s=s.replace('struct ethhdr {unsigned char h_dest[6],h_source[6];};','struct ethhdr {unsigned char h_dest[6],h_source[6];u16 h_proto;};')
extra=r'''
typedef uint8_t u8;
#define ETH_HLEN 14
#define VLAN_ETH_HLEN 18
#define ETH_P_IP 0x0800
struct iphdr {unsigned char ihl:4,version:4;u8 tos;u16 tot_len,id,frag_off;u8 ttl,protocol;u16 check;uint32_t saddr,daddr;};
struct vlan_ethhdr {u8 dest[6],source[6];u16 h_vlan_proto,h_vlan_TCI,h_vlan_encapsulated_proto;};
struct sk_buff {struct net_device*dev;u8*head,*mac,*tail;bool has_mac,has_tag;u16 vlan_proto,vlan_tci;uint32_t mark;};
static bool ppe_bridge_bind_enable=true;
static bool skb_mac_header_was_set(struct sk_buff*s){return s->has_mac;}
static struct ethhdr*eth_hdr(struct sk_buff*s){return (void*)s->mac;}
static u8*skb_tail_pointer(struct sk_buff*s){return s->tail;}
static bool is_valid_ether_addr(const u8*m){return !(m[0]&1)&&(m[0]|m[1]|m[2]|m[3]|m[4]|m[5]);}
static bool eth_type_vlan(u16 p){return p==htons(ETH_P_8021Q)||p==htons(0x88a8);}
static bool skb_vlan_tag_present(struct sk_buff*s){return s->has_tag;}
static u16 skb_vlan_tag_get_id(struct sk_buff*s){return s->vlan_tci&VLAN_VID_MASK;}
static u16 vlan_dev_vlan_proto(struct net_device*d){(void)d;return htons(ETH_P_8021Q);}
static u16 vlan_dev_vlan_id(struct net_device*d){return d->pvid;}
static bool ip_is_fragment(const struct iphdr*i){return !!(i->frag_off&htons(0x3fff));}
'''
a=s.index('static int checks,accepted;')
s=s[:a]+extra+before+after+s[a:]
fixture=r'''
static int packet_cases(void){
 _Alignas(8) unsigned char buffer[80]={0};unsigned char*buf=buffer+2;
 struct flow_rule rule;struct sk_buff skb={.dev=&in,.head=buf,.mac=buf,.tail=buf+34,.has_mac=true};
 struct ethhdr*eth=(void*)buf;struct iphdr*ip=(void*)(buf+14);
 struct airoha_l2_flow_key old_plain,old_tag,new_plain,new_tag,meta_tag;
 reset(&rule);eth->h_source[0]=2;eth->h_dest[0]=4;eth->h_proto=htons(ETH_P_IP);
 ip->version=4;ip->ihl=5;ip->protocol=IPPROTO_UDP;
 CHECK(old_packet_key(&skb,&old_plain));CHECK(airoha_ppe_skb_l2_key(&skb,&new_plain));
 skb.has_tag=true;skb.vlan_tci=50;skb.vlan_proto=htons(ETH_P_8021Q);
 CHECK(old_packet_key(&skb,&old_tag));CHECK(airoha_ppe_skb_l2_key(&skb,&new_tag));
 CHECK(!memcmp(&old_plain,&old_tag,sizeof(old_plain)));
 CHECK(memcmp(&new_plain,&new_tag,sizeof(new_plain)));
 CHECK(new_plain.vid==50&&new_tag.vid==50&&!new_plain.ingress_tagged&&new_tag.ingress_tagged);
 meta_tag=new_tag;
 for(int prio=0;prio<8;prio++){skb.vlan_tci=50|(prio<<13);CHECK(airoha_ppe_skb_l2_key(&skb,&new_tag));CHECK(!memcmp(&meta_tag,&new_tag,sizeof(new_tag)));}
 skb.vlan_tci=0;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_tci=4095;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_tci=51;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_tci=50;skb.vlan_proto=htons(0x88a8);CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 skb.vlan_proto=htons(ETH_P_8021Q);skb.has_tag=false;
 memmove(buf+18,buf+14,20);skb.tail=buf+38;
 struct vlan_ethhdr*vh=(void*)buf;vh->h_vlan_proto=htons(ETH_P_8021Q);vh->h_vlan_TCI=htons(50);vh->h_vlan_encapsulated_proto=htons(ETH_P_IP);
 CHECK(airoha_ppe_skb_l2_key(&skb,&new_tag));CHECK(!memcmp(&meta_tag,&new_tag,sizeof(new_tag)));
 skb.has_tag=true;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));skb.has_tag=false;
 vh->h_vlan_TCI=0;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));vh->h_vlan_TCI=htons(50);
 vh->h_vlan_encapsulated_proto=htons(ETH_P_8021Q);CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));vh->h_vlan_encapsulated_proto=htons(ETH_P_IP);
 for(int len=0;len<38;len++){skb.tail=buf+len;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));}skb.tail=buf+38;
 ip=(void*)(buf+18);ip->frag_off=htons(0x2000);CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));ip->frag_off=0;
 ip->protocol=IPPROTO_ICMP;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));ip->protocol=IPPROTO_TCP;
 skb.mark=1;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));skb.mark=0;
 in.vlan=true;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));in.vlan=false;
 bridge.filter=false;CHECK(!airoha_ppe_skb_l2_key(&skb,&new_tag));
 return 0;
}
'''
s=s.replace('int main(void){',fixture+'\nint main(void){\n CHECK(packet_cases()==0);',1)
(out/'packet-contract.c').write_text(s)
cc=tc/'bin/aarch64-openwrt-linux-musl-gcc'
commands=[['gcc','-Wall','-Wextra','-Werror','-g','-fsanitize=address,undefined',str(out/'packet-contract.c'),'-o',str(out/'packet-native')],
 [str(cc),'-Wall','-Wextra','-Werror','-Os',str(out/'packet-contract.c'),'-o',str(out/'packet-arm')]]
with Path('/home/xrdev/artifacts/xr1710g/build.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for cmd in commands:
  p=subprocess.run(cmd,env=dict(os.environ,STAGING_DIR=str(tc)),capture_output=True,text=True);assert p.returncode==0,p.stderr
logs={}
for name,cmd in [('native',[str(out/'packet-native')]),('ARM',['qemu-aarch64-static','-L',str(r/'staging_dir/target-aarch64_cortex-a53_musl/root-airoha'),str(out/'packet-arm')])]:
 p=subprocess.run(cmd,capture_output=True,text=True);(out/('packet-'+name+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,(name,p.stderr);logs[name]=p.stdout.strip()
report={'passed':True,'actualPacketKeyFunctions':True,'oldTaggedAndPvidAliasDemonstrated':True,'candidateKeysDistinct':True,'metadataAndWireTagAgreement':True,'packetPayloadNotCaptured':True,'nativeASanUBSan':True,'armUserMode':True,'kernelAPIsModeled':True,'sourceSHA256':hashlib.sha256((out/'airoha_ppe.c').read_bytes()).hexdigest(),'logs':logs}
(out/'packet-qa.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
