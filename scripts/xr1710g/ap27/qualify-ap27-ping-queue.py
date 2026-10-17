import json,re,hashlib
from xr_two_ap import WORKSPACE
from ap27_forwarding_observer import header_rows
out=WORKSPACE/'development/ap27/ping-rxbuf';trial=out/'live-queue2'
assert json.loads((trial/'result.json').read_text())['completed']
stages={p.stem:header_rows(p.read_text()) for p in trial.glob('*-headers.txt')};assert len(stages)==4
rows=json.loads((trial/'rounds.json').read_text());checks=[]
for row in rows:
    ident=int(re.search(r'QUEUE_SETUP pid=(\d+)',row['stderr'])[1])&65535
    for stage,records in stages.items():
        for kind in ['request','reply']:
            seqs=[p['seq'] for p in records if p['id']==ident and p['type']==kind]
            assert sorted(seqs)==list(range(6)),(stage,ident,kind,seqs)
    drops=int(re.search(r'QUEUE_RELEASE.*drops=(\d+)',row['stderr'])[1])
    if row['mode']=='original':assert row['received']==4 and drops>0
    else:assert row['received']==6 and drops==0
    checks.append({'mode':row['mode'],'icmpID':ident,'sent':6,'received':row['received'],'allSixRepliesAtAllFourPoints':True,'localSocketDrops':drops})
result={'passed':True,'binarySHA256':hashlib.sha256((out/'busybox').read_bytes()).hexdigest(),'checks':checks,'candidateRequestedMinimum':65536,'effectiveBuffer':131072,'controlledReadDelayMs':2500,'scope':'Reproduces local raw socket receive-queue overflow with already-arrived replies; candidate prevents it in both controlled comparisons. Not proof of complete RF/forwarding-loss repair.'}
(out/'live-queue-qa.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
