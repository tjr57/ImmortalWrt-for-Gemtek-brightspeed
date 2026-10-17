"""Map new scalar RX-drop records to owned ICMP losses without one-way claims."""
from pathlib import Path
from collections import Counter
from statistics import median
import json,re
from xr_two_ap import WORKSPACE
from ap27_forwarding_observer import header_rows
out=WORKSPACE/'development/ap27/forwarding/software-mesh-reasons1'
rounds=json.loads((out/'rounds.json').read_text());stages={p.stem:header_rows(p.read_text()) for p in out.glob('*-headers.txt')};assert len(stages)==4
repo=Path('//wsl.localhost/Debian-XR1710G/home/xrdev/projects/xr1710g/openwrt')
drop=repo/'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mac80211-regular/backports-7.2/net/mac80211/drop.h'
names=re.findall(r'\bR\((RX_DROP_U_\w+)\)',drop.read_text());assert len(names)==len(set(names))
reason_names={0:'unspecified-fast-path',**{0x10000+i:n for i,n in enumerate(names,1)}}
def events(raw):
    return [{'serial':int(m[1]),'ms':int(m[2]),'reason':reason_names.get(int(m[3],16),m[3]),'reasonValue':int(m[3],16),'length':int(m[4]),'ifindex':int(m[5]),'fast':bool(int(m[6]))} for m in re.finditer(r'^(\d+) (\d+) (0x[0-9a-f]+) (\d+) (\d+) ([01])$',raw,re.M)]
def offset(raw):
    a,t,c=map(int,re.search(r'^CLOCK (\d+) (\d+) (\d+)$',raw,re.M).groups());assert 0<=c-a<10000000
    return (t-(a+c)/2)/1000000
def lookup(ident,seq,kind):return {n:[p['time'] for p in v if (p['id'],p['seq'],p['type'])==(ident,seq,kind)] for n,v in stages.items()}
unique={u:{} for u in ['1','2']};losses=[]
for row in rounds:
    for u in ['1','2']:
        for field in ['countersBefore','countersAfter']:
            for event in events(row[field][u]):unique[u][event['serial']]=event
    for name,p in row['probes'].items():
        if name=='gateway' or p['sent']==p['received']:continue
        ident=int(re.search(r'RX_SETUP .*?pid=(\d+)',p['socketAccounting'])[1])&65535
        missing=set(range(p['sent']))-{int(s) for s in re.findall(r'seq=(\d+) ttl=',p['stdout'])}
        for seq in sorted(missing):
            req=lookup(ident,seq,'request');rep=lookup(ident,seq,'reply');row_loss={'round':row['index'],'probe':name,'icmpID':ident,'seq':seq,'requests':req,'replies':rep,'socketAccounting':p['socketAccounting']}
            target=None;kind=None;origin=None
            if req['ap1-mesh6g-headers'] and not req['ap2-mesh6g-headers']:origin,target,kind='1','2','request'
            elif rep['ap2-mesh6g-headers'] and not rep['ap1-mesh6g-headers']:origin,target,kind='2','1','reply'
            if target:
                totals=[int(re.search(r'schema=1 enabled=1 total=(\d+)',row[f][target])[1]) for f in ['countersBefore','countersAfter']]
                row_loss['reasonRingCoversWholeRound']=0<=totals[1]-totals[0]<=32
                shifts=[]
                for other in range(p['sent']):
                    z=lookup(ident,other,kind);a=z[f'ap{origin}-mesh6g-headers'];b=z[f'ap{target}-mesh6g-headers']
                    if len(a)==len(b)==1:shifts.append(b[0]-a[0])
                assert shifts
                z=req if kind=='request' else rep
                expected=(z[f'ap{origin}-mesh6g-headers'][0]+median(shifts))*1000-offset(row['countersAfter'][target])
                retained=events(row['countersAfter'][target])
                serials=[e['serial'] for e in retained]
                a,t,c=map(int,re.search(r'^CLOCK (\d+) (\d+) (\d+)$',row['countersAfter'][target],re.M).groups())
                row_loss['reasonRingCoversLossWindow']=bool(retained and serials==list(range(totals[1]-len(retained)+1,totals[1]+1)) and retained[0]['ms']<=expected-100 and a/1000000>=expected+100)
                near=[e for e in retained if abs(e['ms']-expected)<=100]
                row_loss.update({'missingIngressAP':int(target),'estimatedExpectedMonotonicMs':expected,'nearbyReceiveDrops':near,'correlationToleranceMs':100,'notUniquePacketAttribution':True})
            losses.append(row_loss)
result={'sent':sum(p['sent'] for r in rounds for p in r['probes'].values()),'received':sum(p['received'] for r in rounds for p in r['probes'].values()),'losses':losses,'dropReasonCounts':{u:dict(Counter(e['reason'] for e in d.values())) for u,d in unique.items()},'events':{u:list(d.values()) for u,d in unique.items()},'limits':'Reason recorder covers mac80211 handlers only. Correlation uses adjacent successful frames to account for separate AP clocks; it is not exact ICMP identification or measured one-way delay.'}
(out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='events'},indent=2))
